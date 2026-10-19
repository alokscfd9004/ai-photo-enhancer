"""Background job execution (thread pool, no external broker required)."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.conf import settings

from .services import EnhancementError, RealESRGANService

logger = logging.getLogger("enhancer")

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()

_EXT = {"jpg": ".jpg", "jpeg": ".jpg", "png": ".png", "webp": ".webp"}


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, settings.REALESRGAN_MAX_WORKERS),
                thread_name_prefix="realesrgan",
            )
        return _executor


def process_job(job_id) -> None:
    """Run one enhancement job end-to-end. Safe to call in a worker thread."""
    from .models import EnhancementJob

    try:
        job = EnhancementJob.objects.get(pk=job_id)
    except EnhancementJob.DoesNotExist:
        logger.error("Job %s vanished before processing", job_id)
        return

    if job.status not in (
        EnhancementJob.Status.PENDING,
        EnhancementJob.Status.PROCESSING,
    ):
        return

    service = RealESRGANService()
    input_path = settings.MEDIA_ROOT / job.original_image.name

    try:
        job.mark_started()

        if not service.is_available():
            raise EnhancementError(
                "Real-ESRGAN engine is not installed. "
                "Run `python scripts/setup_realesrgan.py` then retry."
            )
        if not input_path.is_file():
            raise EnhancementError(f"Uploaded file is missing: {input_path}")

        from PIL import Image, ImageOps

        with Image.open(input_path) as img:
            img = ImageOps.exif_transpose(img)
            job.original_width, job.original_height = img.size
        job.original_size = input_path.stat().st_size

        original_rel = Path(job.original_image.name)
        if original_rel.parts and original_rel.parts[0] == "originals":
            tail = original_rel.relative_to("originals")
        else:
            tail = Path(original_rel.name)

        ext = _EXT.get((job.output_format or "jpg").lower(), ".jpg")
        output_rel = (Path("enhanced") / tail).with_suffix(ext)
        output_abs = settings.MEDIA_ROOT / output_rel

        result = service.upscale(
            input_path=input_path,
            output_path=output_abs,
            model=job.model_name,
            target=job.target,
            denoise=job.denoise_strength,
            sharpen=job.sharpness,
            texture=job.texture,
            output_format=job.output_format,
            tile=job.tile_size or settings.REALESRGAN_DEFAULT_TILE,
        )

        job.enhanced_image.name = str(result.output_path.relative_to(settings.MEDIA_ROOT)).replace(
            "\\", "/"
        )
        job.enhanced_width = result.width
        job.enhanced_height = result.height
        job.enhanced_size = result.output_path.stat().st_size
        job.processing_seconds = round(result.elapsed_seconds, 3)
        job.mark_completed()
        logger.info("Job %s completed in %.2fs", job_id, result.elapsed_seconds)

    except EnhancementError as exc:
        logger.warning("Job %s failed: %s", job_id, exc)
        job.mark_failed(str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s crashed", job_id)
        job.mark_failed(f"Unexpected error: {exc}")


def submit_job(job_id) -> None:
    """Queue a job onto the background pool."""
    _get_executor().submit(process_job, job_id)
