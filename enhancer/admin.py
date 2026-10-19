from django.contrib import admin

from .models import EnhancementJob


@admin.register(EnhancementJob)
class EnhancementJobAdmin(admin.ModelAdmin):
    list_display = (
        "id_short",
        "title",
        "status",
        "model_name",
        "target",
        "resolution_label",
        "processing_seconds",
        "created_at",
    )
    list_filter = ("status", "model_name", "target", "created_at")
    search_fields = ("id", "title", "original_image")
    readonly_fields = (
        "id",
        "created_at",
        "started_at",
        "completed_at",
        "processing_seconds",
        "original_width",
        "original_height",
        "enhanced_width",
        "enhanced_height",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    @admin.display(description="Job ID")
    def id_short(self, obj) -> str:
        return str(obj.pk)[:8]
