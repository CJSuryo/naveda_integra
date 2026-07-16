"""Manufacturing forms."""
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError

from apps.purchase.models import ItemMasterPurchase

from .models import BillOfMaterials, BOMLine, OverheadCategory, OverheadRate, ProductionOrder


class BOMForm(forms.ModelForm):
    class Meta:
        model = BillOfMaterials
        fields = ['entitas_bisnis', 'finished_good', 'tanggal_dibuat', 'catatan']
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
    STATUS_PRODUKSI_CHOICES = [
        ('completed', 'Selesai (Langsung)'),
        ('in_progress', 'Work In Progress'),
    ]

    class Meta:
        model = ProductionOrder
        fields = [
            'tanggal',
            'entitas_bisnis',
            'entitas_bisnis_lv2',
            'entitas_bisnis_lv3',
            'bom',
            'qty_produced',
            'status',
            'lama_pengerjaan',
            'coa_produksi',
            'lead_time_days',
            'ordering_cost',
            'holding_cost_pct',
            'moq',
            'target_turnover',
            'notes',
        ]
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'entitas_bisnis': forms.Select(attrs={'class': 'ni-input', 'id': 'id_entitas_bisnis'}),
            'bom': forms.Select(attrs={'class': 'ni-input', 'id': 'id_bom'}),
            'qty_produced': forms.NumberInput(
                attrs={'class': 'ni-input', 'step': '0.0001', 'min': '0.0001', 'id': 'id_qty_produced'},
            ),
            'status': forms.Select(attrs={'class': 'ni-input', 'id': 'id_status_produksi'}),
            'lama_pengerjaan': forms.NumberInput(
                attrs={'class': 'ni-input', 'min': '1', 'id': 'id_lama_pengerjaan',
                       'placeholder': 'Contoh: 7'},
            ),
            'coa_produksi': forms.Select(attrs={'class': 'ni-input'}),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].choices = self.STATUS_PRODUKSI_CHOICES
        self.fields['lama_pengerjaan'].required = False
        from .models import BillOfMaterials as BOM
        self.fields['bom'].queryset = (
            BOM.objects.select_related('finished_good', 'entitas_bisnis').order_by('bom_id')
        )
        from apps.master_data.utils import akun_sorted_queryset
        self.fields['coa_produksi'].queryset = akun_sorted_queryset()

    def clean_tanggal(self):
        tanggal = self.cleaned_data.get('tanggal')
        if tanggal:
            from .models import PeriodClosing
            periode = tanggal.strftime('%Y-%m')
            if PeriodClosing.objects.filter(periode_bulan=periode).exists():
                raise ValidationError(
                    f'Periode {periode} sudah ditutup. Tidak dapat membuat production order pada periode ini.'
                )
        return tanggal


# Bulk item types have no defined "value" semantics for BOMLine.qty_required
# (unlike PurchaseItem.total_value/SalesItem.hpp_terpakai). Allowing them as a
# BOM raw_material lets a small qty_required (e.g. 0.5) slip past
# validate_production() and then be silently misread as a Rupiah VALUE by
# apps.inventory.ledger.consume_stock(), understating RM cost with no error.
BULK_TIPE_ITEM = ('RMB', 'FGB', 'ITMB')


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
        try:
            rm_item = ItemMasterPurchase.objects.filter(pk=int(rm_id)).only('tipe_item').first()
        except (ValueError, TypeError):
            rm_item = None
        if rm_item is None:
            errors.append(f'Baris {i + 1}: Item bahan baku tidak ditemukan.')
            i += 1
            continue
        if rm_item.tipe_item in BULK_TIPE_ITEM:
            errors.append(
                f'Baris {i + 1}: Item bulk (RMB/FGB/ITMB) belum didukung sebagai bahan baku BOM.'
            )
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


class OverheadCategoryForm(forms.ModelForm):
    class Meta:
        model = OverheadCategory
        fields = ['name', 'overhead_type', 'coa_expense', 'coa_overhead_applied', 'cost_driver', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'ni-input'}),
            'overhead_type': forms.Select(attrs={'class': 'ni-input', 'id': 'id_overhead_type'}),
            'coa_expense': forms.Select(attrs={'class': 'ni-input'}),
            'coa_overhead_applied': forms.Select(attrs={'class': 'ni-input'}),
            'cost_driver': forms.Select(attrs={'class': 'ni-input', 'id': 'id_cost_driver'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'ni-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        from apps.master_data.models import Akun
        from apps.master_data.utils import akun_sorted_queryset
        super().__init__(*args, **kwargs)
        expense_qs = akun_sorted_queryset({'kategori_id': 'beban'})
        applied_qs = akun_sorted_queryset({'kategori_id': 'kewajiban'})
        self.fields['coa_expense'].queryset = expense_qs
        self.fields['coa_overhead_applied'].queryset = applied_qs
        self.fields['coa_overhead_applied'].required = False
        self.fields['cost_driver'].required = False
        self.fields['overhead_type'].widget = forms.HiddenInput()
        self.fields['overhead_type'].required = False
        if not self.instance.pk:
            self.fields['overhead_type'].initial = 'PRODUCTION'

    def clean(self):
        cleaned = super().clean()
        overhead_type = cleaned.get('overhead_type') or 'PRODUCTION'
        cleaned['overhead_type'] = overhead_type
        cost_driver = cleaned.get('cost_driver')
        coa_applied = cleaned.get('coa_overhead_applied')
        if overhead_type == 'PRODUCTION':
            if not cost_driver:
                self.add_error('cost_driver', 'Cost Driver wajib diisi untuk Production Overhead.')
            if not coa_applied:
                self.add_error('coa_overhead_applied', 'Akun Overhead Applied wajib diisi untuk Production Overhead.')
        if overhead_type == 'PERIOD' and cost_driver:
            self.add_error('cost_driver', 'Period Overhead tidak memiliki Cost Driver.')
        return cleaned




class OverheadRateForm(forms.ModelForm):
    class Meta:
        model = OverheadRate
        fields = ['estimasi_total', 'estimasi_volume', 'rate_per_driver', 'aktual_total']
        widgets = {
            'estimasi_total': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0'}),
            'estimasi_volume': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.0001', 'min': '0'}),
            'rate_per_driver': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.000001', 'min': '0'}),
            'aktual_total': forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['estimasi_volume'].required = False
        self.fields['aktual_total'].required = False

