"""Purchase forms."""
import re

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
            'coa_account', 'stock_uom', 'purchase_uom', 'sales_uom',
            'lama_kadaluarsa', 'threshold_days_outstanding',
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
            'stock_uom': forms.Select(attrs={'class': 'ni-input'}),
            'purchase_uom': forms.Select(attrs={'class': 'ni-input'}),
            'sales_uom': forms.Select(attrs={'class': 'ni-input'}),
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
                      'metode_amortisasi', 'metode_biaya_persediaan',
                      'stock_uom', 'purchase_uom', 'sales_uom'):
                self.fields.pop(f, None)
        elif tipe_val == 'ALL' or (tipe_item_choices and tipe_item_choices == ['ALL']):
            for f in ('velocity_category', 'lama_kadaluarsa', 'threshold_days_outstanding',
                      'metode_penyusutan', 'metode_biaya_persediaan',
                      'stock_uom', 'purchase_uom', 'sales_uom'):
                self.fields.pop(f, None)
        else:
            # Inventory items: hide asset-specific fields
            for f in ('masa_manfaat', 'metode_penyusutan', 'metode_amortisasi'):
                self.fields.pop(f, None)

        # UOM registration: pick the stock unit once (required); purchase and
        # sales units are optional defaults that only pre-fill the transaction
        # input unit, which can be overridden to any convertible unit.
        if 'stock_uom' in self.fields:
            self.fields['stock_uom'].required = True
        if 'purchase_uom' in self.fields:
            self.fields['purchase_uom'].required = False
            self.fields['purchase_uom'].label = 'Default Satuan Pembelian'
            self.fields['purchase_uom'].help_text = (
                'Opsional. Satuan yang otomatis terisi saat pembelian; tetap bisa '
                'diganti ke satuan lain yang punya konversi.'
            )
        if 'sales_uom' in self.fields:
            self.fields['sales_uom'].required = False
            self.fields['sales_uom'].label = 'Default Satuan Penjualan'
            self.fields['sales_uom'].help_text = (
                'Opsional. Satuan yang otomatis terisi saat penjualan; tetap bisa '
                'diganti ke satuan lain yang punya konversi.'
            )

        # Natural-sort CoA account choices by kode_akun (e.g. "1.1.10" sorts after "1.1.9")
        if 'coa_account' in self.fields:
            from apps.master_data.models import Akun

            def _kode_key(a: Akun) -> list:
                parts = re.split(r'\.', a.kode_akun or '')
                return [int(p) if p.isdigit() else p for p in parts] + [0, 0, 0]

            sorted_akun = sorted(Akun.objects.all(), key=_kode_key)
            self.fields['coa_account'].choices = [('', '---------')] + [
                (a.pk, str(a)) for a in sorted_akun
            ]


class SubTransactionTypeForm(forms.ModelForm):
    class Meta:
        model = SubTransactionType
        fields = (
            'nama', 'module', 'direction',
            'default_offset_account',
            'default_revenue_account',
            'default_payment_account',
            'default_inventory_account',
            'default_tax_account',
            'default_tax_type',
        )
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'module': forms.Select(attrs={'class': 'ni-input'}),
            'direction': forms.Select(attrs={'class': 'ni-input'}),
            'default_offset_account': forms.Select(attrs={'class': 'ni-input'}),
            'default_revenue_account': forms.Select(attrs={'class': 'ni-input'}),
            'default_payment_account': forms.Select(attrs={'class': 'ni-input'}),
            'default_inventory_account': forms.Select(attrs={'class': 'ni-input'}),
            'default_tax_account': forms.Select(attrs={'class': 'ni-input'}),
            'default_tax_type': forms.Select(attrs={'class': 'ni-input'}),
        }
