"""Quick end-to-end smoke test of the Real-ESRGAN service."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ai_photo_enhancer.settings")

import django

django.setup()

from PIL import Image

from enhancer.services import RealESRGANService

src = Path("/tmp/test_src.png")
img = Image.new("RGB", (64, 48))
for x in range(64):
    for y in range(48):
        img.putpixel((x, y), ((x * 4) % 256, (y * 5) % 256, 128))
img.save(src)
print("source:", Image.open(src).size)

svc = RealESRGANService()
print("available:", svc.is_available())
print("info:", svc.info())

out = Path("/tmp/test_out_svc.png")
res = svc.upscale(src, out, model="realesrgan-x4plus", target="hd", denoise=0.4)
print("x4plus result:", res)

out2 = Path("/tmp/test_out_av3.png")
res2 = svc.upscale(src, out2, model="realesr-animevideov3", target="medium", denoise=0.4)
print("animevideov3 x2 result:", res2)

out3 = Path("/tmp/test_out_anime.png")
res3 = svc.upscale(src, out3, model="realesrgan-x4plus-anime", target="4k", denoise=0.4)
print("anime x4plus result:", res3)

print("ALL OK")
