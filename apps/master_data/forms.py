"""Master data forms."""
from django import forms
from .models import AsetLv1, AsetLv2, KewajibanLv1, KewajibanLv2, EkuitasLv1, EkuitasLv2, TipeTransaksi


def _kode_nama_widgets():
    return {
        'kode': forms.TextInput(attrs={'class': 'form-control'}),
        'nama': forms.TextInput(attrs={'class': 'form-control'}),
    }


class AsetLv1Form(forms.ModelForm):
    class Meta:
        model = AsetLv1
        fields = ('kode', 'nama')
        widgets = _kode_nama_widgets()


class AsetLv2Form(forms.ModelForm):
    class Meta:
        model = AsetLv2
        fields = ('kode', 'nama')
        widgets = _kode_nama_widgets()


class KewajibanLv1Form(forms.ModelForm):
    class Meta:
        model = KewajibanLv1
        fields = ('kode', 'nama')
        widgets = _kode_nama_widgets()


class KewajibanLv2Form(forms.ModelForm):
    class Meta:
        model = KewajibanLv2
        fields = ('kode', 'nama')
        widgets = _kode_nama_widgets()


class EkuitasLv1Form(forms.ModelForm):
    class Meta:
        model = EkuitasLv1
        fields = ('kode', 'nama')
        widgets = _kode_nama_widgets()


class EkuitasLv2Form(forms.ModelForm):
    class Meta:
        model = EkuitasLv2
        fields = ('kode', 'nama')
        widgets = _kode_nama_widgets()


class TipeTransaksiForm(forms.ModelForm):
    class Meta:
        model = TipeTransaksi
        fields = ('kode_transaksi', 'nama')
        widgets = {
            'kode_transaksi': forms.TextInput(attrs={'class': 'form-control'}),
            'nama': forms.TextInput(attrs={'class': 'form-control'}),
        }
