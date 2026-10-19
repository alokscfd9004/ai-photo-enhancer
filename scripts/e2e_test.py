"""Full end-to-end: upload → process_job → result on disk."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ai_photo_enhancer.settings")

import django

django.setup()

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from enhancer.models import EnhancementJob
from enhancer.tasks import process_job

img = Image.new("RGB", (80, 60))
for x in range(80):
    for y in range(60):
        img.putpixel((x, y), (x * 3 % 256, y * 4 % 256, 200))
buf_path = Path("/tmp/e2e_src.png")
img.save(buf_path)
data = buf_path.read_bytes()

upload = SimpleUploadedFile("e2e_photo.png", data, content_type="image/png")
job = EnhancementJob.objects.create(
    title="E2E test",
    original_image=upload,
    model_name="realesrgan-x4plus",
    target="hd",
    denoise_strength=0.4,
)
print("created job:", job.pk, "status:", job.status)
print("original path:", job.original_image.name)

process_job(job.pk)
job.refresh_from_db()

print("final status:", job.status)
print("error:", job.error_message)
print("orig dims:", job.original_width, "x", job.original_height)
print("enh  dims:", job.enhanced_width, "x", job.enhanced_height)
print("enh  file:", job.enhanced_image.name)
print("time:", job.processing_seconds, "s")

assert job.status == EnhancementJob.Status.COMPLETED, job.error_message
from enhancer.services import resolve_target

expected = resolve_target((job.original_width, job.original_height), job.target)
assert (job.enhanced_width, job.enhanced_height) == expected, (
    (job.enhanced_width, job.enhanced_height),
    expected,
)
assert (settings.MEDIA_ROOT / job.enhanced_image.name).is_file()
print("E2E OK", f"({job.target} -> {expected[0]}x{expected[1]})")
