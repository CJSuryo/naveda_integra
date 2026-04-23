"""Manufacturing forms."""
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError

from apps.purchase.models import ItemMasterPurchase

from .models import BillOfMaterials, BOMLine, ProductionOrder


class BOMForm(forms.ModelForm):
    class Meta:
        model = BillOfMaterials
        fields = ['finished_good', 'entitas_bisnis', 'tanggal_dibuat', 'catatan']
        widgets = {
            'finished_good': forms.Select(attrs={'class': 'ni-input', 'id': 'id_finished_good'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'tanggal_dibuat': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'catatan': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.instance_pk = kwargs.get('instance') and kwargs['instance'].pk
        super().__init__(*args, **kwargs)

        # On create: only FG items without an existing BOM
        if not self.instance_pk:
            used_ids = BillOfMaterials.objects.values_list('finished_good_id', flat=True)
            self.fields['finished_good'].queryset = (
                ItemMasterPurchase.objects
                .filter(tipe_item__in=['FG', 'FGB'])
                .exclude(id__in=used_ids)
                .order_by('nama')
            )
        else:
            # On update: only show the current item (cannot change FG once BOM is created)
            self.fields['finished_good'].queryset = (
                ItemMasterPurchase.objects
                .filter(id=self.instance.finished_good_id)
            )
            self.fields['finished_good'].disabled = True


class ProductionOrderForm(forms.ModelForm):
    class Meta:
        model = ProductionOrder
        fields = [
            'tanggal',
            'entitas_bisnis',
            'bom',
            'qty_produced',
            'overhead_cost',
            'coa_produksi',
            'coa_overhead',
            'lead_time_days',
            'ordering_cost',
            'holding_cost_pct',
            'moq',
            'target_turnover',
            'notes',
        ]
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input'}),
            'bom': forms.Select(attrs={'class': 'ni-input', 'id': 'id_bom'}),
            'qty_produced': forms.NumberInput(
                attrs={'class': 'ni-input', 'step': '0.0001', 'min': '0.0001', 'id': 'id_qty_produced'},
            ),
            'overhead_cost': forms.NumberInput(
                attrs={'class': 'ni-input', 'step': '0.01', 'min': '0', 'id': 'id_overhead_cost'},
            ),
            'coa_produksi': forms.Select(attrs={'class': 'ni-input'}),
            'coa_overhead': forms.Select(attrs={'class': 'ni-input'}),
            'lead_time_days': forms.NumberInput(attrs={'class': 'ni-input', 'min': '0'}),
            'ordering_cost': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0'}),
            'holding_cost_pct': forms.NumberInput(
                attrs={'class': 'ni-input', 'step': '0.0001', 'min': '0', 'max': '1'},
            ),
            'moq': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001', 'min': '0'}),
            'target_turnover': forms.NumberInput(
                attrs={'class': 'ni-input', 'step': '0.0001', 'min': '0'},
            ),
            'notes': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        overhead = cleaned.get('overhead_cost') or Decimal('0')
        coa_overhead = cleaned.get('coa_overhead')
        if overhead > 0 and not coa_overhead:
            self.add_error(
                'coa_overhead',
                'Akun Overhead wajib diisi jika Overhead Cost lebih dari 0.',
            )
        return cleaned


def parse_bom_lines(post_data: dict) -> tuple[list[dict], list[str]]:
    """Parse BOM line data from POST.

    Returns (valid_lines, errors). Each line: {'raw_material_id': int, 'qty_required': Decimal}.
    """
    lines: list[dict] = []
    errors: list[str] = []
    i = 0
    while f'rm_{i}' in post_data:
        rm_id = post_data.get(f'rm_{i}', '').strip()
        qty_str = post_data.get(f'qty_{i}', '').strip()
        if not rm_id and not qty_str:
            i += 1
            continue
        if not rm_id:
            errors.append(f'Baris {i + 1}: Item bahan baku wajib dipilih.')
            i += 1
            continue
        if not qty_str:
            errors.append(f'Baris {i + 1}: Qty wajib diisi.')
            i += 1
            continue
        try:
            qty = Decimal(qty_str)
            if qty <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            errors.append(f'Baris {i + 1}: Qty tidak valid.')
            i += 1
            continue
        lines.append({'raw_material_id': int(rm_id), 'qty_required': qty})
        i += 1

    if not lines and not errors:
        errors.append('Minimal satu baris bahan baku wajib diisi.')

    # Check for duplicate RM
    seen = set()
    for line in lines:
        rm_id = line['raw_material_id']
        if rm_id in seen:
            errors.append(f'Item bahan baku ID {rm_id} muncul lebih dari satu kali.')
        seen.add(rm_id)

    return lines, errors
