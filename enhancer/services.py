"""Thin, production-safe wrapper around the Real-ESRGAN NCNN Vulkan CLI.

Pipeline (v2 — tuned for sharpness):
  1. load + EXIF orientation + mode normalisation (alpha preserved)
  2. JPEG deblock (only when 8×8 block artefacts are detected)
  3. chroma-only denoise (LAB a/b blur — luminance detail is untouched)
  4. Real-ESRGAN NCNN Vulkan super-resolution
  5. fit to the requested target tier (Low / Medium / HD / 2K / 4K) —
     up *and* down; Lanczos for downsizing, Real-ESRGAN for upsizing
  6. multi-scale unsharp (fine detail + clarity) driven by `sharpen`
  7. source-texture restoration (high-pass transfer from the source) driven by `texture`
  8. alpha re-attach + encode (JPEG / PNG / WebP)
"""
from __future__ import annotations

import logging
import math
import os
import re
import shutil
import statistics
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

logger = logging.getLogger("enhancer")

# Native model scales. `realesr-animevideov3` ships x2/x3/x4 variants; the
# x4plus / x4plus-anime models are 4× only.
MULTI_SCALE_MODELS = {"realesr-animevideov3"}
NATIVE_SCALE = {
    "realesrgan-x4plus": 4,
    "realesrgan-x4plus-anime": 4,
    "realesr-animevideov3": 4,
}

# Fit-to-target tiers. The image is fitted *inside* the box (aspect kept),
# so the same tier works for landscape and portrait, and works up and down.
TARGET_BOXES = {
    "low": (854, 480),
    "medium": (1280, 720),
    "hd": (1920, 1080),
    "2k": (2560, 1440),
    "4k": (3840, 2160),
}
DEFAULT_TARGET = "hd"

FORMAT_SPECS = {
    "jpg": {"ext": ".jpg", "engine_fmt": "jpg"},
    "jpeg": {"ext": ".jpg", "engine_fmt": "jpg"},
    "png": {"ext": ".png", "engine_fmt": "png"},
    "webp": {"ext": ".webp", "engine_fmt": "webp"},
}


class EnhancementError(RuntimeError):
    """Raised when the upscaling engine fails or is unavailable."""


@dataclass
class EnhancementResult:
    output_path: Path
    width: int
    height: int
    elapsed_seconds: float
    stdout: str = ""
    engine: str = "realesrgan"


# ---------------------------------------------------------------------------
# Image-quality helpers (pure Pillow — unit-testable without the engine)
# ---------------------------------------------------------------------------
def prepare_image(img, denoise: float = 0.0, deblock: bool = True):
    """Return (rgb_image, alpha_channel_or_None) ready for the engine."""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(img)

    alpha = None
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        alpha = rgba.getchannel("A")
        base = rgba.convert("RGB")
    elif img.mode == "RGB":
        base = img
    else:
        base = img.convert("RGB")

    if deblock and _blockiness(base) > 1.18:
        base = _jpeg_deblock(base)
    if denoise and float(denoise) > 0:
        base = chroma_denoise(base, float(denoise))
    return base, alpha


def chroma_denoise(img, strength: float):
    """Blur only colour channels so luminance detail survives.

    Removes colour noise / JPEG chroma blocks without the waxy look of a
    full-image median pre-filter.
    """
    from PIL import Image, ImageFilter

    strength = max(0.0, min(1.0, float(strength)))
    if strength <= 0:
        return img
    ycbcr = img.convert("YCbCr")
    y, cb, cr = ycbcr.split()
    radius = 0.5 + 1.5 * strength
    cb = cb.filter(ImageFilter.GaussianBlur(radius=radius))
    cr = cr.filter(ImageFilter.GaussianBlur(radius=radius))
    return Image.merge("YCbCr", (y, cb, cr)).convert("RGB")


def _blockiness(img) -> float:
    """Ratio of discontinuity across 8px JPEG block borders vs interior."""
    gray = img.convert("L")
    w, h = gray.size
    step = max(1, min(w, 512) // 64)  # sample for speed on huge images
    px = gray.load()
    edge, inside = [], []
    for y in range(0, h, step):
        for x in range(1, w, step):
            d = abs(px[x, y] - px[x - 1, y])
            (edge if x % 8 == 0 else inside).append(d)
    if not edge or not inside:
        return 1.0
    be = statistics.mean(edge)
    bi = statistics.mean(inside) or 0.01
    return be / max(bi, 0.01)


def _jpeg_deblock(img):
    """Smooth 8×8 block boundaries only — interior detail is preserved."""
    from PIL import Image, ImageDraw, ImageFilter

    w, h = img.size
    softened = img.filter(ImageFilter.MedianFilter(size=3))
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    for x in range(8, w, 8):
        draw.rectangle([x - 1, 0, x, h], fill=255)
    for y in range(8, h, 8):
        draw.rectangle([0, y - 1, w, y], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(0.6))
    return Image.composite(Image.blend(img, softened, 0.55), img, mask)


def post_sharpen(img, strength: float):
    """Multi-scale unsharp: fine detail boost + large-radius clarity."""
    from PIL import ImageFilter

    strength = max(0.0, min(1.0, float(strength)))
    if strength <= 0:
        return img
    longest = max(img.size) or 1
    unit = longest / 1000.0  # radius scales with output resolution
    fine_radius = max(0.6, 0.9 * unit)
    clarity_radius = max(2.0, 3.0 * unit)
    img = img.filter(
        ImageFilter.UnsharpMask(
            radius=fine_radius, percent=int(70 * strength), threshold=2
        )
    )
    img = img.filter(
        ImageFilter.UnsharpMask(
            radius=clarity_radius, percent=int(45 * strength), threshold=3
        )
    )
    return img


def restore_texture(esrgan_img, source_img, strength: float = 0.35):
    """Re-graft source micro-texture (grain, fabric, paper) onto the result.

    Real-ESRGAN can over-smooth high-frequency material texture that was
    present in the source. We extract a scale-aware high-pass from a Lanczos
    upscale of the source and add it back — the AI's edge reconstruction is
    preserved while the original "feel" of surfaces returns.
    """
    from PIL import Image, ImageChops, ImageFilter

    strength = max(0.0, min(1.0, float(strength)))
    if strength <= 0:
        return esrgan_img

    target = esrgan_img.size
    naive = source_img.convert("RGB").resize(target, Image.LANCZOS)

    longest = max(target) or 1
    radius = max(1.0, longest / 1500.0)  # ~1.6 px at 2400 px
    blurred = naive.filter(ImageFilter.GaussianBlur(radius=radius))

    # signed high-pass parked at 128 (128 == "no detail")
    hf = ImageChops.subtract(naive, blurred, scale=1.0, offset=128)

    thr = 2  # ignore sub-threshold micro-noise so flat areas stay flat

    def scale_hf(v: int) -> int:
        d = v - 128
        if abs(d) < thr:
            d = 0
        return 128 + int(d * strength)

    scaled = hf.point(scale_hf)
    return ImageChops.add(esrgan_img.convert("RGB"), scaled, scale=1.0, offset=-128)


def resolve_target(src_size, target: str) -> tuple[int, int]:
    """Fit `src_size` inside the tier box, keeping the aspect ratio.

    Works both ways: a big source into `hd` downsamples, a small source
    into `4k` upscales. Unknown tiers fall back to HD.
    """
    bw, bh = TARGET_BOXES.get(target, TARGET_BOXES[DEFAULT_TARGET])
    w = max(1, int(src_size[0]))
    h = max(1, int(src_size[1]))
    s = min(bw / w, bh / h)
    return max(1, round(w * s)), max(1, round(h * s))


def resize_to_size(img, size):
    """Lanczos resize to an exact (w, h) — the final fit to the tier."""
    from PIL import Image

    size = (int(size[0]), int(size[1]))
    return img if tuple(img.size) == size else img.resize(size, Image.LANCZOS)


def cpu_enhance(img, desired, steps: int | None = None):
    """CPU-only upscaler used when the Vulkan engine is unavailable.

    Progressive Lanczos (about 2x per pass) with an unsharp recovery pass in
    between, then a large-radius clarity boost. Not Real-ESRGAN quality, but
    visibly better than a single Lanczos stretch of the same factor.
    """
    from PIL import Image, ImageFilter

    desired = (int(desired[0]), int(desired[1]))
    current = img.convert("RGB") if img.mode != "RGB" else img
    if tuple(current.size) == desired:
        return current

    remaining = max(
        desired[0] / max(1, current.size[0]),
        desired[1] / max(1, current.size[1]),
    )
    passes = steps or max(1, min(6, int(math.ceil(math.log(remaining, 2)))))
    for _ in range(passes):
        if current.size[0] >= desired[0] and current.size[1] >= desired[1]:
            break
        step = min(2.0, desired[0] / max(1, current.size[0]))
        w = max(1, round(current.size[0] * step))
        h = max(1, round(current.size[1] * step))
        current = current.resize((w, h), Image.LANCZOS)
        current = current.filter(
            ImageFilter.UnsharpMask(radius=1.2, percent=85, threshold=2)
        )

    result = resize_to_size(current, desired)
    # Clarity: large-radius unsharp restores local contrast lost to the stretch.
    return result.filter(
        ImageFilter.UnsharpMask(
            radius=max(2, min(result.size) // 60), percent=55, threshold=2
        )
    )


def encode_image(img, path: Path, fmt: str) -> None:
    """Write the final image with sensible per-format quality settings."""
    fmt = (fmt or "jpg").lower()
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt in ("jpg", "jpeg"):
        img.convert("RGB").save(
            path,
            "JPEG",
            quality=92,
            optimize=True,
            progressive=True,
            subsampling=1,
        )
    elif fmt == "webp":
        img.save(path, "WEBP", quality=92, method=6)
    else:
        if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            img = img.convert("RGBA")
        img.save(path, "PNG", optimize=True, compress_level=9)


def sharpness_score(img) -> float:
    """High-frequency energy (PSTDEV of a Laplacian-ish kernel) — QA metric."""
    gray = img.convert("L")
    w, h = gray.size
    px = list(gray.getdata())
    vals = [
        abs(px[y * w + x] * 2 - px[y * w + x - 1] - px[(y - 1) * w + x])
        for y in range(1, h)
        for x in range(1, w)
    ]
    return statistics.pstdev(vals) if vals else 0.0


# ---------------------------------------------------------------------------
# Engine wrapper
# ---------------------------------------------------------------------------
class RealESRGANService:
    """Execute `realesrgan-ncnn-vulkan` in a safe, bounded way."""

    def __init__(
        self,
        binary_path: Path | None = None,
        models_dir: Path | None = None,
        gpu_id: int | None = None,
        timeout: int | None = None,
    ) -> None:
        self.binary_path = Path(binary_path or settings.REALESRGAN_BINARY)
        self.models_dir = Path(models_dir or settings.REALESRGAN_MODELS_DIR)
        self.gpu_id = settings.REALESRGAN_GPU_ID if gpu_id is None else gpu_id
        self.timeout = timeout or settings.REALESRGAN_TIMEOUT_SECONDS

    # -- availability -----------------------------------------------------
    def is_available(self) -> bool:
        if not self.binary_path.is_file():
            return False
        return os.access(self.binary_path, os.X_OK) and self.models_dir.is_dir()

    def info(self) -> dict:
        return {
            "available": self.is_available(),
            "mode": "realesrgan" if self.is_available() else "cpu-fallback",
            "binary": str(self.binary_path),
            "binary_exists": self.binary_path.is_file(),
            "models_dir": str(self.models_dir),
            "models_present": self._list_models() if self.models_dir.is_dir() else [],
            "gpu_id": self.gpu_id,
            "platform": shutil.which("vulkaninfo") and "vulkan-detected" or "unknown",
        }

    def _list_models(self) -> list[str]:
        names = set()
        if not self.models_dir.is_dir():
            return []
        for path in self.models_dir.glob("*.param"):
            stem = re.sub(r"-?x[2-4]$", "", path.stem)
            names.add(stem)
        return sorted(names)

    # -- processing -------------------------------------------------------
    def upscale(
        self,
        input_path: Path | str,
        output_path: Path | str,
        model: str = "realesrgan-x4plus",
        target: str = "hd",
        denoise: float = 0.0,
        sharpen: float = 0.45,
        texture: float = 0.35,
        output_format: str = "jpg",
        tile: int | None = None,
    ) -> EnhancementResult:
        from PIL import Image

        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.is_file():
            raise EnhancementError(f"Input file not found: {input_path}")

        fmt = (output_format or self._format_from_suffix(output_path)).lower()
        spec = FORMAT_SPECS.get(fmt, FORMAT_SPECS["jpg"])
        if output_path.suffix.lower() != spec["ext"]:
            output_path = output_path.with_suffix(spec["ext"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1–3. orientation, alpha, deblock, chroma denoise
        with Image.open(input_path) as raw:
            prepared, alpha = prepare_image(raw, denoise=denoise, deblock=True)

        desired = resolve_target(prepared.size, target)
        factor = desired[0] / prepared.size[0]

        started = time.perf_counter()
        stdout_tail = ""
        if factor <= 1.02:
            # Downscale (or already the right size): Lanczos only, no engine.
            engine_used = "lanczos"
            result = resize_to_size(prepared, desired)
        elif not self.is_available():
            # No Vulkan runtime (e.g. serverless): fall back so the job still
            # completes instead of erroring out.
            logger.warning(
                "Real-ESRGAN engine unavailable (%s); using CPU fallback",
                self.binary_path,
            )
            engine_used = "cpu-fallback"
            result = cpu_enhance(prepared, desired)
        else:
            # Upscale: Real-ESRGAN (cascaded for very large factors), then a
            # Lanczos fit to the exact tier size.
            engine_used = "realesrgan"
            current = prepared
            for _ in range(2):
                remaining = desired[0] / current.size[0]
                if remaining <= 1.05:
                    break
                engine_scale = self._engine_scale_for(model, remaining)
                current, stdout_tail = self._run_engine(
                    current,
                    model,
                    engine_scale,
                    output_path.parent,
                    output_path.stem,
                    tile,
                )
            result = resize_to_size(current, desired)
        elapsed = time.perf_counter() - started

        # 6–8. sharpen, texture, alpha, encode
        result = post_sharpen(result, sharpen)
        if texture and float(texture) > 0 and factor > 1.02:
            result = restore_texture(result, prepared, texture)
        if alpha is not None:
            from PIL import Image as PILImage

            a = alpha.resize(result.size, PILImage.LANCZOS)
            result = result.convert("RGBA")
            result.putalpha(a)
        encode_image(result, output_path, fmt)
        width, height = result.size

        return EnhancementResult(
            output_path=output_path,
            width=width,
            height=height,
            elapsed_seconds=elapsed,
            stdout=(stdout_tail or "")[-2000:],
            engine=engine_used,
        )

    def _run_engine(
        self,
        img,
        model: str,
        engine_scale: int,
        workdir: Path,
        stem: str,
        tile: int | None,
    ):
        """One Real-ESRGAN pass. Returns (upscaled_image, stdout)."""
        from PIL import Image

        engine_input = workdir / f".prep-{stem}.png"
        engine_output = workdir / f".eng-{stem}.png"
        img.save(engine_input, "PNG")

        cmd = [
            str(self.binary_path),
            "-i", str(engine_input),
            "-o", str(engine_output),
            "-n", model,
            "-s", str(engine_scale),
            "-m", str(self.models_dir),
            "-f", "png",
        ]
        if self.gpu_id is not None and int(self.gpu_id) >= 0:
            cmd += ["-g", str(int(self.gpu_id))]
        if tile:
            cmd += ["-t", str(int(tile))]

        logger.info("Real-ESRGAN command: %s", " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            engine_input.unlink(missing_ok=True)
            engine_output.unlink(missing_ok=True)
            raise EnhancementError(
                f"Enhancement timed out after {self.timeout}s."
            ) from exc
        except OSError as exc:
            raise EnhancementError(f"Could not launch engine: {exc}") from exc

        engine_input.unlink(missing_ok=True)
        if proc.returncode != 0 or not engine_output.is_file():
            engine_output.unlink(missing_ok=True)
            tail = (proc.stderr or proc.stdout or "").strip()[-800:]
            raise EnhancementError(
                f"Engine failed (exit {proc.returncode}). {tail}"
            )

        with Image.open(engine_output) as out:
            out = out.convert("RGB")
            out.load()
            result = out.copy()
        engine_output.unlink(missing_ok=True)
        return result, (proc.stdout or "")

    @staticmethod
    def _engine_scale_for(model: str, remaining: float) -> int:
        """Engine scale that covers `remaining` in one pass (2/3/4, or 4)."""
        if model in MULTI_SCALE_MODELS:
            return min(4, max(2, math.ceil(remaining - 1e-9)))
        return 4

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _format_from_suffix(path: Path) -> str:
        ext = path.suffix.lower()
        return {".jpg": "jpg", ".jpeg": "jpg", ".png": "png", ".webp": "webp"}.get(
            ext, "jpg"
        )

    @staticmethod
    def _probe_size(path: Path) -> tuple[int, int]:
        try:
            from PIL import Image

            with Image.open(path) as img:
                return img.size
        except Exception:  # noqa: BLE001
            return 0, 0
