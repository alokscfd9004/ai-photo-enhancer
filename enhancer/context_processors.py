from .services import RealESRGANService


def engine_status(request):
    """Expose engine availability to every template."""
    service = RealESRGANService()
    available = service.is_available()
    return {
        "engine_available": available,
        "engine_mode": "realesrgan" if available else "cpu-fallback",
        "engine_info": service.info(),
    }
