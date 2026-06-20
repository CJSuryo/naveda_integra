"""EntitasBisnis forms."""
from django import forms
from django.utils import timezone

from .models import TipeEntitas, EntitasBisnis, EntitasBisnisLv2, EntitasBisnisLv3


class TipeEntitasForm(forms.ModelForm):
    class Meta:
        model = TipeEntitas
        fields = ('nama',)
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
        }


class EntitasBisnisForm(forms.ModelForm):
    class Meta:
        model = EntitasBisnis
        fields = (
            'nama', 'tipe_entitas', 'relasi', 'standar_akuntansi',
            'email', 'telepon', 'alamat_lengkap', 'tax_id',
            'tanggal_bergabung', 'status_aktif', 'is_company_profile',
        )
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'tipe_entitas': forms.Select(attrs={'class': 'ni-input'}),
            'relasi': forms.Select(attrs={'class': 'ni-input'}),
            'standar_akuntansi': forms.Select(attrs={'class': 'ni-input'}),
            'email': forms.EmailInput(attrs={'class': 'ni-input'}),
            'telepon': forms.TextInput(attrs={'class': 'ni-input'}),
            'alamat_lengkap': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
            'tax_id': forms.TextInput(attrs={'class': 'ni-input'}),
            'tanggal_bergabung': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'status_aktif': forms.CheckboxInput(attrs={'class': 'ni-checkbox'}),
            'is_company_profile': forms.CheckboxInput(attrs={'class': 'ni-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and not self.initial.get('tanggal_bergabung'):
            self.initial['tanggal_bergabung'] = timezone.now().date()


class EntitasBisnisLv2Form(forms.ModelForm):
    class Meta:
        model = EntitasBisnisLv2
        fields = ('nama', 'email', 'telepon', 'alamat_lengkap', 'tanggal_bergabung', 'status_aktif')
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'email': forms.EmailInput(attrs={'class': 'ni-input'}),
            'telepon': forms.TextInput(attrs={'class': 'ni-input'}),
            'alamat_lengkap': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
            'tanggal_bergabung': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'status_aktif': forms.CheckboxInput(attrs={'class': 'ni-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and not self.initial.get('tanggal_bergabung'):
            self.initial['tanggal_bergabung'] = timezone.now().date()


class EntitasBisnisLv3Form(forms.ModelForm):
    class Meta:
        model = EntitasBisnisLv3
        fields = ('nama', 'email', 'telepon', 'alamat_lengkap', 'tanggal_bergabung', 'status_aktif')
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'email': forms.EmailInput(attrs={'class': 'ni-input'}),
            'telepon': forms.TextInput(attrs={'class': 'ni-input'}),
            'alamat_lengkap': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
            'tanggal_bergabung': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'status_aktif': forms.CheckboxInput(attrs={'class': 'ni-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and not self.initial.get('tanggal_bergabung'):
            self.initial['tanggal_bergabung'] = timezone.now().date()
