from django import forms
from django.forms import inlineformset_factory

from apps.master_data.models import Akun
from apps.master_data.utils import akun_sorted_queryset

from .models import UtangAttachment, UtangDetail, UtangHeader, UtangPembayaran


class UtangHeaderForm(forms.ModelForm):
    class Meta:
        model = UtangHeader
        fields = [
            'tanggal', 'jenis_utang', 'kreditor',
            'nomor_referensi', 'kategori_jangka_waktu',
            'coa_source_account', 'requires_approval',
            'tanggal_jatuh_tempo', 'deskripsi',
            'jenis_bunga', 'suku_bunga', 'periode_angsuran',
        ]
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'jenis_utang': forms.Select(attrs={'class': 'ni-input', 'id': 'id_jenis_utang'}),
            'kreditor': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Nama kreditor/pihak yang memberi utang'}),
            'nomor_referensi': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Misal: PK-2026-001, INV-001'}),
            'kategori_jangka_waktu': forms.Select(attrs={'class': 'ni-input', 'id': 'id_kategori_jangka_waktu'}),
            'coa_source_account': forms.Select(attrs={'class': 'ni-input'}),
            'requires_approval': forms.CheckboxInput(attrs={'class': 'ni-checkbox', 'id': 'id_requires_approval'}),
            'tanggal_jatuh_tempo': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'deskripsi': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
            'jenis_bunga': forms.Select(attrs={'class': 'ni-input', 'id': 'id_jenis_bunga'}),
            'suku_bunga': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001', 'min': '0', 'id': 'id_suku_bunga'}),
            'periode_angsuran': forms.Select(attrs={'class': 'ni-input', 'id': 'id_periode_angsuran'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kreditor'].required = False
        self.fields['deskripsi'].required = False
        self.fields['nomor_referensi'].required = False
        self.fields['tanggal_jatuh_tempo'].required = False
        self.fields['coa_source_account'].required = False
        self.fields['coa_source_account'].queryset = akun_sorted_queryset()
        self.fields['coa_source_account'].empty_label = '— Pilih Akun Asal (opsional) —'
        self.fields['suku_bunga'].required = False


class UtangDetailForm(forms.ModelForm):
    class Meta:
        model = UtangDetail
        fields = ['coa_utang_account', 'description', 'amount']
        widgets = {
            'coa_utang_account': forms.Select(attrs={'class': 'ni-input ni-input--sm'}),
            'description': forms.TextInput(attrs={'class': 'ni-input ni-input--sm', 'placeholder': 'Keterangan'}),
            'amount': forms.NumberInput(attrs={'class': 'ni-input ni-input--sm amount-field', 'step': '0.01', 'min': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False
        self.fields['coa_utang_account'].queryset = akun_sorted_queryset({'kategori_id': 'kewajiban'})


UtangDetailFormSet = inlineformset_factory(
    UtangHeader,
    UtangDetail,
    form=UtangDetailForm,
    fields=['coa_utang_account', 'description', 'amount'],
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class UtangPembayaranForm(forms.ModelForm):
    class Meta:
        model = UtangPembayaran
        fields = ['utang_detail', 'tanggal', 'coa_account', 'jumlah', 'keterangan', 'angsuran_no']
        widgets = {
            'utang_detail': forms.Select(attrs={'class': 'ni-input'}),
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'coa_account': forms.Select(attrs={'class': 'ni-input'}),
            'jumlah': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
            'angsuran_no': forms.HiddenInput(),
        }

    def __init__(self, *args, utang_header=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['utang_detail'].required = False
        self.fields['angsuran_no'].required = False
        self.fields['coa_account'].queryset = akun_sorted_queryset({'kategori_id': 'aset'})
        if utang_header is not None:
            self.fields['utang_detail'].queryset = UtangDetail.objects.filter(utang_header=utang_header)
        else:
            self.fields['utang_detail'].queryset = UtangDetail.objects.none()


class UtangAttachmentForm(forms.ModelForm):
    class Meta:
        model = UtangAttachment
        fields = ['file', 'jenis_dokumen']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'ni-input'}),
            'jenis_dokumen': forms.Select(attrs={'class': 'ni-input'}),
        }
