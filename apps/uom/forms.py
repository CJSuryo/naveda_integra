from django import forms

from .models import ItemUOM, UnitOfMeasure


class UnitOfMeasureForm(forms.ModelForm):
    class Meta:
        model = UnitOfMeasure
        fields = ['kode', 'nama', 'dimension', 'factor_to_base', 'is_base', 'is_active']

    def clean(self):
        cleaned = super().clean()
        # Guard: cannot edit kode of a system unit
        if self.instance.pk and self.instance.is_system:
            cleaned['kode'] = self.instance.kode
        return cleaned


class ItemUOMForm(forms.ModelForm):
    class Meta:
        model = ItemUOM
        fields = ('item', 'uom', 'qty_in_stock_uom')

    def clean(self):
        cleaned = super().clean()
        item = cleaned.get('item')
        uom = cleaned.get('uom')
        qty = cleaned.get('qty_in_stock_uom')
        if item and uom and item.stock_uom_id == uom.pk:
            self.add_error('uom', 'Satuan konversi tidak boleh sama dengan satuan stok item.')
        if qty is not None and qty <= 0:
            self.add_error('qty_in_stock_uom', 'Harus lebih dari 0.')
        return cleaned
