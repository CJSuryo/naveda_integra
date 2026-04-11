"""EntitasBisnis forms."""
from django import forms
from .models import TipeEntitas, EntitasBisnis, CabangEntitasBisnis


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
        fields = ('nama', 'tipe_entitas', 'relasi', 'email', 'telepon', 'alamat_lengkap', 'tax_id', 'tanggal_bergabung', 'status_aktif')
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'tipe_entitas': forms.Select(attrs={'class': 'ni-input'}),
            'relasi': forms.Select(attrs={'class': 'ni-input'}),
            'email': forms.EmailInput(attrs={'class': 'ni-input'}),
            'telepon': forms.TextInput(attrs={'class': 'ni-input'}),
            'alamat_lengkap': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
            'tax_id': forms.TextInput(attrs={'class': 'ni-input'}),
            'tanggal_bergabung': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'status_aktif': forms.CheckboxInput(attrs={'class': 'ni-checkbox'}),
        }


class CabangEntitasBisnisForm(forms.ModelForm):
    class Meta:
        model = CabangEntitasBisnis
        fields = ('nama', 'email', 'telepon', 'alamat_lengkap', 'tanggal_bergabung', 'status_aktif')
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input'}),
            'email': forms.EmailInput(attrs={'class': 'ni-input'}),
            'telepon': forms.TextInput(attrs={'class': 'ni-input'}),
            'alamat_lengkap': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3}),
            'tanggal_bergabung': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'status_aktif': forms.CheckboxInput(attrs={'class': 'ni-checkbox'}),
        }
