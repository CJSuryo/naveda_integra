"""Inventory forms."""
from django import forms

from apps.entitas_bisnis.models import EntitasBisnis
from apps.purchase.models import ItemMasterPurchase

from .models import InventoryRecord


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
