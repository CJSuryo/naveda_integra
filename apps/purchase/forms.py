"""Purchase forms."""
from django import forms

from .models import (
    KategoriItem, ItemMasterPurchase, SubTransactionType,
)


class KategoriItemForm(forms.ModelForm):
    class Meta:
        model = KategoriItem
        fields = ('nama', 'tipe_item', 'entitas_bisnis')
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'tipe_item': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis': forms.SelectMultiple(attrs={'class': 'ni-input', 'size': '6'}),
        }


class ItemMasterPurchaseForm(forms.ModelForm):
    class Meta:
        model = ItemMasterPurchase
        fields = (
            'nama', 'tipe_item', 'kategori', 'velocity_category',
            'coa_account', 'lama_kadaluarsa', 'threshold_days_outstanding',
            'masa_manfaat', 'metode_penyusutan', 'metode_amortisasi',
            'metode_biaya_persediaan',
            'entitas_bisnis',
        )
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'tipe_item': forms.Select(attrs={'class': 'ni-input'}),
            'kategori': forms.Select(attrs={'class': 'ni-input'}),
            'velocity_category': forms.Select(attrs={'class': 'ni-input'}),
            'coa_account': forms.Select(attrs={'class': 'ni-input'}),
            'lama_kadaluarsa': forms.NumberInput(attrs={'class': 'ni-input'}),
            'threshold_days_outstanding': forms.NumberInput(attrs={'class': 'ni-input'}),
            'masa_manfaat': forms.NumberInput(attrs={'class': 'ni-input'}),
            'metode_penyusutan': forms.Select(attrs={'class': 'ni-input'}),
            'metode_amortisasi': forms.Select(attrs={'class': 'ni-input'}),
            'metode_biaya_persediaan': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis': forms.SelectMultiple(attrs={'class': 'ni-input', 'size': '6'}),
        }

    def __init__(self, *args, tipe_item_choices: list[str] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if tipe_item_choices:
            all_choices = ItemMasterPurchase.ITEM_TYPE_CHOICES
            self.fields['tipe_item'].choices = [
                c for c in all_choices if c[0] in tipe_item_choices
            ]
            # Filter kategori by tipe_item
            self.fields['kategori'].queryset = KategoriItem.objects.filter(
                tipe_item__in=tipe_item_choices
            ).order_by('nama')
        # For Aset Tetap: hide inventory-only fields, show penyusutan fields
        tipe_val = self.instance.tipe_item if self.instance.pk else (
            tipe_item_choices[0] if tipe_item_choices and len(tipe_item_choices) == 1 else None
        )
        if tipe_val == 'ATP' or (tipe_item_choices and tipe_item_choices == ['ATP']):
            for f in ('velocity_category', 'lama_kadaluarsa', 'threshold_days_outstanding',
                      'metode_amortisasi', 'metode_biaya_persediaan'):
                self.fields.pop(f, None)
        elif tipe_val == 'ALL' or (tipe_item_choices and tipe_item_choices == ['ALL']):
            for f in ('velocity_category', 'lama_kadaluarsa', 'threshold_days_outstanding',
                      'metode_penyusutan', 'metode_biaya_persediaan'):
                self.fields.pop(f, None)
        else:
            # Inventory items: hide asset-specific fields
            for f in ('masa_manfaat', 'metode_penyusutan', 'metode_amortisasi'):
                self.fields.pop(f, None)


class SubTransactionTypeForm(forms.ModelForm):
    class Meta:
        model = SubTransactionType
        fields = ('nama', 'module', 'direction', 'default_offset_account')
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'module': forms.Select(attrs={'class': 'ni-input'}),
            'direction': forms.Select(attrs={'class': 'ni-input'}),
            'default_offset_account': forms.Select(attrs={'class': 'ni-input'}),
        }
