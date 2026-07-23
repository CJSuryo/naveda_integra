from django import forms
from .models import MerchantPOSConfig, StorePOSConfig, PaymentMethod, WorkShift


NI_INPUT_ATTRS = {'class': 'ni-input'}
NI_CHECKBOX_ATTRS = {'class': 'ni-checkbox'}
# Selects carrying this attribute are upgraded to TomSelect by static/js/ni-tomselect.js.
NI_SELECT_ATTRS = {'class': 'ni-input', 'data-ni-tomselect': ''}


class _AkunFieldsMixin:
    """Apply the project-wide akun ordering to every account dropdown.

    ``Akun.kode_akun`` is a string, so ``order_by('kode_akun')`` sorts
    lexicographically (1, 10, 2). ``akun_sorted_queryset()`` is the only correct
    source for these querysets.
    """

    akun_fields: tuple[str, ...] = ()

    def _apply_akun_querysets(self):
        from apps.master_data.utils import akun_sorted_queryset
        qs = akun_sorted_queryset()
        for name in self.akun_fields:
            if name in self.fields:
                self.fields[name].queryset = qs


class MerchantPOSConfigForm(_AkunFieldsMixin, forms.ModelForm):
    akun_fields = ('revenue_account', 'offset_coa_account', 'default_payment_account')

    class Meta:
        model = MerchantPOSConfig
        fields = [
            'is_pos_active',
            'sub_transaction_type',
            'revenue_account',
            'offset_coa_account',
            'default_payment_account',
            'default_tax_pct', 'default_service_charge_pct',
            'tax_inclusive', 'currency',
            'logo', 'qris_image',
        ]
        widgets = {
            'is_pos_active': forms.CheckboxInput(attrs=NI_CHECKBOX_ATTRS),
            'sub_transaction_type': forms.Select(attrs=NI_SELECT_ATTRS),
            'revenue_account': forms.Select(attrs=NI_SELECT_ATTRS),
            'offset_coa_account': forms.Select(attrs=NI_SELECT_ATTRS),
            'default_payment_account': forms.Select(attrs=NI_SELECT_ATTRS),
            'default_tax_pct': forms.NumberInput(attrs={**NI_INPUT_ATTRS, 'step': '0.01'}),
            'default_service_charge_pct': forms.NumberInput(attrs={**NI_INPUT_ATTRS, 'step': '0.01'}),
            'tax_inclusive': forms.CheckboxInput(attrs=NI_CHECKBOX_ATTRS),
            'currency': forms.TextInput(attrs=NI_INPUT_ATTRS),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_akun_querysets()


class StorePOSConfigForm(_AkunFieldsMixin, forms.ModelForm):
    akun_fields = ('revenue_account', 'offset_coa_account', 'default_payment_account')

    class Meta:
        model = StorePOSConfig
        fields = [
            'tax_pct', 'service_charge_pct',
            'sub_transaction_type',
            'revenue_account', 'offset_coa_account', 'default_payment_account',
            'printer_type', 'printer_ip', 'printer_port',
            'receipt_header', 'receipt_footer',
            'qris_image', 'is_active',
        ]
        widgets = {
            'tax_pct': forms.NumberInput(
                attrs={**NI_INPUT_ATTRS, 'step': '0.01', 'placeholder': 'Kosong = ikut merchant'}
            ),
            'service_charge_pct': forms.NumberInput(
                attrs={**NI_INPUT_ATTRS, 'step': '0.01', 'placeholder': 'Kosong = ikut merchant'}
            ),
            'sub_transaction_type': forms.Select(attrs=NI_SELECT_ATTRS),
            'revenue_account': forms.Select(attrs=NI_SELECT_ATTRS),
            'offset_coa_account': forms.Select(attrs=NI_SELECT_ATTRS),
            'default_payment_account': forms.Select(attrs=NI_SELECT_ATTRS),
            'printer_type': forms.Select(attrs=NI_INPUT_ATTRS),
            'printer_ip': forms.TextInput(attrs=NI_INPUT_ATTRS),
            'printer_port': forms.NumberInput(attrs=NI_INPUT_ATTRS),
            'receipt_header': forms.Textarea(attrs={**NI_INPUT_ATTRS, 'rows': 3}),
            'receipt_footer': forms.Textarea(attrs={**NI_INPUT_ATTRS, 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs=NI_CHECKBOX_ATTRS),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_akun_querysets()


class PaymentMethodForm(_AkunFieldsMixin, forms.ModelForm):
    akun_fields = ('offset_coa_account', 'payment_account')

    class Meta:
        model = PaymentMethod
        fields = [
            'name', 'method_type', 'offset_coa_account', 'payment_account',
            'is_active', 'display_order',
        ]
        widgets = {
            'name': forms.TextInput(attrs=NI_INPUT_ATTRS),
            'method_type': forms.Select(attrs=NI_INPUT_ATTRS),
            'offset_coa_account': forms.Select(attrs=NI_SELECT_ATTRS),
            'payment_account': forms.Select(attrs=NI_SELECT_ATTRS),
            'is_active': forms.CheckboxInput(attrs=NI_CHECKBOX_ATTRS),
            'display_order': forms.NumberInput(attrs=NI_INPUT_ATTRS),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_akun_querysets()


class WorkShiftForm(forms.ModelForm):
    class Meta:
        model = WorkShift
        fields = ['name', 'start_time', 'end_time', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs=NI_INPUT_ATTRS),
            'start_time': forms.TimeInput(attrs={**NI_INPUT_ATTRS, 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={**NI_INPUT_ATTRS, 'type': 'time'}),
            'is_active': forms.CheckboxInput(attrs=NI_CHECKBOX_ATTRS),
        }
