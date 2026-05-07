from django import forms
from .models import POSCategory, POSProduct, ModifierGroup, ModifierOption, ProductModifierGroup

NI = {'class': 'ni-input'}
NI_CB = {'class': 'ni-checkbox'}


class POSCategoryForm(forms.ModelForm):
    class Meta:
        model = POSCategory
        fields = ['name', 'color', 'icon', 'display_order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs=NI),
            'color': forms.TextInput(attrs={**NI, 'type': 'color'}),
            'icon': forms.TextInput(attrs=NI),
            'display_order': forms.NumberInput(attrs=NI),
            'is_active': forms.CheckboxInput(attrs=NI_CB),
        }


class POSProductForm(forms.ModelForm):
    class Meta:
        model = POSProduct
        fields = ['item_master', 'category', 'pos_name', 'description', 'image',
                  'selling_price', 'is_available', 'track_inventory', 'display_order']
        widgets = {
            'item_master': forms.Select(attrs=NI),
            'category': forms.Select(attrs=NI),
            'pos_name': forms.TextInput(attrs=NI),
            'description': forms.Textarea(attrs={**NI, 'rows': 3}),
            'selling_price': forms.NumberInput(attrs=NI),
            'is_available': forms.CheckboxInput(attrs=NI_CB),
            'track_inventory': forms.CheckboxInput(attrs=NI_CB),
            'display_order': forms.NumberInput(attrs=NI),
        }


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
