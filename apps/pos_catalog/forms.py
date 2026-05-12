from django import forms
from .models import ModifierGroup, ModifierOption

NI = {'class': 'ni-input'}
NI_CB = {'class': 'ni-checkbox'}


class ModifierGroupForm(forms.ModelForm):
    class Meta:
        model = ModifierGroup
        fields = ['name', 'is_required', 'min_selections', 'max_selections', 'display_order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs=NI),
            'is_required': forms.CheckboxInput(attrs=NI_CB),
            'min_selections': forms.NumberInput(attrs=NI),
            'max_selections': forms.NumberInput(attrs=NI),
            'display_order': forms.NumberInput(attrs=NI),
            'is_active': forms.CheckboxInput(attrs=NI_CB),
        }


class ModifierOptionForm(forms.ModelForm):
    class Meta:
        model = ModifierOption
        fields = ['name', 'additional_price', 'is_default', 'is_available', 'display_order']
        widgets = {
            'name': forms.TextInput(attrs=NI),
            'additional_price': forms.NumberInput(attrs=NI),
            'is_default': forms.CheckboxInput(attrs=NI_CB),
            'is_available': forms.CheckboxInput(attrs=NI_CB),
            'display_order': forms.NumberInput(attrs=NI),
        }
