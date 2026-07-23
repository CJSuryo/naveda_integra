from django import forms

from .constants import AggregatorType, Environment, POSTrigger
from .models import AggregatorCredential

NI_INPUT_ATTRS = {'class': 'ni-input'}
NI_CHECKBOX_ATTRS = {'class': 'ni-checkbox'}
NI_SELECT_ATTRS = {'class': 'ni-input'}


class ConnectChannelForm(forms.Form):
    """Step 1: which channel, which region."""

    aggregator = forms.ChoiceField(
        choices=AggregatorType.choices, label='Channel',
        widget=forms.Select(attrs=NI_SELECT_ATTRS),
    )
    country = forms.ChoiceField(
        choices=[('ID', 'Indonesia')], initial='ID', label='Negara',
        widget=forms.Select(attrs=NI_SELECT_ATTRS),
    )
    environment = forms.ChoiceField(
        choices=Environment.choices, initial=Environment.PRODUCTION, label='Lingkungan',
        widget=forms.Select(attrs=NI_SELECT_ATTRS),
        help_text='Gunakan Sandbox untuk uji coba, Production untuk pesanan sungguhan.',
    )


class CredentialSecretsForm(forms.Form):
    """Restricted step: the values the aggregator issues to the company.

    Secrets are write-only. Existing values are never rendered back — leaving a
    field blank keeps what is already stored.
    """

    client_id = forms.CharField(
        label='Client / Partner ID', required=False,
        widget=forms.TextInput(attrs=NI_INPUT_ATTRS),
    )
    client_secret = forms.CharField(
        label='Client / Partner Secret', required=False,
        widget=forms.PasswordInput(attrs=NI_INPUT_ATTRS, render_value=False),
        help_text='Kosongkan untuk mempertahankan nilai yang tersimpan.',
    )
    webhook_secret = forms.CharField(
        label='Webhook Signing Secret', required=False,
        widget=forms.PasswordInput(attrs=NI_INPUT_ATTRS, render_value=False),
        help_text='Digunakan untuk memverifikasi keaslian pesanan yang masuk.',
    )
    enterprise_id = forms.CharField(
        label='Enterprise ID (GoFood lama)', required=False,
        widget=forms.TextInput(attrs=NI_INPUT_ATTRS),
        help_text='Hanya untuk integrasi GoFood model lama. Kosongkan bila tidak tahu.',
    )

    def apply_to(self, credential: AggregatorCredential) -> None:
        data = self.cleaned_data
        fields = []
        if data.get('client_id'):
            credential.client_id = data['client_id'].strip()
            fields.append('client_id')
        if data.get('client_secret'):
            credential.client_secret = data['client_secret'].strip()
            fields.append('client_secret_encrypted')
        if data.get('webhook_secret'):
            credential.webhook_secret = data['webhook_secret'].strip()
            fields.append('webhook_secret_encrypted')
        if data.get('enterprise_id'):
            credential.enterprise_id = data['enterprise_id'].strip()
            fields.append('enterprise_id')
        if fields:
            credential.save(update_fields=fields + ['updated_at'])


class ChannelSettingsForm(forms.ModelForm):
    """Behaviour an operator may safely change."""

    class Meta:
        model = AggregatorCredential
        fields = ['pos_trigger', 'tax_pct', 'price_markup_pct', 'auto_accept_orders']
        widgets = {
            'pos_trigger': forms.Select(attrs=NI_SELECT_ATTRS),
            'tax_pct': forms.NumberInput(
                attrs={**NI_INPUT_ATTRS, 'step': '0.01', 'placeholder': 'Kosong = ikut merchant'}
            ),
            'price_markup_pct': forms.NumberInput(attrs={**NI_INPUT_ATTRS, 'step': '0.01'}),
            'auto_accept_orders': forms.CheckboxInput(attrs=NI_CHECKBOX_ATTRS),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pos_trigger'].choices = POSTrigger.choices


class ManualStoreLinkForm(forms.Form):
    """The one value a ShopeeFood operator types."""

    external_store_id = forms.CharField(
        label='Store ID di aggregator',
        widget=forms.TextInput(attrs={**NI_INPUT_ATTRS, 'autocomplete': 'off'}),
        help_text=(
            'Salin ID outlet dari portal aggregator. Pastikan ini ID outlet '
            'cabang ini — bukan nama toko dan bukan ID akun.'
        ),
    )
