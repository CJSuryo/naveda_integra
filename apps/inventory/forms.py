"""Inventory forms."""
from django import forms
from django.forms import inlineformset_factory

from apps.entitas_bisnis.models import EntitasBisnis
from apps.master_data.models import Akun
from apps.purchase.models import ItemMasterPurchase

from .models import (
    InventoryRecord, ReturCustomer, ReturCustomerItem, ReturSupplier, ReturSupplierItem,
    StockAdjustment, StockAdjustmentItem, StockOpname, StockOpnameItem,
    StockTransfer, StockTransferItem, Warehouse,
)


class InventoryRecordForm(forms.ModelForm):
    class Meta:
        model = InventoryRecord
        fields = (
            'item', 'entitas_bisnis', 'quantity', 'unit_price',
            'tanggal', 'metode_alokasi',
            'lead_time_days', 'ordering_cost', 'holding_cost_pct',
            'moq', 'tanggal_kadaluarsa',
        )
        widgets = {
            'item': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'quantity': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'unit_price': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'metode_alokasi': forms.Select(attrs={'class': 'ni-input'}),
            'lead_time_days': forms.NumberInput(attrs={'class': 'ni-input'}),
            'ordering_cost': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'holding_cost_pct': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'moq': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'tanggal_kadaluarsa': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit_price'].label = 'Unit Cost'
        self.fields['item'].queryset = ItemMasterPurchase.objects.filter(
            tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB'],
        ).order_by('item_id')
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            status_aktif=True,
        ).order_by('nama')
        self.fields['lead_time_days'].required = False
        self.fields['ordering_cost'].required = False
        self.fields['holding_cost_pct'].required = False
        self.fields['moq'].required = False
        self.fields['tanggal_kadaluarsa'].required = False


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ('entitas_bisnis', 'nama', 'alamat', 'is_active')
        widgets = {
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'alamat': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
            'is_active': forms.CheckboxInput(),
        }


class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockAdjustment
        fields = ('tanggal', 'entitas_bisnis', 'entitas_bisnis_lv2',
                  'entitas_bisnis_lv3', 'warehouse', 'akun_selisih', 'keterangan')
        widgets = {
            'tanggal': forms.DateInput(attrs={'type': 'date', 'class': 'ni-input'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv2': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv3': forms.Select(attrs={'class': 'ni-input'}),
            'warehouse': forms.Select(attrs={'class': 'ni-input'}),
            'akun_selisih': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            status_aktif=True,
        ).order_by('nama')


class StockAdjustmentItemForm(forms.ModelForm):
    class Meta:
        model = StockAdjustmentItem
        fields = ('item', 'qty', 'unit_cost')
        widgets = {
            'item': forms.Select(attrs={'class': 'ni-input'}),
            'qty': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMasterPurchase.objects.filter(
            tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB'],
        ).order_by('item_id')


StockAdjustmentItemFormSet = inlineformset_factory(
    StockAdjustment, StockAdjustmentItem,
    form=StockAdjustmentItemForm,
    fields=('item', 'qty', 'unit_cost'), extra=3, min_num=1, validate_min=True, can_delete=True,
)


class StockOpnameForm(forms.ModelForm):
    class Meta:
        model = StockOpname
        fields = ('tanggal', 'entitas_bisnis', 'entitas_bisnis_lv2',
                  'entitas_bisnis_lv3', 'warehouse', 'akun_selisih', 'keterangan')
        widgets = {
            'tanggal': forms.DateInput(attrs={'type': 'date', 'class': 'ni-input'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv2': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv3': forms.Select(attrs={'class': 'ni-input'}),
            'warehouse': forms.Select(attrs={'class': 'ni-input'}),
            'akun_selisih': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            status_aktif=True,
        ).order_by('nama')


class StockOpnameItemForm(forms.ModelForm):
    class Meta:
        model = StockOpnameItem
        fields = ('item', 'qty_sistem', 'qty_fisik', 'unit_cost')
        widgets = {
            'item': forms.Select(attrs={'class': 'ni-input'}),
            'qty_sistem': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'qty_fisik': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMasterPurchase.objects.filter(
            tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB'],
        ).order_by('item_id')


StockOpnameItemFormSet = inlineformset_factory(
    StockOpname, StockOpnameItem,
    form=StockOpnameItemForm,
    fields=('item', 'qty_sistem', 'qty_fisik', 'unit_cost'),
    extra=3, min_num=1, validate_min=True, can_delete=True,
)


class StockTransferForm(forms.ModelForm):
    class Meta:
        model = StockTransfer
        fields = ('tanggal', 'eb_asal', 'eb_asal_lv2', 'eb_asal_lv3', 'warehouse_asal',
                  'eb_tujuan', 'eb_tujuan_lv2', 'eb_tujuan_lv3', 'warehouse_tujuan',
                  'akun_perantara', 'keterangan')
        widgets = {
            'tanggal': forms.DateInput(attrs={'type': 'date', 'class': 'ni-input'}),
            'eb_asal': forms.Select(attrs={'class': 'ni-input'}),
            'eb_asal_lv2': forms.Select(attrs={'class': 'ni-input'}),
            'eb_asal_lv3': forms.Select(attrs={'class': 'ni-input'}),
            'warehouse_asal': forms.Select(attrs={'class': 'ni-input'}),
            'eb_tujuan': forms.Select(attrs={'class': 'ni-input'}),
            'eb_tujuan_lv2': forms.Select(attrs={'class': 'ni-input'}),
            'eb_tujuan_lv3': forms.Select(attrs={'class': 'ni-input'}),
            'warehouse_tujuan': forms.Select(attrs={'class': 'ni-input'}),
            'akun_perantara': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_eb = EntitasBisnis.objects.filter(status_aktif=True).order_by('nama')
        self.fields['eb_asal'].queryset = active_eb
        self.fields['eb_tujuan'].queryset = active_eb


class StockTransferItemForm(forms.ModelForm):
    class Meta:
        model = StockTransferItem
        fields = ('item', 'qty')
        widgets = {
            'item': forms.Select(attrs={'class': 'ni-input'}),
            'qty': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMasterPurchase.objects.filter(
            tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB'],
        ).order_by('item_id')

    def clean_qty(self):
        qty = self.cleaned_data.get('qty')
        if qty is not None and qty <= 0:
            raise forms.ValidationError('Qty transfer harus lebih dari 0.')
        return qty


StockTransferItemFormSet = inlineformset_factory(
    StockTransfer, StockTransferItem,
    form=StockTransferItemForm,
    fields=('item', 'qty'),
    extra=3, min_num=1, validate_min=True, can_delete=True,
)


class ReturCustomerForm(forms.ModelForm):
    """Akun override (pendapatan/piutang/HPP) dipakai hanya untuk item tanpa sales_item asal."""
    akun_pendapatan = forms.ModelChoiceField(queryset=Akun.objects.all(), required=False,
                                             widget=forms.Select(attrs={'class': 'ni-input'}))
    akun_piutang = forms.ModelChoiceField(queryset=Akun.objects.all(), required=False,
                                          widget=forms.Select(attrs={'class': 'ni-input'}))
    akun_hpp = forms.ModelChoiceField(queryset=Akun.objects.all(), required=False,
                                      widget=forms.Select(attrs={'class': 'ni-input'}))

    class Meta:
        model = ReturCustomer
        fields = ('tanggal', 'sales_header', 'entitas_bisnis', 'entitas_bisnis_lv2',
                  'entitas_bisnis_lv3', 'warehouse', 'keterangan')
        widgets = {
            'tanggal': forms.DateInput(attrs={'type': 'date', 'class': 'ni-input'}),
            'sales_header': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv2': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv3': forms.Select(attrs={'class': 'ni-input'}),
            'warehouse': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sales_header'].required = False
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            status_aktif=True,
        ).order_by('nama')


class ReturCustomerItemForm(forms.ModelForm):
    class Meta:
        model = ReturCustomerItem
        fields = ('item', 'qty', 'unit_cost', 'harga_jual')
        widgets = {
            'item': forms.Select(attrs={'class': 'ni-input'}),
            'qty': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'harga_jual': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMasterPurchase.objects.filter(
            tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB'],
        ).order_by('item_id')

    def clean_qty(self):
        qty = self.cleaned_data.get('qty')
        if qty is not None and qty <= 0:
            raise forms.ValidationError('Qty retur harus lebih dari 0.')
        return qty


ReturCustomerItemFormSet = inlineformset_factory(
    ReturCustomer, ReturCustomerItem,
    form=ReturCustomerItemForm,
    fields=('item', 'qty', 'unit_cost', 'harga_jual'),
    extra=3, min_num=1, validate_min=True, can_delete=True,
)


class ReturSupplierForm(forms.ModelForm):
    class Meta:
        model = ReturSupplier
        fields = ('tanggal', 'purchase_header', 'entitas_bisnis', 'entitas_bisnis_lv2',
                  'entitas_bisnis_lv3', 'warehouse', 'akun_lawan', 'keterangan')
        widgets = {
            'tanggal': forms.DateInput(attrs={'type': 'date', 'class': 'ni-input'}),
            'purchase_header': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv2': forms.Select(attrs={'class': 'ni-input'}),
            'entitas_bisnis_lv3': forms.Select(attrs={'class': 'ni-input'}),
            'warehouse': forms.Select(attrs={'class': 'ni-input'}),
            'akun_lawan': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['purchase_header'].required = False
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            status_aktif=True,
        ).order_by('nama')


class ReturSupplierItemForm(forms.ModelForm):
    class Meta:
        model = ReturSupplierItem
        fields = ('item', 'qty')
        widgets = {
            'item': forms.Select(attrs={'class': 'ni-input'}),
            'qty': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMasterPurchase.objects.filter(
            tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB'],
        ).order_by('item_id')

    def clean_qty(self):
        qty = self.cleaned_data.get('qty')
        if qty is not None and qty <= 0:
            raise forms.ValidationError('Qty retur harus lebih dari 0.')
        return qty


ReturSupplierItemFormSet = inlineformset_factory(
    ReturSupplier, ReturSupplierItem,
    form=ReturSupplierItemForm,
    fields=('item', 'qty'),
    extra=3, min_num=1, validate_min=True, can_delete=True,
)
