# apps/pos_crm/forms.py
from django import forms
from apps.pos_crm.models import Member


class MemberRegisterForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ['name', 'phone', 'email', 'birth_date', 'notes']
        widgets = {
            'name':       forms.TextInput(attrs={'class': 'ni-input'}),
            'phone':      forms.TextInput(attrs={'class': 'ni-input'}),
            'email':      forms.EmailInput(attrs={'class': 'ni-input'}),
            'birth_date': forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'notes':      forms.Textarea(attrs={'class': 'ni-textarea', 'rows': 2}),
        }
