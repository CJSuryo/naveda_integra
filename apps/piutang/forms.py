from django import forms
from django.forms import inlineformset_factory

from apps.master_data.models import Akun

from .models import PiutangAttachment, PiutangDetail, PiutangHeader, PiutangPenerimaan


class PiutangHeaderForm(forms.ModelForm):
    class Meta:
        model = PiutangHeader
        fields = [
            'tanggal', 'debitur', 'deskripsi', 'jatuh_tempo',
            'jenis_jangka_waktu', 'coa_piutang_account',
        ]
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'debitur': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Nama debitur'}),
            'deskripsi': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
            'jatuh_tempo': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'jenis_jangka_waktu': forms.Select(attrs={'class': 'ni-input'}),
            'coa_piutang_account': forms.Select(attrs={'class': 'ni-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deskripsi'].required = False
        self.fields['jatuh_tempo'].required = False
        self.fields['coa_piutang_account'].queryset = Akun.objects.filter(
            kategori_id='aset'
        ).order_by('kode_akun')
        self.fields['coa_piutang_account'].empty_label = '— Pilih Akun Piutang —'


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
        self.fields['revenue_account'].queryset = Akun.objects.all().order_by('kode_akun')
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
        self.fields['payment_account'].queryset = Akun.objects.filter(
            kategori_id='aset'
        ).order_by('kode_akun')
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
        queryset=Akun.objects.all(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Beban Piutang Tak Tertagih',
    )
    allowance_account = forms.ModelChoiceField(
        queryset=Akun.objects.all(), required=False,
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Cadangan Kerugian Piutang',
    )
    alasan = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
    )


class PiutangReklasifikasiForm(forms.Form):
    tanggal = forms.DateField(widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}))
    dari_akun = forms.ModelChoiceField(
        queryset=Akun.objects.all(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Dari Akun',
    )
    ke_akun = forms.ModelChoiceField(
        queryset=Akun.objects.all(),
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
