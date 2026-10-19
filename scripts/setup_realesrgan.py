#!/usr/bin/env python
"""
Download & install the Real-ESRGAN (NCNN Vulkan) engine + models.

Usage:
    python scripts/setup_realesrgan.py           # auto-detect platform
    python scripts/setup_realesrgan.py --force   # re-download even if present

The engine is placed in  <project>/bin/realesrgan-ncnn-vulkan  (or .exe)
and the models in         <project>/bin/models/
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import stat
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = PROJECT_ROOT / "bin"
MODELS_DIR = BIN_DIR / "models"

RELEASE_TAG = "v0.2.5.0"
BASE_URL = (
    "https://github.com/xinntao/Real-ESRGAN/releases/download/"
    f"{RELEASE_TAG}/"
)

ASSETS = {
    "darwin": "realesrgan-ncnn-vulkan-20220424-macos.zip",
    "linux": "realesrgan-ncnn-vulkan-20220424-ubuntu.zip",
    "win32": "realesrgan-ncnn-vulkan-20220424-windows.zip",
}

BINARY_NAMES = {
    "darwin": "realesrgan-ncnn-vulkan",
    "linux": "realesrgan-ncnn-vulkan",
    "win32": "realesrgan-ncnn-vulkan.exe",
}


def log(msg: str) -> None:
    print(f"[setup] {msg}", flush=True)


def detect_platform() -> str:
    plat = sys.platform
    if plat.startswith("darwin"):
        return "darwin"
    if plat.startswith("linux"):
        return "linux"
    if plat.startswith("win"):
        return "win32"
    raise SystemExit(f"Unsupported platform: {plat}")


def download(url: str, dest: Path) -> None:
    log(f"Downloading {url}")
    tmp = dest.with_suffix(".part")

    def hook(blocks: int, block_size: int, total: int) -> None:
        done = blocks * block_size
        if total > 0:
            pct = min(100.0, done * 100.0 / total)
            sys.stdout.write(f"\r[setup]   {pct:5.1f}%  ({done // 1024 // 1024} MB)")
            sys.stdout.flush()

    try:
        urllib.request.urlretrieve(url, tmp, reporthook=hook)
    except urllib.error.URLError as exc:
        tmp.unlink(missing_ok=True)
        raise SystemExit(
            f"\n[setup] Download failed: {exc}\n"
            f"[setup] Download manually from:\n"
            f"[setup]   {url}\n"
            f"[setup] and extract it into: {BIN_DIR}"
        ) from exc
    print()
    tmp.replace(dest)
    log(f"Saved {dest.name} ({dest.stat().st_size // 1024 // 1024} MB)")


def extract(zip_path: Path, target: Path) -> None:
    log(f"Extracting {zip_path.name} → {target}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target)


def find_binary(root: Path, name: str) -> Path | None:
    for path in root.rglob(name):
        return path
    # fallback: any executable that looks like the engine
    for path in root.rglob("*realesrgan*"):
        if path.is_file() and path.suffix in ("", ".exe"):
            return path
    return None


def find_models_dir(root: Path) -> Path | None:
    for path in root.rglob("models"):
        if path.is_dir() and any(path.glob("*.param")):
            return path
    return None


def make_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def already_installed(plat: str) -> bool:
    binary = BIN_DIR / BINARY_NAMES[plat]
    return binary.is_file() and MODELS_DIR.is_dir() and any(MODELS_DIR.glob("*.param"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Install Real-ESRGAN NCNN Vulkan engine")
    parser.add_argument("--force", action="store_true", help="re-download even if installed")
    args = parser.parse_args()

    plat = detect_platform()
    asset = ASSETS[plat]
    binary_name = BINARY_NAMES[plat]

    if already_installed(plat) and not args.force:
        log(f"Engine already installed at {BIN_DIR / binary_name}")
        log("Use --force to reinstall.")
        return

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    url = BASE_URL + asset
    with tempfile.TemporaryDirectory(prefix="realesrgan-") as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / asset
        download(url, zip_path)
        extract(zip_path, tmp_path / "extracted")

        extracted_root = tmp_path / "extracted"
        # The zip usually contains a top-level folder
        candidates = [extracted_root, *extracted_root.iterdir()]
        binary = None
        models = None
        for cand in candidates:
            if not cand.exists():
                continue
            if binary is None:
                binary = find_binary(cand, binary_name) or find_binary(cand, "realesrgan-ncnn-vulkan")
            if models is None:
                models = find_models_dir(cand)

        if binary is None:
            log("Could not locate the engine binary in the archive. Contents:")
            for p in sorted(extracted_root.rglob("*")):
                log(f"  {p.relative_to(extracted_root)}")
            raise SystemExit(1)

        dest_binary = BIN_DIR / binary_name
        shutil.copy2(binary, dest_binary)
        make_executable(dest_binary)
        log(f"Installed binary → {dest_binary}")

        if models is not None:
            # refresh models dir
            if MODELS_DIR.exists():
                shutil.rmtree(MODELS_DIR)
            shutil.copytree(models, MODELS_DIR)
            log(f"Installed models → {MODELS_DIR}")
            for p in sorted(MODELS_DIR.glob("*.param")):
                log(f"  · {p.name}")
        else:
            log("WARNING: no models folder found in the archive!")

        # copy any bundled shared libraries next to the binary (macOS/Linux)
        for extra in extracted_root.rglob("*"):
            if extra.suffix in {".dylib", ".so", ".dll"} and extra.is_file():
                shutil.copy2(extra, BIN_DIR / extra.name)
                log(f"Installed library → {BIN_DIR / extra.name}")

    log("")
    log("Done. Verify with:")
    log(f'  "{BIN_DIR / binary_name}" -h')
    log("Then start Django:")
    log("  python manage.py migrate")
    log("  python manage.py runserver")


if __name__ == "__main__":
    main()
