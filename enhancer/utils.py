"""File & image validation helpers."""
from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

ALLOWED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


def validate_image_file(file) -> None:
    """Raise ValidationError if the upload is not a supported, safe image."""
    if not file or not getattr(file, "name", None):
        raise ValidationError("No file was provided.")

    ext = Path(file.name).suffix.lower()
    if ext not in settings.ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(
            f"Unsupported file extension “{ext}”. "
            f"Allowed: {', '.join(settings.ALLOWED_IMAGE_EXTENSIONS)}"
        )

    if file.size == 0:
        raise ValidationError("Uploaded file is empty.")

    if file.size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise ValidationError(
            f"File is too large (max {settings.MAX_UPLOAD_SIZE_MB} MB)."
        )

    try:
        from PIL import Image, ImageFile

        ImageFile.LOAD_TRUNCATED_IMAGES = False
        Image.MAX_IMAGE_PIXELS = settings.MAX_IMAGE_PIXELS

        file.seek(0)
        with Image.open(file) as img:
            img.verify()
        file.seek(0)
        with Image.open(file) as img:
            fmt = (img.format or "").upper()
            width, height = img.size

        if fmt not in ALLOWED_FORMATS:
            raise ValidationError(
                f"Unsupported image format “{fmt.lower() or 'unknown'}”. "
                f"Supported: JPEG, PNG, WebP."
            )
        if width * height > settings.MAX_IMAGE_PIXELS:
            raise ValidationError(
                f"Image is too large ({width}×{height}). "
                f"Maximum {settings.MAX_IMAGE_PIXELS:,} pixels."
            )
        if width < 8 or height < 8:
            raise ValidationError("Image is too small (minimum 8×8 pixels).")
    except ValidationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(f"Could not read image: {exc}") from exc
    finally:
        file.seek(0)


def safe_filename(name: str) -> str:
    """Strip directory components and dangerous characters from a filename."""
    base = os.path.basename(name or "image")
    cleaned = "".join(c for c in base if c.isalnum() or c in "._- ")
    return cleaned.strip(". ") or "image"
