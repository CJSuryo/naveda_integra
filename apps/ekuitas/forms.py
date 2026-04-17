"""Ekuitas forms."""
from django import forms

from .models import Pemilik


class PemilikForm(forms.ModelForm):
    class Meta:
        model = Pemilik
        fields = ('nama', 'keterangan')
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

