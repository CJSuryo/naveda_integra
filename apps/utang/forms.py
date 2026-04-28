from django import forms

from apps.master_data.models import Akun
from .models import UtangHeader, UtangPembayaran


class UtangHeaderForm(forms.ModelForm):
    class Meta:
        model = UtangHeader
        fields = ['tanggal', 'entitas_bisnis', 'coa_utang_account', 'total_amount', 'deskripsi']
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'coa_utang_account': forms.Select(attrs={'class': 'ni-input'}),
            'total_amount': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
            'deskripsi': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['entitas_bisnis'].required = False
        self.fields['deskripsi'].required = False


class UtangPembayaranForm(forms.ModelForm):
    class Meta:
        model = UtangPembayaran
        fields = ['utang_detail', 'tanggal', 'coa_account', 'jumlah', 'keterangan']
        widgets = {
            'utang_detail': forms.Select(attrs={'class': 'ni-input'}),
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'coa_account': forms.Select(attrs={'class': 'ni-input'}),
            'jumlah': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
        }
