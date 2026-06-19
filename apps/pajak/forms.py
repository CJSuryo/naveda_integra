from django import forms

from .models import PajakTransaksi, TarifPajak, JENIS_PAJAK_CHOICES


class OverridePajakForm(forms.Form):
    jumlah_baru = forms.DecimalField(
        label='Jumlah Pajak Baru',
        max_digits=19,
        decimal_places=4,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001', 'min': '0'}),
    )


class TarifPajakForm(forms.ModelForm):
    class Meta:
        model = TarifPajak
        fields = [
            'jenis_pajak', 'nama', 'tarif_persen', 'faktor_dpp',
            'berlaku_mulai', 'berlaku_sampai', 'keterangan',
        ]
        widgets = {
            'jenis_pajak': forms.Select(attrs={'class': 'ni-input'}),
            'nama': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Nama tarif pajak'}),
            'tarif_persen': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001', 'min': '0'}),
            'faktor_dpp': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.000001', 'min': '0'}),
            'berlaku_mulai': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'berlaku_sampai': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['berlaku_sampai'].required = False
        self.fields['keterangan'].required = False
