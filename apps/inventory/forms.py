"""Inventory forms."""
from django import forms
from django.forms import inlineformset_factory

from apps.entitas_bisnis.models import EntitasBisnis
from apps.master_data.models import Akun
from apps.purchase.models import ItemMasterPurchase

from .models import (
    InventoryRecord, ItemReorderSetting, ReturCustomer, ReturCustomerItem,
    ReturSupplier, ReturSupplierItem,
    StockAdjustment, StockAdjustmentItem, StockOpname, StockOpnameItem,
    StockTransfer, StockTransferItem, Warehouse,
)


class EntitasScopedSelect(forms.Select):
    """Select gudang: menandai tiap opsi dengan ``data-eb`` (id entitas pemilik) agar
    bisa difilter di sisi klien mengikuti entitas yang dipilih (lihat
    ``_warehouse_scope_js.html``). ``eb_map`` = {warehouse_pk: entitas_bisnis_id}."""

    def __init__(self, *args, eb_map=None, **kwargs):
        self.eb_map = eb_map or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        raw = getattr(value, 'value', value)  # unwrap ModelChoiceIteratorValue
        try:
            pk = int(raw)
        except (TypeError, ValueError):
            pk = None
        if pk is not None and pk in self.eb_map:
            option['attrs']['data-eb'] = str(self.eb_map[pk])
        return option


def _warehouse_eb_map():
    return dict(Warehouse.objects.values_list('pk', 'entitas_bisnis_id'))


def _validate_warehouse_scope(cleaned_data, eb_field, warehouse_field, errors_form):
    """Pastikan gudang yang dipilih memang milik entitas bisnis yang dipilih."""
    eb = cleaned_data.get(eb_field)
    wh = cleaned_data.get(warehouse_field)
    if eb and wh and wh.entitas_bisnis_id != eb.pk:
        errors_form.add_error(
            warehouse_field,
            'Gudang yang dipilih bukan milik entitas bisnis tersebut.',
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
            'warehouse': EntitasScopedSelect(attrs={'class': 'ni-input', 'data-eb-filter': 'id_entitas_bisnis'}),
            'akun_selisih': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            status_aktif=True,
        ).order_by('nama')
        self.fields['warehouse'].widget.eb_map = _warehouse_eb_map()

    def clean(self):
        cleaned_data = super().clean()
        _validate_warehouse_scope(cleaned_data, 'entitas_bisnis', 'warehouse', self)
        return cleaned_data


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
            'warehouse': EntitasScopedSelect(attrs={'class': 'ni-input', 'data-eb-filter': 'id_entitas_bisnis'}),
            'akun_selisih': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            status_aktif=True,
        ).order_by('nama')
        self.fields['warehouse'].widget.eb_map = _warehouse_eb_map()

    def clean(self):
        cleaned_data = super().clean()
        _validate_warehouse_scope(cleaned_data, 'entitas_bisnis', 'warehouse', self)
        return cleaned_data


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
            'warehouse_asal': EntitasScopedSelect(attrs={'class': 'ni-input', 'data-eb-filter': 'id_eb_asal'}),
            'eb_tujuan': forms.Select(attrs={'class': 'ni-input'}),
            'eb_tujuan_lv2': forms.Select(attrs={'class': 'ni-input'}),
            'eb_tujuan_lv3': forms.Select(attrs={'class': 'ni-input'}),
            'warehouse_tujuan': EntitasScopedSelect(attrs={'class': 'ni-input', 'data-eb-filter': 'id_eb_tujuan'}),
            'akun_perantara': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_eb = EntitasBisnis.objects.filter(status_aktif=True).order_by('nama')
        self.fields['eb_asal'].queryset = active_eb
        self.fields['eb_tujuan'].queryset = active_eb
        eb_map = _warehouse_eb_map()
        self.fields['warehouse_asal'].widget.eb_map = eb_map
        self.fields['warehouse_tujuan'].widget.eb_map = eb_map

    def clean(self):
        cleaned_data = super().clean()
        _validate_warehouse_scope(cleaned_data, 'eb_asal', 'warehouse_asal', self)
        _validate_warehouse_scope(cleaned_data, 'eb_tujuan', 'warehouse_tujuan', self)
        return cleaned_data


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
            'warehouse': EntitasScopedSelect(attrs={'class': 'ni-input', 'data-eb-filter': 'id_entitas_bisnis'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sales_header'].required = False
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            status_aktif=True,
        ).order_by('nama')
        self.fields['warehouse'].widget.eb_map = _warehouse_eb_map()

    def clean(self):
        cleaned_data = super().clean()
        _validate_warehouse_scope(cleaned_data, 'entitas_bisnis', 'warehouse', self)
        return cleaned_data


class SalesItemScopedSelect(forms.Select):
    """Select faktur asal (SalesItem): menandai tiap opsi dengan ``data-sales-header``
    (id SalesHeader) agar bisa difilter mengikuti 'Dokumen Penjualan Asal' terpilih."""

    def __init__(self, *args, header_map=None, **kwargs):
        self.header_map = header_map or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        raw = getattr(value, 'value', value)
        try:
            pk = int(raw)
        except (TypeError, ValueError):
            pk = None
        if pk is not None and pk in self.header_map:
            option['attrs']['data-sales-header'] = str(self.header_map[pk])
        return option


class ReturCustomerItemForm(forms.ModelForm):
    class Meta:
        model = ReturCustomerItem
        fields = ('sales_item', 'item', 'qty', 'unit_cost', 'harga_jual')
        widgets = {
            'sales_item': SalesItemScopedSelect(attrs={'class': 'ni-input', 'data-parent-filter': 'id_sales_header'}),
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

        from apps.sales.models import SalesItem
        self.fields['sales_item'].required = False
        self.fields['sales_item'].queryset = SalesItem.objects.select_related(
            'sales_eb__sales_header', 'item',
        ).order_by('-sales_eb__sales_header__tanggal', '-id')
        self.fields['sales_item'].label_from_instance = (
            lambda si: f'{si.sales_eb.sales_header.transaction_id} · {si.item.item_id} · qty {si.quantity}'
        )
        self.fields['sales_item'].widget.header_map = dict(
            SalesItem.objects.values_list('pk', 'sales_eb__sales_header_id')
        )

    def clean_qty(self):
        qty = self.cleaned_data.get('qty')
        if qty is not None and qty <= 0:
            raise forms.ValidationError('Qty retur harus lebih dari 0.')
        return qty


ReturCustomerItemFormSet = inlineformset_factory(
    ReturCustomer, ReturCustomerItem,
    form=ReturCustomerItemForm,
    fields=('sales_item', 'item', 'qty', 'unit_cost', 'harga_jual'),
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
            'warehouse': EntitasScopedSelect(attrs={'class': 'ni-input', 'data-eb-filter': 'id_entitas_bisnis'}),
            'akun_lawan': forms.Select(attrs={'class': 'ni-input'}),
            'keterangan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['purchase_header'].required = False
        self.fields['entitas_bisnis'].queryset = EntitasBisnis.objects.filter(
            status_aktif=True,
        ).order_by('nama')
        self.fields['warehouse'].widget.eb_map = _warehouse_eb_map()

    def clean(self):
        cleaned_data = super().clean()
        _validate_warehouse_scope(cleaned_data, 'entitas_bisnis', 'warehouse', self)
        return cleaned_data


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


class ItemReorderSettingForm(forms.ModelForm):
    class Meta:
        model = ItemReorderSetting
        fields = ('item', 'warehouse', 'minimum_stock', 'reorder_point', 'reorder_qty')
        widgets = {
            'item': forms.Select(attrs={'class': 'ni-input'}),
            'warehouse': forms.Select(attrs={'class': 'ni-input'}),
            'minimum_stock': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'reorder_point': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
            'reorder_qty': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = ItemMasterPurchase.objects.filter(
            tipe_item__in=['RM', 'FG', 'ITM', 'RMB', 'FGB', 'ITMB'],
        ).order_by('item_id')
