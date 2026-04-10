"""Jurnal forms."""
from django import forms
from .models import (
    Item, TransactionPrefix,
    JurnalHeader, JurnalDetail,
    JurnalAutomasi, JurnalAutomasiAkun,
)
from apps.master_data.models import Akun


def _kode_nama_widgets():
    return {
        'kode': forms.TextInput(attrs={'class': 'form-control'}),
        'nama': forms.TextInput(attrs={'class': 'form-control'}),
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
            'tanggal': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'nomor_transaksi': forms.TextInput(attrs={'class': 'form-control'}),
            'uraian_transaksi': forms.TextInput(attrs={'class': 'form-control'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'form-control'}),
            'tipe_transaksi': forms.Select(attrs={'class': 'form-control'}),
            'item': forms.Select(attrs={'class': 'form-control'}),
            'transaction_prefix': forms.Select(attrs={'class': 'form-control'}),
        }


class JurnalDetailForm(forms.ModelForm):
    class Meta:
        model = JurnalDetail
        fields = ('akun', 'debit', 'kredit')
        widgets = {
            'akun': forms.Select(attrs={'class': 'form-control'}),
            'debit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'kredit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['akun'].queryset = Akun.objects.all().order_by('kode_akun')


class JurnalAutomasiForm(forms.ModelForm):
    class Meta:
        model = JurnalAutomasi
        fields = ('nama',)
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'form-control'}),
        }


class JurnalAutomasiAkunForm(forms.ModelForm):
    class Meta:
        model = JurnalAutomasiAkun
        fields = ('akun',)
        widgets = {
            'akun': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['akun'].queryset = Akun.objects.all().order_by('kode_akun')


class AutomasiEntryForm(forms.Form):
    """Form for creating automated journal entries."""
    tanggal = forms.DateField(widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    uraian_transaksi = forms.CharField(
        max_length=512,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    item = forms.ModelChoiceField(
        queryset=Item.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    transaction_prefix = forms.ModelChoiceField(
        queryset=TransactionPrefix.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
