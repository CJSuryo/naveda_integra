"""Inventory forms."""
from django import forms
from django.forms import inlineformset_factory

from apps.entitas_bisnis.models import EntitasBisnis
from apps.purchase.models import ItemMasterPurchase

from .models import InventoryRecord, StockAdjustment, StockAdjustmentItem, Warehouse


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
