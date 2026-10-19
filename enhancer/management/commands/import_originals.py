"""Create jobs for images already sitting in media/originals (and process them)."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

ALLOWED = {".jpg", ".jpeg", ".png", ".webp"}


class Command(BaseCommand):
    help = (
        "Scan media/originals for images that have no job yet, create enhancement "
        "jobs for them and queue processing. Use --target/--model/--format to taste."
    )

    def add_arguments(self, parser):
        parser.add_argument("--target", default="hd",
                            choices=["low", "medium", "hd", "2k", "4k"])
        parser.add_argument("--model", default="realesrgan-x4plus",
                            choices=["realesrgan-x4plus", "realesrgan-x4plus-anime", "realesr-animevideov3"])
        parser.add_argument("--format", dest="output_format", default="jpg",
                            choices=["jpg", "png", "webp"])
        parser.add_argument("--sharpness", type=float, default=0.45)
        parser.add_argument("--denoise", type=float, default=0.0)
        parser.add_argument("--texture", type=float, default=0.35)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        from enhancer.models import EnhancementJob
        from enhancer.tasks import submit_job

        root = Path(settings.MEDIA_ROOT) / "originals"
        if not root.is_dir():
            self.stdout.write(self.style.WARNING(f"{root} does not exist"))
            return

        known = set(EnhancementJob.objects.values_list("original_image", flat=True))
        found = queued = 0

        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in ALLOWED:
                continue
            if path.name.startswith("."):
                continue
            rel = str(path.relative_to(settings.MEDIA_ROOT)).replace("\\", "/")
            found += 1
            if rel in known:
                self.stdout.write(f"skip (already has job): {rel}")
                continue

            title = path.stem.replace("_", " ").replace("-", " ").strip()[:120]
            if opts["dry_run"]:
                self.stdout.write(self.style.NOTICE(f"would import: {rel}"))
                continue

            job = EnhancementJob.objects.create(
                title=title,
                original_image=rel,
                model_name=opts["model"],
                target=opts["target"],
                output_format=opts["output_format"],
                sharpness=opts["sharpness"],
                denoise_strength=opts["denoise"],
                texture=opts["texture"],
            )
            submit_job(job.pk)
            queued += 1
            self.stdout.write(self.style.SUCCESS(f"queued: {rel} → job {job.pk}"))

        self.stdout.write(
            f"Done. scanned={found} queued={queued} "
            f"(use --dry-run to preview)"
        )
