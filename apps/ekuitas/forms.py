"""Ekuitas forms."""
from django import forms

from apps.entitas_bisnis.models import EntitasBisnis

from .models import ModalDisetor


class ModalDisetorForm(forms.ModelForm):
    class Meta:
        model = ModalDisetor
        fields = (
            'entitas_bisnis', 'nama_pemilik', 'jumlah_modal',
            'persentase_kepemilikan', 'tanggal_setor', 'keterangan',
        )
        widgets = {
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'nama_pemilik': forms.TextInput(attrs={'class': 'ni-input'}),
            'jumlah_modal': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'persentase_kepemilikan': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'tanggal_setor': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            status_aktif=True,
        ).order_by('nama')
        self.fields['keterangan'].required = False
