"""HTTP views (pages + JSON API)."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q
from django.http import (
    FileResponse,
    Http404,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import EnhancementUploadForm
from .models import EnhancementJob
from .services import RealESRGANService
from .tasks import submit_job

MAX_HISTORY = 24


def _serialize_job(job: EnhancementJob) -> dict:
    return {
        "id": str(job.pk),
        "title": job.title or job.filename,
        "status": job.status,
        "model": job.model_name,
        "model_display": job.get_model_name_display(),
        "target": job.target,
        "target_display": job.target_label,
        "scale_label": job.scale_label,
        "output_format": job.output_format,
        "sharpness": job.sharpness,
        "texture": job.texture,
        "denoise": job.denoise_strength,
        "error": job.error_message or None,
        "original": {
            "url": job.original_image.url if job.original_image else None,
            "width": job.original_width,
            "height": job.original_height,
            "size": job.original_size,
        },
        "enhanced": {
            "url": job.enhanced_image.url if job.enhanced_image else None,
            "width": job.enhanced_width,
            "height": job.enhanced_height,
            "size": job.enhanced_size,
        },
        "processing_seconds": job.processing_seconds,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "result_url": reverse("enhancer:result", args=[job.pk]),
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def home(request):
    form = EnhancementUploadForm()

    if request.method == "POST":
        form = EnhancementUploadForm(request.POST, request.FILES)
        if form.is_valid():
            job = form.save()
            submit_job(job.pk)
            if _wants_json(request):
                return JsonResponse(_serialize_job(job), status=202)
            return redirect("enhancer:result", job_id=job.pk)
        if _wants_json(request):
            return JsonResponse({"errors": form.errors}, status=400)
        messages.error(request, "Please fix the errors below and try again.")

    return render(
        request,
        "enhancer/home.html",
        {
            "form": form,
            "recent_jobs": _recent(),
            "max_upload_mb": settings.MAX_UPLOAD_SIZE_MB,
        },
    )


@require_GET
def result(request, job_id):
    job = get_object_or_404(EnhancementJob, pk=job_id)
    return render(request, "enhancer/result.html", {"job": job})


@require_GET
def history(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    jobs = EnhancementJob.objects.all()
    if q:
        jobs = jobs.filter(
            Q(title__icontains=q) | Q(original_image__icontains=q)
        )
    if status in EnhancementJob.Status.values:
        jobs = jobs.filter(status=status)
    stats = EnhancementJob.objects.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=EnhancementJob.Status.COMPLETED)),
        failed=Count("id", filter=Q(status=EnhancementJob.Status.FAILED)),
        processing=Count("id", filter=Q(status=EnhancementJob.Status.PROCESSING)),
    )
    return render(
        request,
        "enhancer/history.html",
        {"jobs": jobs[:200], "stats": stats, "q": q, "status": status},
    )


@require_GET
def about(request):
    return render(request, "enhancer/about.html", {"engine": RealESRGANService().info()})


@require_POST
def delete_job(request, job_id):
    job = get_object_or_404(EnhancementJob, pk=job_id)
    for field in (job.original_image, job.enhanced_image):
        if field:
            field.delete(save=False)
    job.delete()
    messages.success(request, "Job deleted.")
    return redirect("enhancer:history")


@require_GET
def download(request, job_id):
    job = get_object_or_404(EnhancementJob, pk=job_id)
    if not job.enhanced_image:
        raise Http404("No enhanced image available.")
    path = settings.MEDIA_ROOT / job.enhanced_image.name
    if not path.is_file():
        raise Http404("Enhanced file missing from storage.")
    content_type = mimetypes.guess_type(path.name)[0] or "image/png"
    filename = f"enhanced-{job.title or job.pk}{path.suffix}"
    response = FileResponse(path.open("rb"), content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def download_original(request, job_id):
    job = get_object_or_404(EnhancementJob, pk=job_id)
    path = settings.MEDIA_ROOT / job.original_image.name
    if not path.is_file():
        raise Http404("Original file missing from storage.")
    content_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    response = FileResponse(path.open("rb"), content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{Path(job.original_image.name).name}"'
    return response


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------
@require_POST
def api_upload(request):
    form = EnhancementUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": form.errors}, status=400)
    job = form.save()
    submit_job(job.pk)
    return JsonResponse({"ok": True, "job": _serialize_job(job)}, status=202)


@require_GET
def api_status(request, job_id):
    job = get_object_or_404(EnhancementJob, pk=job_id)
    return JsonResponse(_serialize_job(job))


@require_GET
def api_jobs(request):
    jobs = EnhancementJob.objects.all()[:50]
    return JsonResponse({"ok": True, "jobs": [_serialize_job(j) for j in jobs]})


@require_GET
def health(request):
    engine = RealESRGANService()
    payload = {
        # The app always serves; the engine just degrades to a CPU fallback.
        "status": "ok",
        "engine": engine.info(),
        "time": timezone.now().isoformat(),
    }
    return JsonResponse(payload, status=200)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _recent() -> list[EnhancementJob]:
    return list(EnhancementJob.objects.all()[:MAX_HISTORY])


def _wants_json(request) -> bool:
    if request.headers.get("X-Requested-With") == "fetch":
        return True
    accept = request.META.get("HTTP_ACCEPT", "")
    return "application/json" in accept and "text/html" not in accept


@require_GET
def serve_media(request, path):
    """Serve MEDIA_ROOT files when Django is not in DEBUG (e.g. Vercel demo).

    Local-only convenience so before/after images resolve behind a CDN that
    does not have a durable media bucket wired up.
    """
    if not getattr(settings, "SERVE_MEDIA", False):
        raise Http404()
    base = Path(settings.MEDIA_ROOT).resolve()
    try:
        fp = (base / path).resolve()
        fp.relative_to(base)
    except (OSError, ValueError):
        raise Http404()
    if not fp.is_file():
        raise Http404()
    ctype = mimetypes.guess_type(fp.name)[0] or "application/octet-stream"
    response = FileResponse(fp.open("rb"), content_type=ctype)
    response["X-Content-Type-Options"] = "nosniff"
    return response
