"""Custom User model for naveda_integra."""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


# ── Role ─────────────────────────────────────────────────────────────────────

class Role(models.Model):
    """Lookup table for user roles (Admin, Operator, Pemilik Bisnis, Karyawan Bisnis)."""
    ADMIN = 'admin'
    OPERATOR = 'operator'
    BUSINESS_OWNER = 'business_owner'
    BUSINESS_EMPLOYEE = 'business_employee'

    ROLE_CHOICES = [
        (ADMIN, 'Admin'),
        (OPERATOR, 'Operator'),
        (BUSINESS_OWNER, 'Pemilik Bisnis'),
        (BUSINESS_EMPLOYEE, 'Karyawan Bisnis'),
    ]

    kode = models.CharField(max_length=50, unique=True, choices=ROLE_CHOICES)
    nama = models.CharField(max_length=255)
    deskripsi = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Role'
        verbose_name_plural = 'Role'

    def __str__(self) -> str:
        return self.nama


# ── NiPermission ─────────────────────────────────────────────────────────────

class NiPermission(models.Model):
    """Application-level permission defined in config/roles_permissions.toml."""
    code = models.CharField(max_length=100, unique=True, verbose_name='Kode Permission')
    name = models.CharField(max_length=255, verbose_name='Nama Permission')
    module = models.CharField(max_length=100, blank=True, default='', verbose_name='Modul')

    class Meta:
        verbose_name = 'Permission'
        verbose_name_plural = 'Permissions'
        ordering = ['module', 'code']

    def __str__(self) -> str:
        return f'{self.name} ({self.code})'


# ── User ─────────────────────────────────────────────────────────────────────

class UserManager(BaseUserManager):
    def create_user(self, email: str, password: str | None = None, **extra_fields) -> 'User':
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str, **extra_fields) -> 'User':
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='users',
        verbose_name='Role',
    )
    ni_permissions = models.ManyToManyField(
        NiPermission,
        blank=True,
        related_name='users',
        verbose_name='Permissions',
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self) -> str:
        return self.email

    @property
    def is_admin(self) -> bool:
        return self.role is not None and self.role.kode == Role.ADMIN

    @property
    def is_operator(self) -> bool:
        return self.role is not None and self.role.kode == Role.OPERATOR

    @property
    def is_business_owner(self) -> bool:
        return self.role is not None and self.role.kode == Role.BUSINESS_OWNER

    @property
    def is_business_employee(self) -> bool:
        return self.role is not None and self.role.kode == Role.BUSINESS_EMPLOYEE

    @property
    def is_internal(self) -> bool:
        """True for Admin and Operator roles."""
        return self.is_admin or self.is_operator

    @property
    def is_business_user(self) -> bool:
        """True for Business Owner and Business Employee roles."""
        return self.is_business_owner or self.is_business_employee

    def has_ni_perm(self, perm_code: str) -> bool:
        """Check if user has a specific application permission.

        Superusers and admins always have all permissions.
        Other users are checked against their ni_permissions M2M.
        """
        if self.is_superuser or self.is_admin:
            return True
        return self.ni_permissions.filter(code=perm_code).exists()

    def get_ni_permission_codes(self) -> set[str]:
        """Return set of all permission codes this user has."""
        if self.is_superuser or self.is_admin:
            return set(NiPermission.objects.values_list('code', flat=True))
        return set(self.ni_permissions.values_list('code', flat=True))


# ── UserEntitasBisnis (Junction) ─────────────────────────────────────────────

class UserEntitasBisnis(models.Model):
    """Junction table linking users to business entities they can access."""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='user_entitas_bisnis',
    )
    entitas_bisnis = models.ForeignKey(
        'entitas_bisnis.EntitasBisnis',
        on_delete=models.CASCADE,
        related_name='user_entitas_bisnis',
    )

    class Meta:
        verbose_name = 'Akses User ke Entitas Bisnis'
        verbose_name_plural = 'Akses User ke Entitas Bisnis'
        unique_together = [('user', 'entitas_bisnis')]
        indexes = [
            models.Index(fields=['user', 'entitas_bisnis'], name='idx_ueb_user_entitas'),
        ]

    def __str__(self) -> str:
        return f'{self.user.email} → {self.entitas_bisnis}'
