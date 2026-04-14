"""Unit tests for the accounts app."""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class UserModelTests(TestCase):
    def test_create_user(self):
        user = User.objects.create_user(email='test@example.com', password='pass1234', name='Test User')
        self.assertEqual(user.email, 'test@example.com')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_superuser(self):
        su = User.objects.create_superuser(email='admin@example.com', password='admin1234', name='Admin')
        self.assertTrue(su.is_staff)
        self.assertTrue(su.is_superuser)

    def test_create_user_without_email_raises(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email='', password='pass1234', name='No Email')

    def test_user_str(self):
        user = User.objects.create_user(email='str@example.com', password='pass', name='Str Test')
        self.assertEqual(str(user), 'str@example.com')

    def test_email_is_username_field(self):
        self.assertEqual(User.USERNAME_FIELD, 'email')


class LoginViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='login@example.com', password='pass1234', name='Login User')
        self.url = reverse('accounts:login')

    def test_login_page_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/login.html')

    def test_login_success(self):
        response = self.client.post(self.url, {'username': 'login@example.com', 'password': 'pass1234'})
        self.assertRedirects(response, reverse('home'))

    def test_login_with_safe_next(self):
        next_url = reverse('entitas_bisnis:list')
        response = self.client.post(
            f'{self.url}?next={next_url}',
            {'username': 'login@example.com', 'password': 'pass1234'},
        )
        self.assertRedirects(response, next_url)

    def test_login_with_unsafe_next_redirects_home(self):
        response = self.client.post(
            f'{self.url}?next=http://evil.com/steal',
            {'username': 'login@example.com', 'password': 'pass1234'},
        )
        self.assertRedirects(response, reverse('home'))

    def test_login_wrong_password(self):
        response = self.client.post(self.url, {'username': 'login@example.com', 'password': 'wrong'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['user'].is_authenticated)

    def test_authenticated_user_redirected(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('home'))


class RegisterViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('accounts:register')

    def test_register_page_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/register.html')

    def test_register_success(self):
        data = {
            'email': 'new@example.com',
            'name': 'New User',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        }
        response = self.client.post(self.url, data)
        self.assertRedirects(response, reverse('home'))
        self.assertTrue(User.objects.filter(email='new@example.com').exists())

    def test_register_password_mismatch(self):
        data = {
            'email': 'mismatch@example.com',
            'name': 'Mismatch User',
            'password1': 'pass1234',
            'password2': 'wrong',
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email='mismatch@example.com').exists())


class LogoutViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='logout@example.com', password='pass1234', name='Logout User')

    def test_logout(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:logout'))
        self.assertRedirects(response, reverse('accounts:login'))

    def test_home_requires_login(self):
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('home')}")


# ── RBAC Model Tests ────────────────────────────────────────────────────────

class RoleModelTests(TestCase):
    def test_role_str(self):
        from .models import Role
        role = Role.objects.create(kode='admin', nama='Admin')
        self.assertEqual(str(role), 'Admin')

    def test_role_unique_kode(self):
        from .models import Role
        from django.db import IntegrityError
        Role.objects.create(kode='admin', nama='Admin')
        with self.assertRaises(IntegrityError):
            Role.objects.create(kode='admin', nama='Admin Duplicate')


class UserRoleTests(TestCase):
    def setUp(self):
        from .models import Role
        self.admin_role = Role.objects.create(kode='admin', nama='Admin')
        self.operator_role = Role.objects.create(kode='operator', nama='Operator')
        self.owner_role = Role.objects.create(kode='business_owner', nama='Pemilik Bisnis')
        self.employee_role = Role.objects.create(kode='business_employee', nama='Karyawan Bisnis')

    def test_is_admin(self):
        user = User.objects.create_user(email='admin@test.com', password='pass', name='Admin', role=self.admin_role)
        self.assertTrue(user.is_admin)
        self.assertFalse(user.is_operator)
        self.assertTrue(user.is_internal)
        self.assertFalse(user.is_business_user)

    def test_is_operator(self):
        user = User.objects.create_user(email='op@test.com', password='pass', name='Op', role=self.operator_role)
        self.assertTrue(user.is_operator)
        self.assertTrue(user.is_internal)
        self.assertFalse(user.is_admin)

    def test_is_business_owner(self):
        user = User.objects.create_user(email='owner@test.com', password='pass', name='Owner', role=self.owner_role)
        self.assertTrue(user.is_business_owner)
        self.assertTrue(user.is_business_user)
        self.assertFalse(user.is_internal)

    def test_is_business_employee(self):
        user = User.objects.create_user(email='emp@test.com', password='pass', name='Emp', role=self.employee_role)
        self.assertTrue(user.is_business_employee)
        self.assertTrue(user.is_business_user)

    def test_no_role(self):
        user = User.objects.create_user(email='norole@test.com', password='pass', name='NoRole')
        self.assertFalse(user.is_admin)
        self.assertFalse(user.is_operator)
        self.assertFalse(user.is_internal)
        self.assertFalse(user.is_business_user)


class UserEntitasBisnisTests(TestCase):
    def test_create_junction(self):
        from .models import UserEntitasBisnis
        from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
        tipe = TipeEntitas.objects.create(nama='FnB')
        entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=tipe)
        user = User.objects.create_user(email='junction@test.com', password='pass', name='J')
        ueb = UserEntitasBisnis.objects.create(user=user, entitas_bisnis=entitas)
        self.assertIn(str(user.email), str(ueb))
        self.assertEqual(user.user_entitas_bisnis.count(), 1)

    def test_unique_constraint(self):
        from .models import UserEntitasBisnis
        from apps.entitas_bisnis.models import TipeEntitas, EntitasBisnis
        from django.db import IntegrityError
        tipe = TipeEntitas.objects.create(nama='FnB')
        entitas = EntitasBisnis.objects.create(nama='PT Test', tipe_entitas=tipe)
        user = User.objects.create_user(email='dup@test.com', password='pass', name='D')
        UserEntitasBisnis.objects.create(user=user, entitas_bisnis=entitas)
        with self.assertRaises(IntegrityError):
            UserEntitasBisnis.objects.create(user=user, entitas_bisnis=entitas)


# ── NiPermission Tests ───────────────────────────────────────────────────────

class NiPermissionTests(TestCase):
    def test_permission_str(self):
        from .models import NiPermission
        p = NiPermission.objects.create(code='test_view', name='Lihat Test', module='Test')
        self.assertIn('test_view', str(p))

    def test_has_ni_perm_admin(self):
        from .models import Role, NiPermission
        role = Role.objects.create(kode='admin', nama='Admin')
        user = User.objects.create_user(email='admin_perm@test.com', password='pass', name='Admin', role=role)
        NiPermission.objects.create(code='some_perm', name='Some', module='Test')
        self.assertTrue(user.has_ni_perm('some_perm'))

    def test_has_ni_perm_explicit(self):
        from .models import Role, NiPermission
        role = Role.objects.create(kode='operator', nama='Operator')
        user = User.objects.create_user(email='op_perm@test.com', password='pass', name='Op', role=role)
        perm = NiPermission.objects.create(code='test_perm', name='Test Perm', module='Test')
        self.assertFalse(user.has_ni_perm('test_perm'))
        user.ni_permissions.add(perm)
        self.assertTrue(user.has_ni_perm('test_perm'))

    def test_get_ni_permission_codes(self):
        from .models import Role, NiPermission
        role = Role.objects.create(kode='operator', nama='Operator')
        user = User.objects.create_user(email='codes@test.com', password='pass', name='Codes', role=role)
        p1 = NiPermission.objects.create(code='a_perm', name='A', module='Test')
        p2 = NiPermission.objects.create(code='b_perm', name='B', module='Test')
        user.ni_permissions.add(p1, p2)
        codes = user.get_ni_permission_codes()
        self.assertIn('a_perm', codes)
        self.assertIn('b_perm', codes)


# ── User CRUD View Tests ─────────────────────────────────────────────────────

class UserCRUDViewTests(TestCase):
    def setUp(self):
        from .models import Role
        self.admin_role = Role.objects.create(kode='admin', nama='Admin')
        self.admin_user = User.objects.create_user(
            email='adminview@test.com', password='pass', name='Admin', role=self.admin_role,
        )
        self.client = Client()
        self.client.force_login(self.admin_user)

    def test_user_list(self):
        resp = self.client.get(reverse('accounts:user_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.admin_user.email)

    def test_user_create(self):
        resp = self.client.get(reverse('accounts:user_create'))
        self.assertEqual(resp.status_code, 200)

    def test_user_create_post(self):
        resp = self.client.post(reverse('accounts:user_create'), {
            'email': 'newuser@test.com',
            'name': 'New User',
            'password': 'pass123',
            'role': self.admin_role.pk,
            'is_active': True,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(email='newuser@test.com').exists())

    def test_user_detail(self):
        resp = self.client.get(reverse('accounts:user_detail', args=[self.admin_user.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.admin_user.email)

    def test_user_update(self):
        resp = self.client.post(reverse('accounts:user_update', args=[self.admin_user.pk]), {
            'email': self.admin_user.email,
            'name': 'Updated Name',
            'role': self.admin_role.pk,
            'is_active': True,
        })
        self.assertEqual(resp.status_code, 302)
        self.admin_user.refresh_from_db()
        self.assertEqual(self.admin_user.name, 'Updated Name')

    def test_user_delete(self):
        target = User.objects.create_user(email='del@test.com', password='pass', name='Del')
        resp = self.client.post(reverse('accounts:user_delete', args=[target.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(User.objects.filter(pk=target.pk).exists())

    def test_user_permissions_page(self):
        resp = self.client.get(reverse('accounts:user_permissions', args=[self.admin_user.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_user_permissions_post(self):
        from .models import NiPermission
        p = NiPermission.objects.create(code='test_perm', name='Test', module='Test')
        resp = self.client.post(reverse('accounts:user_permissions', args=[self.admin_user.pk]), {
            'permissions': [p.pk],
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(self.admin_user.ni_permissions.filter(code='test_perm').exists())

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse('accounts:user_list'))
        self.assertEqual(resp.status_code, 302)
