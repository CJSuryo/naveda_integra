from django.db import models


class MemberTierConfig(models.Model):
    REGULAR  = 'REGULAR'
    SILVER   = 'SILVER'
    GOLD     = 'GOLD'
    PLATINUM = 'PLATINUM'
    TIER_CHOICES = [(REGULAR, 'Regular'), (SILVER, 'Silver'), (GOLD, 'Gold'), (PLATINUM, 'Platinum')]

    merchant_config     = models.ForeignKey('pos_config.MerchantPOSConfig', on_delete=models.CASCADE, related_name='tier_configs')
    tier                = models.CharField(max_length=20, choices=TIER_CHOICES)
    min_total_spent     = models.DecimalField(max_digits=15, decimal_places=2)
    points_per_thousand = models.IntegerField(default=1)
    point_value         = models.DecimalField(max_digits=10, decimal_places=2, default=100)

    class Meta:
        unique_together = ('merchant_config', 'tier')

    def __str__(self):
        return f'{self.merchant_config} — {self.tier}'


class Member(models.Model):
    merchant_config = models.ForeignKey('pos_config.MerchantPOSConfig', on_delete=models.CASCADE, related_name='members')
    entitas_bisnis  = models.ForeignKey('entitas_bisnis.EntitasBisnis', on_delete=models.SET_NULL, null=True, blank=True, related_name='member_profiles')
    member_id       = models.CharField(max_length=20, unique=True, editable=False)
    name            = models.CharField(max_length=200)
    phone           = models.CharField(max_length=20)
    email           = models.EmailField(blank=True)
    birth_date      = models.DateField(null=True, blank=True)
    tier            = models.CharField(max_length=20, choices=MemberTierConfig.TIER_CHOICES, default=MemberTierConfig.REGULAR)
    points          = models.IntegerField(default=0)
    total_spent     = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_orders    = models.IntegerField(default=0)
    joined_at       = models.DateTimeField(auto_now_add=True)
    is_active       = models.BooleanField(default=True)
    notes           = models.TextField(blank=True)

    class Meta:
        unique_together = ('merchant_config', 'phone')

    def __str__(self):
        return f'{self.member_id} — {self.name}'

    def save(self, *args, **kwargs):
        if not self.member_id:
            self.member_id = self._generate_member_id()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_member_id() -> str:
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            last = (
                Member.objects
                .select_for_update()
                .filter(member_id__startswith='MBR-')
                .order_by('-member_id')
                .values_list('member_id', flat=True)
                .first()
            )
            seq = 1
            if last:
                try:
                    seq = int(last.split('-')[1]) + 1
                except (ValueError, IndexError):
                    pass
            return f'MBR-{seq:04d}'


class MemberPointLog(models.Model):
    member     = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='point_logs')
    order      = models.ForeignKey('pos_orders.Order', on_delete=models.SET_NULL, null=True, blank=True)
    points     = models.IntegerField()
    reason     = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        sign = '+' if self.points >= 0 else ''
        return f'{self.member.member_id} {sign}{self.points} — {self.reason}'
