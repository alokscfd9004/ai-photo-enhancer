"""Forms for the enhancement workflow."""
from __future__ import annotations

from django import forms

from .models import EnhancementJob
from .utils import safe_filename, validate_image_file


class EnhancementUploadForm(forms.ModelForm):
    """Upload + enhancement options."""

    class Meta:
        model = EnhancementJob
        fields = [
            "title",
            "original_image",
            "model_name",
            "target",
            "output_format",
            "sharpness",
            "texture",
            "denoise_strength",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "field",
                    "placeholder": "Give this photo a name (optional)",
                    "maxlength": 120,
                }
            ),
            "original_image": forms.ClearableFileInput(
                attrs={
                    "class": "file-input",
                    "accept": ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp",
                }
            ),
            "model_name": forms.Select(attrs={"class": "field"}),
            "target": forms.Select(attrs={"class": "field", "id": "target-select"}),
            "output_format": forms.Select(attrs={"class": "field"}),
            "sharpness": forms.NumberInput(
                attrs={
                    "class": "field range",
                    "type": "range",
                    "min": 0,
                    "max": 1,
                    "step": 0.05,
                }
            ),
            "texture": forms.NumberInput(
                attrs={
                    "class": "field range",
                    "type": "range",
                    "min": 0,
                    "max": 1,
                    "step": 0.05,
                }
            ),
            "denoise_strength": forms.NumberInput(
                attrs={
                    "class": "field range",
                    "type": "range",
                    "min": 0,
                    "max": 1,
                    "step": 0.05,
                }
            ),
        }

    def clean_original_image(self):
        image = self.cleaned_data.get("original_image")
        if image:
            validate_image_file(image)
            image.name = safe_filename(image.name)
        return image

    def clean_denoise_strength(self):
        return self._clamp(self.cleaned_data.get("denoise_strength", 0.0), 0.0)

    def clean_sharpness(self):
        return self._clamp(self.cleaned_data.get("sharpness", 0.45), 0.45)

    def clean_texture(self):
        return self._clamp(self.cleaned_data.get("texture", 0.35), 0.35)

    @staticmethod
    def _clamp(value, default):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = default
        return max(0.0, min(1.0, value))
