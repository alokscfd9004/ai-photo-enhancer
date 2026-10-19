from django import template
from django.template.defaultfilters import filesizeformat

register = template.Library()


@register.filter
def pretty_size(value):
    """Render a byte count as a human readable size."""
    try:
        return filesizeformat(int(value))
    except (TypeError, ValueError):
        return "—"


@register.filter
def pretty_dims(job):
    """Render `1920 × 1080` for a job's original dimensions."""
    if not job:
        return "—"
    w, h = job.original_width, job.original_height
    if not w or not h:
        return "—"
    return f"{w} × {h}"


@register.filter
def enhanced_dims(job):
    if not job:
        return "—"
    w, h = job.enhanced_width, job.enhanced_height
    if not w or not h:
        return "—"
    return f"{w} × {h}"
