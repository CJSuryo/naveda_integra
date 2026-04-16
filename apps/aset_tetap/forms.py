"""Aset Tetap forms."""
from django import forms

from apps.entitas_bisnis.models import EntitasBisnis
from apps.purchase.models import ItemMasterPurchase

from .models import AsetTetapRecord


class AsetTetapRecordForm(forms.ModelForm):
    class Meta:
        model = AsetTetapRecord
        fields = (
            'item', 'entitas_bisnis', 'quantity', 'harga_perolehan',
            'tanggal_perolehan', 'masa_manfaat', 'metode_penyusutan',
            'akumulasi_penyusutan', 'nilai_residu', 'estimasi_jam_kerja',
            'estimasi_unit_produksi', 'lokasi', 'kondisi', 'keterangan',
        )
        widgets = {
            'item': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'quantity': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'harga_perolehan': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'tanggal_perolehan': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'masa_manfaat': forms.NumberInput(attrs={'class': 'ni-input'}),
            'metode_penyusutan': forms.Select(attrs={'class': 'ni-input'}),
            'akumulasi_penyusutan': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'nilai_residu': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'estimasi_jam_kerja': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
            'estimasi_unit_produksi': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
            'lokasi': forms.TextInput(attrs={'class': 'ni-input'}),
            'kondisi': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMasterPurchase.objects.filter(
            tipe_item='ATP',
        ).order_by('item_id')
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            status_aktif=True,
        ).order_by('nama')
        self.fields['masa_manfaat'].required = False
        self.fields['metode_penyusutan'].required = False
        self.fields['nilai_residu'].required = False
        self.fields['estimasi_jam_kerja'].required = False
        self.fields['estimasi_unit_produksi'].required = False
        self.fields['lokasi'].required = False
        self.fields['keterangan'].required = False
