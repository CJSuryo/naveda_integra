from django import forms
from django.forms import inlineformset_factory, modelformset_factory

from apps.master_data.models import Akun
from apps.master_data.utils import akun_sorted_queryset

from .models import (
    PiutangAttachment, PiutangDetail, PiutangHeader, PiutangPenerimaan,
    PenyisihanRateConfig,
)


class PiutangHeaderForm(forms.ModelForm):
    class Meta:
        model = PiutangHeader
        fields = [
            'tanggal', 'debitur', 'deskripsi', 'jatuh_tempo',
            'jenis_jangka_waktu', 'coa_piutang_account',
            'jenis_bunga', 'suku_bunga', 'periode_angsuran',
            'is_approval_required',
            'pv_discount_rate', 'interest_income_account',
            'coa_piutang_lancar_account',
        ]
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'debitur': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Nama debitur'}),
            'deskripsi': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
            'jatuh_tempo': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'jenis_jangka_waktu': forms.Select(attrs={'class': 'ni-input', 'id': 'id_jenis_jangka_waktu'}),
            'coa_piutang_account': forms.Select(attrs={'class': 'ni-input'}),
            'jenis_bunga': forms.Select(attrs={'class': 'ni-input', 'id': 'id_jenis_bunga'}),
            'suku_bunga': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0'}),
            'periode_angsuran': forms.Select(attrs={'class': 'ni-input'}),
            'is_approval_required': forms.CheckboxInput(attrs={'class': 'ni-checkbox'}),
            'pv_discount_rate': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0'}),
            'interest_income_account': forms.Select(attrs={'class': 'ni-input'}),
            'coa_piutang_lancar_account': forms.Select(attrs={'class': 'ni-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deskripsi'].required = False
        self.fields['jatuh_tempo'].required = False
        self.fields['suku_bunga'].required = False
        self.fields['pv_discount_rate'].required = False
        self.fields['interest_income_account'].required = False
        self.fields['coa_piutang_lancar_account'].required = False
        self.fields['coa_piutang_account'].queryset = akun_sorted_queryset({'kategori_id': 'aset'})
        self.fields['coa_piutang_account'].empty_label = '— Pilih Akun Piutang —'
        self.fields['interest_income_account'].queryset = akun_sorted_queryset({'kategori_id': 'pendapatan'})
        self.fields['interest_income_account'].empty_label = '— Pilih Akun Pendapatan Bunga Efektif —'
        self.fields['coa_piutang_lancar_account'].queryset = akun_sorted_queryset({'kategori_id': 'aset'})
        self.fields['coa_piutang_lancar_account'].empty_label = '— Pilih Akun Piutang Bagian Lancar —'


class PiutangDetailForm(forms.ModelForm):
    class Meta:
        model = PiutangDetail
        fields = ['deskripsi', 'jumlah', 'revenue_account']
        widgets = {
            'deskripsi': forms.TextInput(attrs={'class': 'ni-input ni-input--sm', 'placeholder': 'Keterangan'}),
            'jumlah': forms.NumberInput(attrs={'class': 'ni-input ni-input--sm amount-field', 'step': '0.01', 'min': '0.01'}),
            'revenue_account': forms.Select(attrs={'class': 'ni-input ni-input--sm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['revenue_account'].required = False
        self.fields['revenue_account'].queryset = akun_sorted_queryset()
        self.fields['revenue_account'].empty_label = '— Akun Pendapatan (opsional) —'


PiutangDetailFormSet = inlineformset_factory(
    PiutangHeader, PiutangDetail,
    form=PiutangDetailForm,
    fields=['deskripsi', 'jumlah', 'revenue_account'],
    extra=1, min_num=1, validate_min=True, can_delete=True,
)


class PiutangPenerimaanForm(forms.ModelForm):
    class Meta:
        model = PiutangPenerimaan
        fields = ['tanggal_terima', 'jumlah_diterima', 'payment_account',
                  'metode_penerimaan', 'nomor_referensi', 'catatan']
        widgets = {
            'tanggal_terima': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'jumlah_diterima': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0.01'}),
            'payment_account': forms.Select(attrs={'class': 'ni-input'}),
            'metode_penerimaan': forms.Select(attrs={'class': 'ni-input'}),
            'nomor_referensi': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'No. transfer / cek'}),
            'catatan': forms.TextInput(attrs={'class': 'ni-input'}),
        }

    def __init__(self, *args, piutang_header=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nomor_referensi'].required = False
        self.fields['catatan'].required = False
        self.fields['payment_account'].queryset = akun_sorted_queryset({'kategori_id': 'aset'})
        self.fields['payment_account'].empty_label = '— Pilih Akun Kas/Bank —'


class PiutangAttachmentForm(forms.ModelForm):
    class Meta:
        model = PiutangAttachment
        fields = ['file', 'file_name', 'jenis_dokumen']
        widgets = {
            'file_name': forms.TextInput(attrs={'class': 'ni-input'}),
            'jenis_dokumen': forms.Select(attrs={'class': 'ni-input'}),
        }


class PiutangWriteOffForm(forms.Form):
    tanggal = forms.DateField(widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}))
    metode = forms.ChoiceField(
        choices=[('langsung', 'Langsung'), ('cadangan', 'Cadangan Kerugian')],
        widget=forms.Select(attrs={'class': 'ni-input'}),
    )
    bad_debt_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Beban Piutang Tak Tertagih',
    )
    allowance_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(), required=False,
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Cadangan Kerugian Piutang',
    )
    alasan = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['bad_debt_account'].queryset = akun_sorted_queryset()
        self.fields['allowance_account'].queryset = akun_sorted_queryset()


class PiutangReklasifikasiForm(forms.Form):
    tanggal = forms.DateField(widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}))
    dari_akun = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Dari Akun',
    )
    ke_akun = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Ke Akun',
    )
    jumlah = forms.DecimalField(
        max_digits=19, decimal_places=4,
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
    )
    keterangan = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'ni-input'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dari_akun'].queryset = akun_sorted_queryset()
        self.fields['ke_akun'].queryset = akun_sorted_queryset()


class PiutangPenyisihanForm(forms.Form):
    tanggal = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
        label='Tanggal',
    )
    allowance_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Cadangan Kerugian Piutang',
        empty_label='— Pilih Akun Cadangan —',
    )
    expense_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Beban Penyisihan',
        empty_label='— Pilih Akun Beban —',
    )
    catatan = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Catatan (opsional)'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['allowance_account'].queryset = akun_sorted_queryset({'kategori_id': 'aset'})
        self.fields['expense_account'].queryset = akun_sorted_queryset({'kategori_id': 'beban'})


class BatchPenyisihanForm(forms.Form):
    tanggal = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
        label='Tanggal Perhitungan',
    )
    allowance_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Cadangan Kerugian Piutang',
        empty_label='— Pilih Akun Cadangan —',
    )
    expense_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Beban Penyisihan',
        empty_label='— Pilih Akun Beban —',
    )
    catatan = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Catatan (opsional)'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['allowance_account'].queryset = akun_sorted_queryset({'kategori_id': 'aset'})
        self.fields['expense_account'].queryset = akun_sorted_queryset({'kategori_id': 'beban'})


PenyisihanRateConfigFormSet = modelformset_factory(
    PenyisihanRateConfig,
    fields=['rate_percent'],
    extra=0,
    widgets={
        'rate_percent': forms.NumberInput(attrs={
            'class': 'ni-input ni-input--sm', 'step': '0.01', 'min': '0', 'max': '100',
        }),
    },
)


class PvAdjustmentForm(forms.Form):
    tanggal = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
        label='Tanggal Jurnal',
    )
    interest_income_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Pendapatan Bunga Efektif',
        empty_label='— Pilih Akun —',
    )
    catatan = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'ni-input'}),
        label='Catatan',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['interest_income_account'].queryset = akun_sorted_queryset({'kategori_id': 'pendapatan'})


class PvAccrualForm(forms.Form):
    tanggal = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
        label='Tanggal Akrual (Akhir Periode)',
    )
    catatan = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'ni-input'}),
        label='Catatan',
    )
