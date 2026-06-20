from django import forms
from django.forms import inlineformset_factory, modelformset_factory

from apps.master_data.models import Akun
from apps.master_data.utils import akun_sorted_queryset

from .models import (
    PiutangAttachment, PiutangDetail, PiutangHeader, PiutangPenerimaan,
    PenyisihanRateConfig,
    STANDAR_AKUNTANSI_CHOICES, KATEGORI_PENGUKURAN_CHOICES, ECL_STAGE_CHOICES,
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
            # PSAK/SAK fields
            'standar_akuntansi', 'kategori_pengukuran', 'business_model',
            'sppi_test_passed', 'biaya_transaksi', 'biaya_transaksi_account',
            'agunan_jenis', 'agunan_nilai',
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
            'standar_akuntansi': forms.Select(attrs={'class': 'ni-input', 'id': 'id_standar_akuntansi'}),
            'kategori_pengukuran': forms.HiddenInput(attrs={'id': 'id_kategori_pengukuran'}),
            'business_model': forms.HiddenInput(attrs={'id': 'id_business_model'}),
            'sppi_test_passed': forms.HiddenInput(attrs={'id': 'id_sppi_test_passed'}),
            'biaya_transaksi': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0'}),
            'biaya_transaksi_account': forms.Select(attrs={'class': 'ni-input'}),
            'agunan_jenis': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'mis. Tanah, Bangunan, Deposito'}),
            'agunan_nilai': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deskripsi'].required = False
        self.fields['jatuh_tempo'].required = False
        self.fields['suku_bunga'].required = False
        self.fields['pv_discount_rate'].required = False
        self.fields['interest_income_account'].required = False
        self.fields['coa_piutang_lancar_account'].required = False
        self.fields['standar_akuntansi'].required = False
        self.fields['standar_akuntansi'].empty_label = '— Ikuti standar entitas bisnis —'
        self.fields['kategori_pengukuran'].required = False
        self.fields['business_model'].required = False
        self.fields['sppi_test_passed'].required = False
        self.fields['biaya_transaksi'].required = False
        self.fields['biaya_transaksi_account'].required = False
        self.fields['agunan_jenis'].required = False
        self.fields['agunan_nilai'].required = False
        self.fields['coa_piutang_account'].queryset = akun_sorted_queryset({'kode_akun__startswith': '1'})
        self.fields['coa_piutang_account'].empty_label = '— Pilih Akun Piutang —'
        self.fields['interest_income_account'].queryset = akun_sorted_queryset({'kode_akun__startswith': '4'})
        self.fields['interest_income_account'].empty_label = '— Pilih Akun Pendapatan Bunga Efektif —'
        self.fields['coa_piutang_lancar_account'].queryset = akun_sorted_queryset({'kode_akun__startswith': '1'})
        self.fields['coa_piutang_lancar_account'].empty_label = '— Pilih Akun Piutang Bagian Lancar —'
        self.fields['biaya_transaksi_account'].queryset = akun_sorted_queryset()
        self.fields['biaya_transaksi_account'].empty_label = '— Pilih Akun Biaya Transaksi —'


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
        self.fields['revenue_account'].queryset = akun_sorted_queryset({'kode_akun__startswith': '4'})
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
        empty_label='— Gunakan akun dari piutang —',
        required=False,
    )
    catatan = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'ni-input'}),
        label='Catatan',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['interest_income_account'].queryset = akun_sorted_queryset({'kode_akun__startswith': '4'})


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


class ECLStageUpdateForm(forms.Form):
    new_stage = forms.ChoiceField(
        choices=ECL_STAGE_CHOICES,
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Stage ECL Baru',
    )
    alasan = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
        label='Alasan Perubahan',
    )


class ECLGeneralApproachForm(forms.Form):
    tanggal = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
        label='Tanggal Penyisihan',
    )
    pd_rate = forms.DecimalField(
        max_digits=7, decimal_places=4,
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001', 'min': '0', 'max': '100'}),
        label='PD Rate (%) per tahun',
        help_text='Probability of Default dalam persen. Mis: 2.5 untuk 2,5%.',
    )
    lgd_rate = forms.DecimalField(
        max_digits=7, decimal_places=4,
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001', 'min': '0', 'max': '100'}),
        label='LGD Rate (%) ',
        help_text='Loss Given Default dalam persen. Mis: 45 untuk 45%.',
    )
    forward_looking_adj = forms.DecimalField(
        max_digits=7, decimal_places=4,
        initial='1.0000',
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001', 'min': '0'}),
        label='Forward-Looking Adjustment',
        help_text='Faktor penyesuaian makro-ekonomi. Default 1.0 (tanpa penyesuaian).',
    )
    allowance_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Cadangan ECL',
        empty_label='— Pilih Akun Cadangan —',
    )
    expense_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Beban ECL',
        empty_label='— Pilih Akun Beban —',
    )
    catatan = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'ni-input'}),
        label='Catatan',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['allowance_account'].queryset = akun_sorted_queryset({'kategori_id': 'aset'})
        self.fields['expense_account'].queryset = akun_sorted_queryset({'kategori_id': 'beban'})


class PiutangModifikasiForm(forms.Form):
    tanggal = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
        label='Tanggal Modifikasi',
    )
    deskripsi_perubahan = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
        label='Deskripsi Perubahan Syarat',
    )
    new_cashflows_json = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'ni-input', 'rows': 5, 'placeholder':
            '[{"tanggal": "2027-01-01", "jumlah": 5000000}, ...]',
        }),
        label='Arus Kas Baru (JSON)',
        help_text='Array JSON dengan field "tanggal" (YYYY-MM-DD) dan "jumlah".',
    )
    gain_loss_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Laba/Rugi Modifikasi',
        empty_label='— Pilih Akun —',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['gain_loss_account'].queryset = akun_sorted_queryset()


class PiutangPemulihanForm(forms.Form):
    tanggal = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
        label='Tanggal Pemulihan',
    )
    jumlah = forms.DecimalField(
        max_digits=19, decimal_places=4,
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0.01'}),
        label='Jumlah Dipulihkan',
    )
    kas_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Kas/Bank',
        empty_label='— Pilih Akun Kas/Bank —',
    )
    recovery_income_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Pendapatan Pemulihan',
        empty_label='— Pilih Akun Pendapatan —',
    )
    catatan = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'ni-input'}),
        label='Catatan',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kas_account'].queryset = akun_sorted_queryset({'kategori_id': 'aset'})
        self.fields['recovery_income_account'].queryset = akun_sorted_queryset({'kode_akun__startswith': '4'})


class PiutangFactoringForm(forms.Form):
    HASIL_CHOICES = [
        ('derecognized', 'Diderecognize — risiko/manfaat sudah dialihkan penuh'),
        ('continuing', 'Continuing Involvement — risiko/manfaat tidak sepenuhnya dialihkan'),
        ('not_derecognized', 'Tidak Diderecognize — risiko/manfaat tetap pada entitas'),
    ]

    tanggal = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
        label='Tanggal Transaksi',
    )
    pihak_penerima = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Nama bank/lembaga penerima piutang'}),
        label='Pihak Penerima',
    )
    nilai_transfer = forms.DecimalField(
        max_digits=19, decimal_places=4,
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0.01'}),
        label='Nilai Transfer (Kas Diterima)',
    )
    hasil_analisis = forms.ChoiceField(
        choices=HASIL_CHOICES,
        widget=forms.Select(attrs={'class': 'ni-input', 'id': 'id_hasil_analisis'}),
        label='Hasil Analisis Risiko & Manfaat',
    )
    continuing_involvement_amount = forms.DecimalField(
        max_digits=19, decimal_places=4, required=False,
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0'}),
        label='Nilai Continuing Involvement',
        help_text='Isi jika hasil analisis adalah Continuing Involvement.',
    )
    gain_loss_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(), required=False,
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Akun Laba/Rugi Derecognition',
        empty_label='— Pilih Akun (jika diderecognize) —',
    )
    analisis_detail = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'ni-input', 'rows': 4}),
        label='Uraian Analisis',
        help_text='Dokumentasi analisis pemindahan risiko dan manfaat.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['gain_loss_account'].queryset = akun_sorted_queryset()
