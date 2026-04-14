"""Account forms."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

from .models import NiPermission, Role

User = get_user_model()


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'class': 'ni-input', 'autofocus': True}))
    password = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={'class': 'ni-input'}))


class RegisterForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={'class': 'ni-input'}))
    password2 = forms.CharField(label='Confirm Password', widget=forms.PasswordInput(attrs={'class': 'ni-input'}))

    class Meta:
        model = User
        fields = ('email', 'name')
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'ni-input'}),
            'name': forms.TextInput(attrs={'class': 'ni-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned_data

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class UserForm(forms.ModelForm):
    """Form for creating/editing users (admin use)."""
    password = forms.CharField(
        label='Password',
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'ni-input', 'placeholder': 'Kosongkan jika tidak diubah'}),
        help_text='Kosongkan untuk tidak mengubah password.',
    )

    class Meta:
        model = User
        fields = ('email', 'name', 'role', 'is_active')
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'ni-input'}),
            'name': forms.TextInput(attrs={'class': 'ni-input'}),
            'role': forms.Select(attrs={'class': 'ni-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'ni-checkbox'}),
        }

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        pw = self.cleaned_data.get('password')
        if pw:
            user.set_password(pw)
        if commit:
            user.save()
            self.save_m2m()
        return user


class UserPermissionForm(forms.Form):
    """Form for managing a user's permissions."""
    permissions = forms.ModelMultipleChoiceField(
        queryset=NiPermission.objects.all(),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='Permissions',
    )
