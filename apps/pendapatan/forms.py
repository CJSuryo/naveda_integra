from django import forms
from apps.master_data.models import Akun
from apps.purchase.models import SubTransactionType
from .models import PendapatanHeader


class PendapatanHeaderForm(forms.ModelForm):
    class Meta:
        model = PendapatanHeader
        fields = ['tanggal', 'deskripsi', 'payment_type']
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'deskripsi': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
            'payment_type': forms.Select(attrs={'class': 'ni-input', 'id': 'id_payment_type'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deskripsi'].required = False


class PendapatanItemForm(forms.Form):
    deskripsi_item = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Deskripsi item'}),
    )
    kategori = forms.ChoiceField(
        choices=[('', '— Pilih Kategori —')] + [
            ('sewa', 'Sewa'), ('jasa', 'Jasa'), ('bunga', 'Bunga'), ('dividen', 'Dividen'),
            ('komisi', 'Komisi'), ('royalti', 'Royalti'), ('management_fee', 'Management Fee'),
            ('penjualan_aset', 'Penjualan Aset'), ('lainnya', 'Lainnya'),
        ],
        widget=forms.Select(attrs={'class': 'ni-input'}),
    )
    sub_transaction_type = forms.ModelChoiceField(
        queryset=SubTransactionType.objects.filter(module='pendapatan').order_by('nama'),
        widget=forms.Select(attrs={'class': 'ni-input stt-select'}),
        empty_label='— Pilih STT —',
    )
    jumlah_bruto = forms.DecimalField(
        max_digits=19, decimal_places=4,
        widget=forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0.01'}),
    )
    revenue_account = forms.ModelChoiceField(
        queryset=Akun.objects.all().order_by('kode_akun'),
        widget=forms.Select(attrs={'class': 'ni-input revenue-account-field'}),
        empty_label='— Pilih Akun Pendapatan —',
    )
    payment_account = forms.ModelChoiceField(
        queryset=Akun.objects.filter(kategori_id='aset').order_by('kode_akun'),
        required=False,
        widget=forms.Select(attrs={'class': 'ni-input'}),
        empty_label='— Akun Kas/Bank (opsional) —',
    )
    is_deferred = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'ni-checkbox deferred-toggle'}),
        label='Pendapatan Diterima di Muka',
    )
    deferred_account = forms.ModelChoiceField(
        queryset=Akun.objects.all().order_by('kode_akun'),
        required=False,
        widget=forms.Select(attrs={'class': 'ni-input deferred-field'}),
        empty_label='— Akun Deferred (Liability) —',
    )
    recognition_account = forms.ModelChoiceField(
        queryset=Akun.objects.all().order_by('kode_akun'),
        required=False,
        widget=forms.Select(attrs={'class': 'ni-input deferred-field'}),
        empty_label='— Akun Pengakuan (Revenue) —',
    )
    deferred_tanggal_mulai = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'ni-input deferred-field', 'type': 'date'}),
    )
    deferred_tanggal_selesai = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'ni-input deferred-field', 'type': 'date'}),
    )
    deferred_metode = forms.ChoiceField(
        choices=[('straight_line', 'Garis Lurus'), ('custom', 'Custom')],
        required=False,
        widget=forms.Select(attrs={'class': 'ni-input deferred-field'}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('is_deferred'):
            required_fields = ['deferred_account', 'recognition_account',
                               'deferred_tanggal_mulai', 'deferred_tanggal_selesai']
            for f in required_fields:
                if not cleaned.get(f):
                    self.add_error(f, 'Field ini wajib diisi untuk item deferred.')
        return cleaned
