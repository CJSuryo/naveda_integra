from django import forms
from .models import MerchantPOSConfig, StorePOSConfig, PaymentMethod, WorkShift


NI_INPUT_ATTRS = {'class': 'ni-input'}
NI_CHECKBOX_ATTRS = {'class': 'ni-checkbox'}


class MerchantPOSConfigForm(forms.ModelForm):
    class Meta:
        model = MerchantPOSConfig
        fields = [
            'is_pos_active', 'logo', 'qris_image',
            'default_tax_pct', 'default_service_charge_pct',
            'tax_inclusive', 'currency', 'revenue_account',
        ]
        widgets = {
            'is_pos_active': forms.CheckboxInput(attrs=NI_CHECKBOX_ATTRS),
            'default_tax_pct': forms.NumberInput(attrs=NI_INPUT_ATTRS),
            'default_service_charge_pct': forms.NumberInput(attrs=NI_INPUT_ATTRS),
            'tax_inclusive': forms.CheckboxInput(attrs=NI_CHECKBOX_ATTRS),
            'currency': forms.TextInput(attrs=NI_INPUT_ATTRS),
            'revenue_account': forms.Select(attrs=NI_INPUT_ATTRS),
        }


class StorePOSConfigForm(forms.ModelForm):
    class Meta:
        model = StorePOSConfig
        fields = [
            'tax_pct', 'service_charge_pct',
            'printer_type', 'printer_ip', 'printer_port',
            'receipt_header', 'receipt_footer', 'is_active',
        ]
        widgets = {
            'tax_pct': forms.NumberInput(attrs=NI_INPUT_ATTRS),
            'service_charge_pct': forms.NumberInput(attrs=NI_INPUT_ATTRS),
            'printer_type': forms.Select(attrs=NI_INPUT_ATTRS),
            'printer_ip': forms.TextInput(attrs=NI_INPUT_ATTRS),
            'printer_port': forms.NumberInput(attrs=NI_INPUT_ATTRS),
            'receipt_header': forms.Textarea(attrs={**NI_INPUT_ATTRS, 'rows': 3}),
            'receipt_footer': forms.Textarea(attrs={**NI_INPUT_ATTRS, 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs=NI_CHECKBOX_ATTRS),
        }


class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ['name', 'method_type', 'offset_coa_account', 'is_active', 'display_order']
        widgets = {
            'name': forms.TextInput(attrs=NI_INPUT_ATTRS),
            'method_type': forms.Select(attrs=NI_INPUT_ATTRS),
            'offset_coa_account': forms.Select(attrs=NI_INPUT_ATTRS),
            'is_active': forms.CheckboxInput(attrs=NI_CHECKBOX_ATTRS),
            'display_order': forms.NumberInput(attrs=NI_INPUT_ATTRS),
        }


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
