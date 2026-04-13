"""Purchase forms."""
from django import forms

from .models import (
    KategoriItem, ItemMasterPurchase, SubTransactionType,
)


class KategoriItemForm(forms.ModelForm):
    class Meta:
        model = KategoriItem
        fields = ('nama',)
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
        }


class ItemMasterPurchaseForm(forms.ModelForm):
    class Meta:
        model = ItemMasterPurchase
        fields = (
            'nama', 'tipe_item', 'kategori', 'velocity_category',
            'coa_account', 'expiry_date', 'threshold_days_outstanding', 'unit_price',
        )
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'tipe_item': forms.Select(attrs={'class': 'ni-input'}),
            'kategori': forms.Select(attrs={'class': 'ni-input'}),
            'velocity_category': forms.Select(attrs={'class': 'ni-input'}),
            'coa_account': forms.Select(attrs={'class': 'ni-input'}),
            'expiry_date': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'threshold_days_outstanding': forms.NumberInput(attrs={'class': 'ni-input'}),
            'unit_price': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
        }


class SubTransactionTypeForm(forms.ModelForm):
    class Meta:
        model = SubTransactionType
        fields = ('nama', 'direction', 'default_offset_account')
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'direction': forms.Select(attrs={'class': 'ni-input'}),
            'default_offset_account': forms.Select(attrs={'class': 'ni-input'}),
        }
