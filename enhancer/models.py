"""Domain models for enhancement jobs."""
from __future__ import annotations

import uuid

from django.db import models
from django.urls import reverse
from django.utils import timezone


class EnhancementJob(models.Model):
    """A single image upscaling request and its result."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class ModelName(models.TextChoices):
        GENERAL = "realesrgan-x4plus", "General photo (RealESRGAN x4plus)"
        ANIME = "realesrgan-x4plus-anime", "Anime / illustration (x4plus anime)"
        ANIME_VIDEO = "realesr-animevideov3", "Fast general / video (AnimeVideo v3)"

    class Target(models.TextChoices):
        LOW = "low", "Low — 480p"
        MEDIUM = "medium", "Medium — 720p"
        HD = "hd", "HD — 1080p"
        QHD = "2k", "2K — QHD"
        UHD = "4k", "4K — UHD"

    class OutputFormat(models.TextChoices):
        JPG = "jpg", "JPEG — small (recommended)"
        PNG = "png", "PNG — lossless"
        WEBP = "webp", "WebP — modern"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=120, blank=True)

    original_image = models.ImageField(upload_to="originals/%Y/%m/%d/")
    enhanced_image = models.ImageField(upload_to="enhanced/%Y/%m/%d/", blank=True)

    model_name = models.CharField(
        max_length=64, choices=ModelName.choices, default=ModelName.GENERAL
    )
    target = models.CharField(
        max_length=8, choices=Target.choices, default=Target.HD,
        help_text="Output size tier — fitted inside the box, aspect kept",
    )
    output_format = models.CharField(
        max_length=8, choices=OutputFormat.choices, default=OutputFormat.JPG
    )
    sharpness = models.FloatField(
        default=0.45,
        help_text="Post-process detail boost (0 = off, 1 = maximum)",
    )
    denoise_strength = models.FloatField(
        default=0.0,
        help_text="Color/JPEG cleanup strength (luminance detail is kept)",
    )
    texture = models.FloatField(
        default=0.35,
        help_text="Source micro-texture restoration (0 = off, 1 = maximum)",
    )
    tile_size = models.PositiveIntegerField(default=0, help_text="0 = auto")

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    error_message = models.TextField(blank=True)

    original_width = models.PositiveIntegerField(null=True, blank=True)
    original_height = models.PositiveIntegerField(null=True, blank=True)
    enhanced_width = models.PositiveIntegerField(null=True, blank=True)
    enhanced_height = models.PositiveIntegerField(null=True, blank=True)
    original_size = models.PositiveBigIntegerField(null=True, blank=True)
    enhanced_size = models.PositiveBigIntegerField(null=True, blank=True)

    processing_seconds = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Enhancement job"
        verbose_name_plural = "Enhancement jobs"
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        label = self.title or self.original_image.name
        return f"{label} [{self.status}]"

    def get_absolute_url(self) -> str:
        return reverse("enhancer:result", args=[self.pk])

    @property
    def is_finished(self) -> bool:
        return self.status in (self.Status.COMPLETED, self.Status.FAILED)

    @property
    def filename(self) -> str:
        return self.title or self.original_image.name.split("/")[-1]

    @property
    def resolution_label(self) -> str:
        if self.original_width and self.enhanced_width:
            return f"{self.original_width}×{self.original_height} → {self.enhanced_width}×{self.enhanced_height}"
        return "—"

    @property
    def target_label(self) -> str:
        return self.get_target_display()

    @property
    def scale_label(self) -> str:
        """Actual resize factor, e.g. '2.72×' or '÷2.00' when downsizing."""
        if self.original_width and self.enhanced_width and self.original_width:
            r = self.enhanced_width / self.original_width
            return f"{r:.2f}×" if r >= 1 else f"÷{1 / r:.2f}"
        return "—"

    @property
    def upscale_factor(self) -> str:
        return self.scale_label

    def mark_started(self) -> None:
        self.status = self.Status.PROCESSING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])

    def mark_completed(self, **fields) -> None:
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        for key, value in fields.items():
            setattr(self, key, value)
        self.save()

    def mark_failed(self, message: str) -> None:
        self.status = self.Status.FAILED
        self.error_message = message[:4000]
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "error_message", "completed_at"])
