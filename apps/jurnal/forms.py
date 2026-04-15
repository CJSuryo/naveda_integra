"""Jurnal forms."""
from django import forms
from .models import (
    Item, TransactionPrefix,
    JurnalHeader, JurnalDetail,
    JurnalAutomasi, JurnalAutomasiAkun,
)
from apps.master_data.models import Akun
from apps.master_data.utils import natural_sort_key


def _kode_nama_widgets():
    return {
        'kode': forms.TextInput(attrs={'class': 'ni-input'}),
        'nama': forms.TextInput(attrs={'class': 'ni-input'}),
    }


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ('kode', 'nama')
        widgets = _kode_nama_widgets()


class TransactionPrefixForm(forms.ModelForm):
    class Meta:
        model = TransactionPrefix
        fields = ('kode', 'nama')
        widgets = _kode_nama_widgets()


class JurnalHeaderForm(forms.ModelForm):
    class Meta:
        model = JurnalHeader
        fields = (
            'tanggal', 'nomor_transaksi', 'uraian_transaksi',
            'entitas_bisnis', 'tipe_transaksi', 'item', 'transaction_prefix',
        )
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'nomor_transaksi': forms.TextInput(attrs={'class': 'ni-input'}),
            'uraian_transaksi': forms.TextInput(attrs={'class': 'ni-input'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'tipe_transaksi': forms.Select(attrs={'class': 'ni-input'}),
            'item': forms.Select(attrs={'class': 'ni-input'}),
            'transaction_prefix': forms.Select(attrs={'class': 'ni-input'}),
        }


class JurnalDetailForm(forms.ModelForm):
    class Meta:
        model = JurnalDetail
        fields = ('akun', 'debit', 'kredit')
        widgets = {
            'akun': forms.Select(attrs={'class': 'ni-input'}),
            'debit': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
            'kredit': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['akun'].choices = [('', '---------')] + [
            (a.pk, str(a)) for a in sorted(Akun.objects.all(), key=lambda a: natural_sort_key(a.kode_akun))
        ]


class JurnalAutomasiForm(forms.ModelForm):
    class Meta:
        model = JurnalAutomasi
        fields = ('nama',)
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
        }


class JurnalAutomasiAkunForm(forms.ModelForm):
    class Meta:
        model = JurnalAutomasiAkun
        fields = ('akun',)
        widgets = {
            'akun': forms.Select(attrs={'class': 'ni-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['akun'].choices = [('', '---------')] + [
            (a.pk, str(a)) for a in sorted(Akun.objects.all(), key=lambda a: natural_sort_key(a.kode_akun))
        ]


class AutomasiEntryForm(forms.Form):
    """Form for creating automated journal entries."""
    tanggal = forms.DateField(widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}))
    uraian_transaksi = forms.CharField(
        max_length=512,
        widget=forms.TextInput(attrs={'class': 'ni-input'}),
    )
    item = forms.ModelChoiceField(
        queryset=Item.objects.all(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
    )
    transaction_prefix = forms.ModelChoiceField(
        queryset=TransactionPrefix.objects.all(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
    )
