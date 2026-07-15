from django import forms

from .models import UnitOfMeasure


class UnitOfMeasureForm(forms.ModelForm):
    class Meta:
        model = UnitOfMeasure
        fields = ['kode', 'nama', 'dimension', 'factor_to_base', 'is_base', 'is_active']

    def clean(self):
        cleaned = super().clean()
        # Guard: cannot edit kode of a system unit
        if self.instance.pk and self.instance.is_system:
            cleaned['kode'] = self.instance.kode
        return cleaned
