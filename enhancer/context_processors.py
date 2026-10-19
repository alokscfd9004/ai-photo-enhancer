from .services import RealESRGANService


def engine_status(request):
    """Expose engine availability to every template."""
    service = RealESRGANService()
    return {
        "engine_available": service.is_available(),
        "engine_info": service.info(),
    }
