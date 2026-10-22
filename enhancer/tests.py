import inspect
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from .models import EnhancementJob
from .services import (
    RealESRGANService,
    chroma_denoise,
    encode_image,
    post_sharpen,
    prepare_image,
    resize_to_size,
    resolve_target,
    restore_texture,
    sharpness_score,
)
from .utils import safe_filename


class UtilsTests(SimpleTestCase):
    def test_safe_filename_strips_paths(self):
        self.assertEqual(safe_filename("../../etc/passwd"), "passwd")
        self.assertEqual(safe_filename("my photo!!.png"), "my photo.png")

    def test_safe_filename_fallback(self):
        self.assertEqual(safe_filename("..."), "image")


class TargetTests(SimpleTestCase):
    def test_upscale_fits_inside_4k_box(self):
        # 600x794 portrait -> limited by the 2160px height side
        self.assertEqual(resolve_target((600, 794), "4k"), (1632, 2160))

    def test_downscale_landscape_to_hd(self):
        self.assertEqual(resolve_target((5000, 4000), "hd"), (1350, 1080))

    def test_upscale_square_to_medium(self):
        self.assertEqual(resolve_target((320, 320), "medium"), (720, 720))

    def test_low_tier_downscales(self):
        self.assertEqual(resolve_target((3000, 2000), "low"), (720, 480))

    def test_unknown_target_falls_back_to_hd(self):
        self.assertEqual(
            resolve_target((400, 300), "nope"), resolve_target((400, 300), "hd")
        )

    def test_never_zero(self):
        w, h = resolve_target((1, 5000), "low")
        self.assertGreaterEqual(w, 1)
        self.assertGreaterEqual(h, 1)

    def test_resize_to_size_exact(self):
        from PIL import Image

        img = Image.new("RGB", (10, 20), (1, 2, 3))
        self.assertEqual(resize_to_size(img, (40, 80)).size, (40, 80))
        self.assertIs(resize_to_size(img, (10, 20)), img)


class PipelineTests(SimpleTestCase):
    def _checkerboard(self, size=64, cell=8):
        from PIL import Image

        img = Image.new("RGB", (size, size), (0, 0, 0))
        px = img.load()
        for y in range(size):
            for x in range(size):
                on = ((x // cell) + (y // cell)) % 2 == 0
                px[x, y] = (240, 240, 240) if on else (10, 10, 10)
        return img

    def test_post_sharpen_increases_high_frequency_energy(self):
        from PIL import Image

        base = self._checkerboard(64, 16).resize((256, 256), Image.LANCZOS)
        before = sharpness_score(base)
        boosted = post_sharpen(base.copy(), 0.6)
        after = sharpness_score(boosted)
        self.assertGreater(after, before * 1.02)

    def test_post_sharpen_zero_is_noop(self):
        img = self._checkerboard()
        self.assertEqual(sharpness_score(post_sharpen(img.copy(), 0.0)), sharpness_score(img))

    def test_chroma_denoise_keeps_luminance_edges(self):
        from PIL import Image

        img = self._checkerboard(48, 12)
        y_before = img.convert("L").getextrema()
        out = chroma_denoise(img, 1.0)
        y_after = out.convert("L").getextrema()
        self.assertEqual(y_before, y_after)

    def test_prepare_preserves_alpha(self):
        from PIL import Image

        img = Image.new("RGBA", (32, 32), (255, 0, 0, 0))
        img.putpixel((16, 16), (0, 255, 0, 255))
        rgb, alpha = prepare_image(img, denoise=0.0, deblock=False)
        self.assertIsNotNone(alpha)
        self.assertEqual(alpha.size, (32, 32))
        self.assertEqual(alpha.getpixel((16, 16)), 255)

    def test_prepare_applies_exif_orientation(self):
        import io

        from PIL import Image

        img = Image.new("RGB", (40, 20), (10, 20, 30))
        buf = io.BytesIO()
        exif = img.getexif()
        exif[274] = 6  # rotate 90 CW on load
        img.save(buf, "JPEG", exif=exif)
        buf.seek(0)
        loaded = Image.open(buf)
        rgb, _ = prepare_image(loaded, denoise=0.0, deblock=False)
        self.assertEqual(rgb.size, (20, 40))  # transposed

    def test_restore_texture_increases_high_frequency_energy(self):
        from PIL import ImageFilter

        textured = self._checkerboard(128, 4)
        smoothed = textured.filter(ImageFilter.GaussianBlur(2.5))
        out = restore_texture(smoothed, textured, 0.7)
        self.assertGreater(sharpness_score(out), sharpness_score(smoothed))

    def test_restore_texture_zero_is_noop(self):
        from PIL import ImageFilter

        textured = self._checkerboard(64, 8)
        smoothed = textured.filter(ImageFilter.GaussianBlur(1.5))
        out = restore_texture(smoothed, textured, 0.0)
        self.assertEqual(list(out.getdata()), list(smoothed.getdata()))

    def test_restore_texture_keeps_output_size(self):
        from PIL import Image

        src = self._checkerboard(32, 8)
        big = Image.new("RGB", (128, 128), (30, 30, 30))
        out = restore_texture(big, src, 0.5)
        self.assertEqual(out.size, (128, 128))

    def test_encode_all_formats(self):
        import tempfile
        from pathlib import Path

        from PIL import Image

        img = Image.new("RGB", (64, 48), (200, 100, 50))
        with tempfile.TemporaryDirectory() as td:
            for fmt, ext in (("jpg", ".jpg"), ("png", ".png"), ("webp", ".webp")):
                p = Path(td) / f"out{ext}"
                encode_image(img, p, fmt)
                self.assertTrue(p.is_file(), fmt)
                with Image.open(p) as re:
                    re.load()
                    self.assertEqual(re.size, (64, 48), fmt)


class ModelTests(TestCase):
    def test_create_job_defaults(self):
        job = EnhancementJob.objects.create(original_image="originals/test.jpg")
        self.assertEqual(job.status, EnhancementJob.Status.PENDING)
        self.assertEqual(job.target, EnhancementJob.Target.HD)
        self.assertEqual(job.scale_label, "—")
        self.assertEqual(job.output_format, EnhancementJob.OutputFormat.JPG)
        self.assertEqual(job.sharpness, 0.45)
        self.assertEqual(job.texture, 0.35)
        self.assertEqual(job.denoise_strength, 0.0)
        self.assertFalse(job.is_finished)

    def test_mark_lifecycle(self):
        job = EnhancementJob.objects.create(original_image="originals/a.jpg")
        job.mark_started()
        self.assertEqual(job.status, EnhancementJob.Status.PROCESSING)
        job.mark_failed("boom")
        job.refresh_from_db()
        self.assertEqual(job.status, EnhancementJob.Status.FAILED)
        self.assertIn("boom", job.error_message)


class ServiceTests(SimpleTestCase):
    def test_info_structure(self):
        info = RealESRGANService().info()
        self.assertIn("available", info)
        self.assertIn("binary", info)

    def test_is_available_false_without_binary(self):
        svc = RealESRGANService(binary_path="/nonexistent/realesrgan")
        self.assertFalse(svc.is_available())


class ViewTests(TestCase):
    def test_home_renders(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "AI Photo Enhancer")

    def test_home_has_format_and_sharpness_controls(self):
        resp = self.client.get("/")
        self.assertContains(resp, "output_format")
        self.assertContains(resp, "sharpness")
        self.assertContains(resp, "texture")
        self.assertContains(resp, "name=\"target\"")
        self.assertContains(resp, "theme-toggle")

    def test_health_endpoint(self):
        resp = self.client.get("/health/")
        self.assertIn(resp.status_code, (200, 503))
        self.assertIn("engine", resp.json())

    def test_history_renders(self):
        resp = self.client.get("/history/")
        self.assertEqual(resp.status_code, 200)

    def test_api_jobs(self):
        resp = self.client.get("/api/jobs/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_upload_rejects_bad_file(self):
        bad = SimpleUploadedFile(
            "evil.exe", b"not an image", content_type="application/octet-stream"
        )
        resp = self.client.post(
            "/api/upload/",
            {
                "original_image": bad,
                "model_name": "realesrgan-x4plus",
                "target": "hd",
            },
        )
        self.assertEqual(resp.status_code, 400)


class StaticStorageTests(SimpleTestCase):
    """Regression tests for the production (manifest) static files storage."""

    def _storage(self):
        from ai_photo_enhancer.storage import (
            ForgivingCompressedManifestStaticFilesStorage,
        )

        return ForgivingCompressedManifestStaticFilesStorage(
            location=settings.STATIC_ROOT,
            base_url=settings.STATIC_URL,
        )

    def test_manifest_is_not_strict(self):
        from ai_photo_enhancer.storage import (
            ForgivingCompressedManifestStaticFilesStorage,
        )

        self.assertFalse(ForgivingCompressedManifestStaticFilesStorage.manifest_strict)

    def test_stored_name_accepts_any_signature(self):
        # Regression: a hardcoded ``stored_name(self, name, hashed_name=None)``
        # raised TypeError inside WhiteNoise startup and 500'd every request.
        from ai_photo_enhancer.storage import (
            ForgivingCompressedManifestStaticFilesStorage,
        )

        params = inspect.signature(
            ForgivingCompressedManifestStaticFilesStorage.stored_name
        ).parameters
        self.assertIn("args", params)
        self.assertIn("kwargs", params)

    def test_existing_asset_resolves_to_hashed_name(self):
        url = self._storage().url("enhancer/css/style.css")
        self.assertTrue(url.startswith(settings.STATIC_URL))
        self.assertNotEqual(url, settings.STATIC_URL + "enhancer/css/style.css")

    def test_missing_asset_does_not_raise(self):
        url = self._storage().url("enhancer/does-not-exist.css")
        self.assertEqual(url, settings.STATIC_URL + "enhancer/does-not-exist.css")


class CpuFallbackTests(SimpleTestCase):
    """The app must keep working when the Vulkan engine is unavailable."""

    def test_cpu_enhance_hits_target_size(self):
        from PIL import Image

        from enhancer.services import cpu_enhance

        src = Image.new("RGB", (40, 30), (120, 80, 200))
        self.assertEqual(cpu_enhance(src, (1440, 1080)).size, (1440, 1080))

    def test_cpu_enhance_downsizes(self):
        from PIL import Image

        from enhancer.services import cpu_enhance

        src = Image.new("RGB", (800, 600), (10, 20, 30))
        self.assertEqual(cpu_enhance(src, (200, 150)).size, (200, 150))

    def test_cpu_enhance_is_sharper_than_plain_lanczos(self):
        from PIL import Image

        from enhancer.services import cpu_enhance, resize_to_size, sharpness_score

        src = Image.new("RGB", (40, 30), (0, 0, 0))
        for x in range(40):
            for y in range(30):
                if (x // 4 + y // 4) % 2:
                    src.putpixel((x, y), (255, 255, 255))
        target = (240, 180)
        self.assertGreater(
            sharpness_score(cpu_enhance(src, target)),
            sharpness_score(resize_to_size(src, target)),
        )

    def test_upscale_falls_back_when_engine_missing(self):
        import tempfile

        from PIL import Image

        from enhancer.services import RealESRGANService

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src = td / "in.png"
            Image.new("RGB", (40, 30), (200, 30, 30)).save(src)
            svc = RealESRGANService(binary_path=td / "missing-binary")
            self.assertFalse(svc.is_available())
            res = svc.upscale(src, td / "out.jpg", target="hd")
            self.assertEqual(res.engine, "cpu-fallback")
            self.assertEqual((res.width, res.height), (1440, 1080))
            self.assertTrue(res.output_path.is_file())

    def test_info_reports_mode(self):
        from enhancer.services import RealESRGANService

        info = RealESRGANService().info()
        self.assertIn("mode", info)
        self.assertIn(info["mode"], ("realesrgan", "cpu-fallback"))


class ServeMediaTests(TestCase):
    """/media/* must resolve, or before/after images render as broken."""

    def test_media_is_served_by_default(self):
        self.assertTrue(settings.SERVE_MEDIA)

    def test_serves_uploaded_file(self):
        from django.core.files.base import ContentFile

        job = EnhancementJob.objects.create(
            title="media serve",
            model_name="realesrgan-x4plus",
            target="hd",
            output_format="jpg",
        )
        job.enhanced_image.save("probe.jpg", ContentFile(b"\xff\xd8\xff\xe0fakejpeg"), save=True)
        resp = self.client.get(settings.MEDIA_URL + job.enhanced_image.name)
        self.assertEqual(resp.status_code, 200)

    def test_missing_file_404s(self):
        resp = self.client.get("/media/enhanced/nope/missing.jpg")
        self.assertEqual(resp.status_code, 404)

    def test_path_traversal_is_rejected(self):
        resp = self.client.get("/media/../../etc/passwd")
        self.assertIn(resp.status_code, (404, 400))
