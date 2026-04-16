"""Aset Lainnya forms."""
from django import forms

from apps.entitas_bisnis.models import EntitasBisnis
from apps.purchase.models import ItemMasterPurchase

from .models import AsetLainnyaRecord


class AsetLainnyaRecordForm(forms.ModelForm):
    class Meta:
        model = AsetLainnyaRecord
        fields = (
            'item', 'entitas_bisnis', 'quantity', 'harga_perolehan',
            'tanggal_perolehan', 'masa_manfaat', 'metode_amortisasi',
            'akumulasi_amortisasi', 'nilai_residu', 'estimasi_unit_produksi',
            'keterangan',
        )
        widgets = {
            'item': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'quantity': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'harga_perolehan': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'tanggal_perolehan': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'masa_manfaat': forms.NumberInput(attrs={'class': 'ni-input'}),
            'metode_amortisasi': forms.Select(attrs={'class': 'ni-input'}),
            'akumulasi_amortisasi': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'nilai_residu': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'estimasi_unit_produksi': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMasterPurchase.objects.filter(
            tipe_item='ALL',
        ).order_by('item_id')
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            status_aktif=True,
        ).order_by('nama')
        self.fields['masa_manfaat'].required = False
        self.fields['metode_amortisasi'].required = False
        self.fields['nilai_residu'].required = False
        self.fields['estimasi_unit_produksi'].required = False
        self.fields['keterangan'].required = False
