from django import forms
from apps.pos_promotions.models import Campaign


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = [
            'name', 'description', 'campaign_type', 'discount_pct', 'discount_amount',
            'max_discount_cap', 'min_purchase_amount', 'buy_quantity', 'get_quantity',
            'applicable_to', 'applicable_products', 'applicable_categories',
            'stores', 'start_date', 'end_date', 'max_uses', 'per_member_limit',
            'requires_member', 'min_tier', 'is_active',
        ]
        widgets = {
            'name':               forms.TextInput(attrs={'class': 'ni-input'}),
            'description':        forms.Textarea(attrs={'class': 'ni-textarea', 'rows': 2}),
            'campaign_type':      forms.Select(attrs={'class': 'ni-select'}),
            'discount_pct':       forms.NumberInput(attrs={'class': 'ni-input', 'step': '0.01'}),
            'discount_amount':    forms.NumberInput(attrs={'class': 'ni-input', 'step': '100'}),
            'max_discount_cap':   forms.NumberInput(attrs={'class': 'ni-input', 'step': '1000'}),
            'min_purchase_amount': forms.NumberInput(attrs={'class': 'ni-input', 'step': '1000'}),
            'start_date':         forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'end_date':           forms.DateInput(attrs={'class': 'ni-input', 'type': 'date'}),
            'applicable_to':      forms.Select(attrs={'class': 'ni-select'}),
        }
