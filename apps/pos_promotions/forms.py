from django import forms
from apps.pos_promotions.models import Campaign

NI = {'class': 'ni-input'}
NI_CB = {'class': 'ni-checkbox'}


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = [
            'name', 'description', 'campaign_type', 'discount_pct', 'discount_amount',
            'max_discount_cap', 'min_purchase_amount', 'buy_quantity', 'get_quantity',
            'applicable_to', 'applicable_products',
            'stores', 'start_date', 'end_date', 'max_uses', 'per_member_limit',
            'requires_member', 'min_tier', 'is_active',
        ]
        widgets = {
            'name':                forms.TextInput(attrs=NI),
            'description':         forms.Textarea(attrs={**NI, 'rows': 2}),
            'campaign_type':       forms.Select(attrs={'class': 'ni-select'}),
            'discount_pct':        forms.NumberInput(attrs={**NI, 'step': '0.01'}),
            'discount_amount':     forms.NumberInput(attrs={**NI, 'step': '100'}),
            'max_discount_cap':    forms.NumberInput(attrs={**NI, 'step': '1000'}),
            'min_purchase_amount': forms.NumberInput(attrs={**NI, 'step': '1000'}),
            'buy_quantity':        forms.NumberInput(attrs=NI),
            'get_quantity':        forms.NumberInput(attrs=NI),
            'applicable_to':       forms.Select(attrs={'class': 'ni-select'}),
            'applicable_products': forms.SelectMultiple(attrs={**NI, 'size': '5'}),
            'stores':              forms.SelectMultiple(attrs={**NI, 'size': '4'}),
            'start_date':          forms.DateInput(attrs={**NI, 'type': 'date'}),
            'end_date':            forms.DateInput(attrs={**NI, 'type': 'date'}),
            'max_uses':            forms.NumberInput(attrs=NI),
            'per_member_limit':    forms.NumberInput(attrs=NI),
            'min_tier':            forms.TextInput(attrs=NI),
            'requires_member':     forms.CheckboxInput(attrs=NI_CB),
            'is_active':           forms.CheckboxInput(attrs=NI_CB),
        }
