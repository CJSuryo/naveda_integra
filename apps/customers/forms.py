from django import forms
from .models import Customer


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['nama', 'email', 'telepon', 'alamat', 'npwp', 'gender', 'tanggal_lahir']
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'Nama lengkap customer'}),
            'email': forms.EmailInput(attrs={'class': 'ni-input', 'placeholder': 'email@contoh.com'}),
            'telepon': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': '08xx-xxxx-xxxx'}),
            'alamat': forms.Textarea(attrs={'class': 'ni-input', 'rows': 3, 'placeholder': 'Alamat lengkap'}),
            'npwp': forms.TextInput(attrs={'class': 'ni-input', 'placeholder': 'xx.xxx.xxx.x-xxx.xxx'}),
            'gender': forms.Select(attrs={'class': 'ni-input'}),
            'tanggal_lahir': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ['email', 'telepon', 'alamat', 'npwp', 'gender', 'tanggal_lahir']:
            self.fields[field].required = False
        self.fields['gender'].empty_label = None
        self.fields['gender'].choices = [('', '— Pilih —')] + Customer.GENDER_CHOICES
