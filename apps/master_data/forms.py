"""Master data forms."""
from django import forms
from .models import (
    AsetLv1, AsetLv2, KewajibanLv1, KewajibanLv2,
    EkuitasLv1, EkuitasLv2, PendapatanLv1, PendapatanLv2,
    BebanLv1, BebanLv2, TipeTransaksi,
)


def _kode_nama_widgets():
    return {
        'kode': forms.TextInput(attrs={'class': 'ni-input'}),
        'nama': forms.TextInput(attrs={'class': 'ni-input'}),
    }


def _kode_auto_widgets():
    """Kode is auto-generated on create (readonly hint), editable on edit."""
    return {
        'kode': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Auto-generate jika kosong'}),
        'nama': forms.TextInput(attrs={'class': 'ni-input'}),
    }


class _KodeRenumberMixin:
    """Exclude 'kode' from unique validation so the view's renumbering logic can handle conflicts.

    When a kode is moved to an already-occupied position (e.g. 1.10 → 1.4), the update
    views call _renumber_lv1_kode / _renumber_lv2_kode (apps/master_data/views.py) which
    shifts sibling kodes out of the way before saving the new value. Standard ModelForm
    unique validation would reject the form before that logic runs, so we exclude 'kode'
    from the unique check here and let the view handle ordering atomically.
    """

    def validate_unique(self):
        exclude = self._get_validation_exclusions()
        exclude.add('kode')
        try:
            self.instance.validate_unique(exclude=exclude)
        except forms.ValidationError as e:
            self._update_errors(e)


class AsetLv1Form(_KodeRenumberMixin, forms.ModelForm):
    class Meta:
        model = AsetLv1
        fields = ('kode', 'nama')
        widgets = _kode_auto_widgets()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kode'].required = False


class AsetLv2Form(_KodeRenumberMixin, forms.ModelForm):
    class Meta:
        model = AsetLv2
        fields = ('kode', 'nama')
        widgets = _kode_auto_widgets()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kode'].required = False


class KewajibanLv1Form(_KodeRenumberMixin, forms.ModelForm):
    class Meta:
        model = KewajibanLv1
        fields = ('kode', 'nama')
        widgets = _kode_auto_widgets()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kode'].required = False


class KewajibanLv2Form(_KodeRenumberMixin, forms.ModelForm):
    class Meta:
        model = KewajibanLv2
        fields = ('kode', 'nama')
        widgets = _kode_auto_widgets()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kode'].required = False


class EkuitasLv1Form(_KodeRenumberMixin, forms.ModelForm):
    class Meta:
        model = EkuitasLv1
        fields = ('kode', 'nama')
        widgets = _kode_auto_widgets()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kode'].required = False


class EkuitasLv2Form(_KodeRenumberMixin, forms.ModelForm):
    class Meta:
        model = EkuitasLv2
        fields = ('kode', 'nama')
        widgets = _kode_auto_widgets()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kode'].required = False


class PendapatanLv1Form(_KodeRenumberMixin, forms.ModelForm):
    class Meta:
        model = PendapatanLv1
        fields = ('kode', 'nama')
        widgets = _kode_auto_widgets()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kode'].required = False


class PendapatanLv2Form(_KodeRenumberMixin, forms.ModelForm):
    class Meta:
        model = PendapatanLv2
        fields = ('kode', 'nama')
        widgets = _kode_auto_widgets()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kode'].required = False


class BebanLv1Form(_KodeRenumberMixin, forms.ModelForm):
    class Meta:
        model = BebanLv1
        fields = ('kode', 'nama')
        widgets = _kode_auto_widgets()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kode'].required = False


class BebanLv2Form(_KodeRenumberMixin, forms.ModelForm):
    class Meta:
        model = BebanLv2
        fields = ('kode', 'nama')
        widgets = _kode_auto_widgets()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kode'].required = False


class TipeTransaksiForm(forms.ModelForm):
    class Meta:
        model = TipeTransaksi
        fields = ('kode_transaksi', 'nama')
        widgets = {
            'kode_transaksi': forms.TextInput(attrs={'class': 'ni-input'}),
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
        }
