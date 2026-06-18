from django import forms
from apps.master_data.models import Akun
from apps.master_data.utils import akun_sorted_queryset
from apps.purchase.models import SubTransactionType
from .models import PendapatanHeader, RecurringTemplate


class PendapatanHeaderForm(forms.ModelForm):
    class Meta:
        model = PendapatanHeader
        fields = ['tanggal', 'deskripsi', 'payment_type']
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}, format='%Y-%m-%d'),
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['revenue_account'].queryset = akun_sorted_queryset()
        self.fields['payment_account'].queryset = akun_sorted_queryset({'kategori_id': 'aset'})


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
