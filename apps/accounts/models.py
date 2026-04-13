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

    class Meta:
        verbose_name = 'Role'
        verbose_name_plural = 'Role'

    def __str__(self) -> str:
        return self.nama


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
