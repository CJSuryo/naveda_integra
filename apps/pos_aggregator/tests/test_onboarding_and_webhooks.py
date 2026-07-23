"""Onboarding state machine, pre-flight gating, and the public webhook surface."""
import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.urls import reverse

from pos_aggregator.constants import AggregatorType, OnboardingState
from pos_aggregator.models import WebhookEvent
from pos_aggregator.services import onboarding

from .factories import gofood_order_payload, make_credential, make_store_link


class StateMachineTest(TestCase):
    def setUp(self):
        self.credential = make_credential()
        self.session = onboarding.get_or_create_session(self.credential)

    def test_starts_not_started(self):
        self.assertEqual(self.session.state, OnboardingState.NOT_STARTED)

    def test_advances_forward(self):
        onboarding.confirm_prerequisites(self.session)
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, OnboardingState.PREREQ_CONFIRMED)

    def test_never_moves_backwards(self):
        self.session.state = OnboardingState.STORES_LINKED
        self.session.save()
        onboarding.confirm_prerequisites(self.session)
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, OnboardingState.STORES_LINKED)

    def test_repeating_a_step_is_harmless(self):
        onboarding.confirm_prerequisites(self.session)
        onboarding.confirm_prerequisites(self.session)
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, OnboardingState.PREREQ_CONFIRMED)

    def test_session_is_created_once(self):
        again = onboarding.get_or_create_session(self.credential)
        self.assertEqual(again.pk, self.session.pk)


class OAuthStateTest(TestCase):
    def setUp(self):
        self.session = onboarding.get_or_create_session(make_credential())

    def test_matching_nonce_accepted(self):
        self.session.oauth_state = 'nonce-abc'
        from django.utils import timezone
        self.session.oauth_state_created_at = timezone.now()
        self.session.save()
        onboarding.verify_oauth_state(self.session, 'nonce-abc')  # must not raise

    def test_mismatched_nonce_rejected(self):
        self.session.oauth_state = 'nonce-abc'
        from django.utils import timezone
        self.session.oauth_state_created_at = timezone.now()
        self.session.save()
        with self.assertRaises(onboarding.OnboardingError):
            onboarding.verify_oauth_state(self.session, 'nonce-wrong')

    def test_missing_nonce_rejected(self):
        with self.assertRaises(onboarding.OnboardingError):
            onboarding.verify_oauth_state(self.session, '')

    def test_expired_nonce_rejected(self):
        from datetime import timedelta
        from django.utils import timezone
        self.session.oauth_state = 'nonce-abc'
        self.session.oauth_state_created_at = timezone.now() - timedelta(hours=2)
        self.session.save()
        with self.assertRaises(onboarding.OnboardingError):
            onboarding.verify_oauth_state(self.session, 'nonce-abc')


class GoLiveGateTest(TestCase):
    def setUp(self):
        self.credential = make_credential()
        make_store_link(self.credential)
        self.session = onboarding.get_or_create_session(self.credential)

    def test_go_live_refused_without_preflight(self):
        with self.assertRaises(onboarding.OnboardingError):
            onboarding.go_live(self.session)

    def test_go_live_refused_when_a_check_failed(self):
        self.session.preflight_results = [
            {'code': 'auth', 'label': 'Auth', 'passed': True, 'detail': '', 'remedy': ''},
            {'code': 'tax', 'label': 'Tax', 'passed': False, 'detail': '', 'remedy': 'Isi pajak'},
        ]
        self.session.save()
        with self.assertRaises(onboarding.OnboardingError):
            onboarding.go_live(self.session)

    def test_preflight_passed_requires_at_least_one_check(self):
        self.session.preflight_results = []
        self.assertFalse(self.session.preflight_passed)


class PreflightTest(TestCase):
    """Pre-flight deliberately performs a live auth call, so it is stubbed here.

    Only the *decision logic* is under test; the network round trip belongs to
    the adapter tests and to the real sandbox run.
    """

    def setUp(self):
        self.credential = make_credential()
        make_store_link(self.credential)

        patcher = patch(
            'pos_aggregator.adapters.gofood.GoFoodAdapter.ping',
            return_value=(True, 'stubbed'),
        )
        self.addCleanup(patcher.stop)
        patcher.start()

    def _results(self):
        from pos_aggregator.services.preflight import run_preflight
        return {r.code: r for r in run_preflight(self.credential)}

    @override_settings(AGGREGATOR_PUBLIC_BASE_URL='')
    def test_missing_public_url_is_caught(self):
        result = self._results()['public_url']
        self.assertFalse(result.passed)
        self.assertTrue(result.remedy)

    @override_settings(AGGREGATOR_PUBLIC_BASE_URL='http://insecure.example.com')
    def test_non_https_public_url_is_rejected(self):
        self.assertFalse(self._results()['public_url'].passed)

    @override_settings(AGGREGATOR_PUBLIC_BASE_URL='https://naveda.example.com')
    def test_https_public_url_passes(self):
        self.assertTrue(self._results()['public_url'].passed)

    def test_auth_failure_is_reported_with_a_remedy(self):
        with patch(
            'pos_aggregator.adapters.gofood.GoFoodAdapter.ping',
            return_value=(False, 'token ditolak'),
        ):
            result = self._results()['auth']
        self.assertFalse(result.passed)
        self.assertTrue(result.remedy)

    def test_missing_accounting_config_blocks_go_live(self):
        # The factory branch has no revenue/HPP accounts configured.
        failing = [r for r in self._results().values() if r.code.startswith('accounting_')]
        self.assertTrue(failing)
        self.assertFalse(failing[0].passed)

    def test_every_failure_carries_a_remedy(self):
        from pos_aggregator.services.preflight import run_preflight
        for result in run_preflight(self.credential):
            if not result.passed:
                self.assertTrue(
                    result.remedy, f'{result.code} has no remedy for the operator'
                )


class WebhookEndpointTest(TestCase):
    """The only unauthenticated surface — it must fail closed."""

    def setUp(self):
        self.client = Client()
        self.credential = make_credential(aggregator=AggregatorType.GOFOOD)
        make_store_link(self.credential, external_store_id='OUTLET-1')
        self.url = reverse('pos_aggregator:webhook', kwargs={
            'aggregator': 'GOFOOD', 'credential_id': self.credential.pk,
        })

    def _sign(self, body: bytes) -> str:
        return hmac.new(
            self.credential.webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()

    def test_unsigned_request_is_rejected(self):
        body = json.dumps(gofood_order_payload())
        response = self.client.post(self.url, body, content_type='application/json')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_wrong_signature_is_rejected(self):
        body = json.dumps(gofood_order_payload())
        response = self.client.post(
            self.url, body, content_type='application/json',
            HTTP_X_GO_SIGNATURE='deadbeef',
        )
        self.assertEqual(response.status_code, 401)

    def test_signed_request_is_accepted_and_stored(self):
        body = json.dumps(gofood_order_payload()).encode()
        response = self.client.post(
            self.url, body, content_type='application/json',
            HTTP_X_GO_SIGNATURE=self._sign(body),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WebhookEvent.objects.count(), 1)
        self.assertTrue(WebhookEvent.objects.get().signature_verified)

    def test_unknown_credential_is_404(self):
        url = reverse('pos_aggregator:webhook', kwargs={
            'aggregator': 'GOFOOD', 'credential_id': 999999,
        })
        response = self.client.post(url, '{}', content_type='application/json')
        self.assertEqual(response.status_code, 404)

    def test_unknown_aggregator_is_404(self):
        url = reverse('pos_aggregator:webhook', kwargs={
            'aggregator': 'DELIVEROO', 'credential_id': self.credential.pk,
        })
        response = self.client.post(url, '{}', content_type='application/json')
        self.assertEqual(response.status_code, 404)

    def test_malformed_json_is_rejected_after_signature(self):
        body = b'not json'
        response = self.client.post(
            self.url, body, content_type='application/json',
            HTTP_X_GO_SIGNATURE=self._sign(body),
        )
        self.assertEqual(response.status_code, 400)

    def test_json_array_is_rejected(self):
        body = b'[1,2,3]'
        response = self.client.post(
            self.url, body, content_type='application/json',
            HTTP_X_GO_SIGNATURE=self._sign(body),
        )
        self.assertEqual(response.status_code, 400)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


class WizardAccessTest(TestCase):
    """A user must not reach another tenant's channel."""

    def setUp(self):
        from apps.accounts.models import NiPermission, Role, User, UserEntitasBisnis
        from pos_config.tests.factories import make_lv1, make_lv2, make_merchant

        role = Role.objects.create(kode=Role.BUSINESS_OWNER, nama='Owner', deskripsi='')
        self.user = User.objects.create_user(
            email='o@test.com', password='p', name='O', role=role
        )
        for code in ('pos_aggregators_manage', 'pos_config_manage'):
            perm, _ = NiPermission.objects.get_or_create(code=code, defaults={'name': code})
            self.user.ni_permissions.add(perm)

        eb_a = make_lv1(nama='Grup A')
        eb_b = make_lv1(nama='Grup B')
        UserEntitasBisnis.objects.create(user=self.user, entitas_bisnis=eb_a)

        self.foreign_credential = make_credential(
            merchant=make_merchant(make_lv2(eb_b, nama='PT B'))
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_foreign_channel_wizard_is_404(self):
        url = reverse('pos_aggregator:wizard', kwargs={'pk': self.foreign_credential.pk})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_foreign_channel_secrets_post_is_404(self):
        url = reverse('pos_aggregator:save_secrets', kwargs={'pk': self.foreign_credential.pk})
        self.assertEqual(self.client.post(url, {}).status_code, 404)

    def test_anonymous_is_redirected_to_login(self):
        anon = Client()
        url = reverse('pos_aggregator:wizard', kwargs={'pk': self.foreign_credential.pk})
        response = anon.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])
