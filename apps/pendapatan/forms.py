from django import forms
from apps.master_data.models import Akun
from apps.master_data.utils import akun_sorted_queryset
from apps.purchase.models import SubTransactionType
from .models import (
    PendapatanHeader, RecurringTemplate, KewajibabPelaksanaan,
    KATEGORI_CHOICES, TAX_TYPE_CHOICES,
    JadwalPengakuan,
)


class PendapatanHeaderForm(forms.ModelForm):
    class Meta:
        model = PendapatanHeader
        fields = ['tanggal', 'deskripsi', 'payment_type', 'standar_akuntansi']
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}, format='%Y-%m-%d'),
            'deskripsi': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
            'payment_type': forms.Select(attrs={'class': 'ni-input', 'id': 'id_payment_type'}),
            'standar_akuntansi': forms.Select(attrs={'class': 'ni-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deskripsi'].required = False


class KewajibabPelaksanaanForm(forms.Form):
    deskripsi_item = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Deskripsi item'}),
    )
    kategori = forms.ChoiceField(
        choices=[('', '— Pilih Kategori —')] + list(KATEGORI_CHOICES),
        widget=forms.Select(attrs={'class': 'ni-input'}),
    )
    sub_transaction_type = forms.ModelChoiceField(
        queryset=SubTransactionType.objects.filter(module='pendapatan').order_by('nama'),
        widget=forms.Select(attrs={'class': 'ni-input stt-select'}),
        empty_label='— Pilih STT —',
    )
    nilai_kontrak = forms.DecimalField(
        max_digits=19, decimal_places=4,
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0.01'}),
        label='Nilai Kontrak',
    )
    revenue_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input revenue-account-field'}),
        empty_label='— Pilih Akun Pendapatan —',
    )
    payment_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        required=True,
        widget=forms.Select(attrs={'class': 'ni-input'}),
        empty_label='— Pilih Akun Kas/Bank —',
    )
    # PSAK 72 recognition fields
    recognition_type = forms.ChoiceField(
        choices=KewajibabPelaksanaan.RecognitionType.choices,
        initial=KewajibabPelaksanaan.RecognitionType.POINT_IN_TIME,
        widget=forms.Select(attrs={'class': 'ni-input recognition-type-select'}),
        label='Tipe Pengakuan',
    )
    # Over-time fields
    ot_tipe_aliran = forms.ChoiceField(
        choices=[('', '— Pilih Tipe Aliran —')] + list(JadwalPengakuan.TipeAliran.choices),
        required=False,
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Tipe Aliran',
    )
    ot_progress_method = forms.ChoiceField(
        choices=[('', '— Pilih Metode —')] + list(JadwalPengakuan.ProgressMethod.choices),
        required=False,
        widget=forms.Select(attrs={'class': 'ni-input'}),
        label='Metode Progress',
    )
    ot_tanggal_mulai = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
        label='Tanggal Mulai OT',
    )
    ot_tanggal_selesai = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
        label='Tanggal Selesai OT',
    )
    ot_liabilitas_kontrak_acct = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'ni-input'}),
        empty_label='— Pilih Akun Liabilitas Kontrak —',
        label='Akun Liabilitas Kontrak',
    )
    ot_aset_kontrak_acct = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'ni-input'}),
        empty_label='— Pilih Akun Aset Kontrak —',
        label='Akun Aset Kontrak',
    )
    ot_biaya_estimasi_total = forms.DecimalField(
        max_digits=19, decimal_places=4, required=False,
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
        label='Biaya Estimasi Total',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs_all = akun_sorted_queryset()
        self.fields['revenue_account'].queryset = qs_all
        self.fields['payment_account'].queryset = akun_sorted_queryset({'kategori_id': 'aset'})
        self.fields['ot_liabilitas_kontrak_acct'].queryset = qs_all
        self.fields['ot_aset_kontrak_acct'].queryset = qs_all

    def clean(self):
        cleaned_data = super().clean()
        recognition_type = cleaned_data.get('recognition_type')

        if recognition_type == KewajibabPelaksanaan.RecognitionType.OVER_TIME:
            required_ot = ['ot_tipe_aliran', 'ot_progress_method', 'ot_tanggal_mulai', 'ot_tanggal_selesai']
            for field in required_ot:
                if not cleaned_data.get(field):
                    self.add_error(field, 'Field ini wajib diisi untuk pengakuan Over Time.')

            tipe_aliran = cleaned_data.get('ot_tipe_aliran')
            if tipe_aliran == JadwalPengakuan.TipeAliran.ADVANCE_PAYMENT_CASH:
                if not cleaned_data.get('ot_liabilitas_kontrak_acct'):
                    self.add_error(
                        'ot_liabilitas_kontrak_acct',
                        'Akun Liabilitas Kontrak wajib diisi untuk tipe aliran Advance Payment.',
                    )
            elif tipe_aliran == JadwalPengakuan.TipeAliran.PERFORMANCE_FIRST:
                if not cleaned_data.get('ot_aset_kontrak_acct'):
                    self.add_error(
                        'ot_aset_kontrak_acct',
                        'Akun Aset Kontrak wajib diisi untuk tipe aliran Performance First.',
                    )

        return cleaned_data


class KPTaxLineForm(forms.Form):
    """Validates a single tax line for a KP."""
    tax_type = forms.ChoiceField(
        choices=TAX_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'ni-input kp-tax-type-sel'}),
        label='Tipe Pajak',
    )
    tax = forms.DecimalField(
        max_digits=19, decimal_places=4, required=False,
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
        label='Pajak (Nominal Override)',
    )
    tax_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        empty_label='— Pilih Akun Pajak —',
        label='Akun Pajak',
    )
    tax_payment_account = forms.ModelChoiceField(
        queryset=Akun.objects.none(),
        widget=forms.Select(attrs={'class': 'ni-input'}),
        empty_label='— Pilih Akun Lawan —',
        label='Akun Lawan Pajak',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs_all = akun_sorted_queryset()
        self.fields['tax_account'].queryset = qs_all
        self.fields['tax_payment_account'].queryset = qs_all


# Backward-compat alias
PendapatanItemForm = KewajibabPelaksanaanForm


class RecurringTemplateForm(forms.ModelForm):
    class Meta:
        model = RecurringTemplate
        fields = [
            'nama', 'entitas_bisnis', 'entitas_bisnis_lv2', 'entitas_bisnis_lv3',
            'deskripsi_item', 'kategori', 'sub_transaction_type', 'jumlah',
            'revenue_account', 'payment_account', 'payment_type',
            'frekuensi', 'tanggal_mulai', 'tanggal_selesai', 'auto_confirm',
        ]
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'deskripsi_item': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
            'jumlah': forms.NumberInput(attrs={'class': 'ni-input'}),
            'kategori': forms.Select(attrs={'class': 'ni-input'}),
            'payment_type': forms.Select(attrs={'class': 'ni-input'}),
            'frekuensi': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv2': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv3': forms.Select(attrs={'class': 'ni-input'}),
            'sub_transaction_type': forms.Select(attrs={'class': 'ni-input'}),
            'revenue_account': forms.Select(attrs={'class': 'ni-input'}),
            'payment_account': forms.Select(attrs={'class': 'ni-input'}),
            'tanggal_mulai': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'tanggal_selesai': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'auto_confirm': forms.CheckboxInput(attrs={'class': 'ni-checkbox'}),
        }
