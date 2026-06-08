"""Sales forms."""
from django import forms

from .models import SalesHeader, SalesItem


class SalesHeaderForm(forms.ModelForm):
    class Meta:
        model = SalesHeader
        fields = ('tanggal', 'entitas_bisnis', 'payment_account', 'payment_type', 'deskripsi')
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'payment_account': forms.Select(attrs={'class': 'ni-input'}),
            'payment_type': forms.Select(attrs={'class': 'ni-input', 'id': 'id_payment_type'}),
            'deskripsi': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }
