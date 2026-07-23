"""Aset Tetap forms."""
from decimal import Decimal

from django import forms

from apps.entitas_bisnis.models import EntitasBisnis
from apps.master_data.models import Akun
from apps.purchase.models import ItemMasterPurchase

from .models import AsetTetapRecord, AssetDisposal


class AsetTetapRecordForm(forms.ModelForm):
    class Meta:
        model = AsetTetapRecord
        fields = (
            'item', 'entitas_bisnis', 'quantity', 'harga_perolehan',
            'tanggal_perolehan', 'masa_manfaat', 'metode_penyusutan',
            'akumulasi_penyusutan', 'nilai_residu', 'estimasi_jam_kerja',
            'estimasi_unit_produksi', 'lokasi_legacy', 'kondisi', 'keterangan',
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
            'lokasi_legacy': forms.TextInput(attrs={'class': 'ni-input'}),
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
        self.fields['lokasi_legacy'].required = False
        self.fields['keterangan'].required = False


class AssetDisposalForm(forms.ModelForm):
    class Meta:
        model = AssetDisposal
        fields = ('jenis', 'tanggal', 'quantity', 'harga_jual', 'akun_kas', 'akun_laba_rugi', 'keterangan')
        widgets = {
            'jenis': forms.Select(attrs={'class': 'ni-input'}),
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'quantity': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'harga_jual': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'akun_kas': forms.Select(attrs={'class': 'ni-input'}),
            'akun_laba_rugi': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, aset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.aset = aset
        self.fields['akun_kas'].queryset = Akun.objects.all().order_by('kode_akun')
        self.fields['akun_laba_rugi'].queryset = Akun.objects.all().order_by('kode_akun')
        self.fields['akun_kas'].required = False
        self.fields['harga_jual'].required = False
        self.fields['keterangan'].required = False

    def clean(self):
        cleaned = super().clean()
        jenis = cleaned.get('jenis')
        qty = cleaned.get('quantity')
        harga = cleaned.get('harga_jual') or Decimal('0')

        if harga < 0:
            self.add_error('harga_jual', 'Harga jual tidak boleh negatif.')

        if qty is not None and qty <= 0:
            self.add_error('quantity', 'Quantity harus lebih dari 0.')
        elif self.aset is not None and qty is not None and qty > self.aset.quantity:
            self.add_error('quantity', f'Melebihi sisa quantity aset ({self.aset.quantity}).')

        if jenis != 'jual':
            cleaned['harga_jual'] = Decimal('0')
            cleaned['akun_kas'] = None
        elif harga > 0 and not cleaned.get('akun_kas'):
            self.add_error('akun_kas', 'Akun Kas/Piutang wajib untuk pelepasan jenis jual.')

        return cleaned
