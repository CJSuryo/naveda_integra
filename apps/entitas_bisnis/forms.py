"""EntitasBisnis forms."""
from django import forms
from .models import TipeEntitas, EntitasBisnis, CabangEntitasBisnis


class TipeEntitasForm(forms.ModelForm):
    class Meta:
        model = TipeEntitas
        fields = ('nama',)
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'form-control'}),
        }


class EntitasBisnisForm(forms.ModelForm):
    class Meta:
        model = EntitasBisnis
        fields = ('nama', 'tipe_entitas', 'relasi', 'email', 'telepon', 'alamat_lengkap', 'tax_id', 'tanggal_bergabung', 'status_aktif')
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'form-control'}),
            'tipe_entitas': forms.Select(attrs={'class': 'form-control'}),
            'relasi': forms.Select(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telepon': forms.TextInput(attrs={'class': 'form-control'}),
            'alamat_lengkap': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'tax_id': forms.TextInput(attrs={'class': 'form-control'}),
            'tanggal_bergabung': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status_aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CabangEntitasBisnisForm(forms.ModelForm):
    class Meta:
        model = CabangEntitasBisnis
        fields = ('nama', 'email', 'telepon', 'alamat_lengkap', 'tanggal_bergabung', 'status_aktif')
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telepon': forms.TextInput(attrs={'class': 'form-control'}),
            'alamat_lengkap': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'tanggal_bergabung': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status_aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
