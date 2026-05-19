from django import forms

from apps.entitas_bisnis.models import EntitasBisnis
from apps.master_data.models import Akun

from .models import UtangDetail, UtangHeader, UtangPembayaran


class UtangHeaderForm(forms.ModelForm):
    class Meta:
        model = UtangHeader
        fields = ['tanggal', 'entitas_bisnis', 'total_amount', 'deskripsi']
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'total_amount': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
            'deskripsi': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['entitas_bisnis'].required = False
        self.fields['deskripsi'].required = False
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            relasi__in=['pemasok', 'keduanya'],
            status_aktif=True,
        )


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

    def __init__(self, *args, utang_header=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['utang_detail'].required = False
        self.fields['coa_account'].queryset = Akun.objects.filter(kategori_id='aset')
        if utang_header is not None:
            self.fields['utang_detail'].queryset = UtangDetail.objects.filter(
                utang_header=utang_header,
            )
        else:
            self.fields['utang_detail'].queryset = UtangDetail.objects.none()
