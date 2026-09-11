from types import SimpleNamespace
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from accounts.models import CustomUser

from .jobs import SCHEDULED_COMMANDS, run_all_jobs
from .models import Business
from .performance import PerformanceDiagnosticMiddleware


class ScheduledJobRegistryTests(TestCase):
    @patch("core.jobs.call_command")
    def test_registry_runs_every_command(self, call_command):
        completed = run_all_jobs()

        self.assertEqual(completed, list(SCHEDULED_COMMANDS))
        self.assertEqual(
            [call.args[0] for call in call_command.call_args_list],
            list(SCHEDULED_COMMANDS),
        )


class OperationsEndpointTests(TestCase):
    def test_health_check_is_public_and_does_not_require_a_database_query(self):
        with self.assertNumQueries(0):
            response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_health_check_does_not_resolve_an_existing_login_session(self):
        user = CustomUser.objects.create_user(
            username="health-session-user",
            password="safe-password-123",
        )
        self.client.force_login(user)

        with self.assertNumQueries(0):
            response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    @override_settings(CRON_SECRET="test-cron-secret")
    def test_scheduled_jobs_require_the_bearer_secret(self):
        response = self.client.post(reverse("run_jobs"))

        self.assertEqual(response.status_code, 403)

    @override_settings(CRON_SECRET="test-cron-secret")
    @patch("core.operations.run_all_jobs", return_value=["sync_subscriptions"])
    def test_scheduled_jobs_run_from_the_shared_registry(self, run_all_jobs):
        response = self.client.post(
            reverse("run_jobs"),
            HTTP_AUTHORIZATION="Bearer test-cron-secret",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["completed"], ["sync_subscriptions"])
        run_all_jobs.assert_called_once_with()


class PerformanceDiagnosticMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(
        PERF_DIAGNOSTICS=True,
        PERF_SLOW_REQUEST_MS=0,
        PERF_SERVER_TIMING=True,
        PERF_EXCLUDED_PREFIXES=("/health/", "/static/", "/media/", "/ws/"),
    )
    def test_records_aggregate_sql_timing_without_logging_request_data(self):
        def get_response(request):
            Business.objects.exists()
            return HttpResponse("ok")

        request = self.factory.get("/business/example/42/?token=do-not-log")
        request.resolver_match = SimpleNamespace(view_name="business-detail")
        middleware = PerformanceDiagnosticMiddleware(get_response)

        with self.assertLogs("inprofic.performance", level="WARNING") as captured:
            response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("app;dur=", response.headers["Server-Timing"])
        self.assertIn("sql;dur=", response.headers["Server-Timing"])
        self.assertIn('desc="1 queries"', response.headers["Server-Timing"])
        self.assertIn("route=business-detail", captured.output[0])
        self.assertNotIn("do-not-log", captured.output[0])
        self.assertNotIn("/business/example/42/", captured.output[0])

    @override_settings(PERF_DIAGNOSTICS=True, PERF_SLOW_REQUEST_MS=0)
    def test_excluded_health_request_has_no_diagnostic_overhead_header(self):
        middleware = PerformanceDiagnosticMiddleware(lambda request: HttpResponse("ok"))
        response = middleware(self.factory.get("/health/"))

        self.assertNotIn("Server-Timing", response.headers)


class PwaEndpointTests(TestCase):
    def test_brand_manifest_is_public_and_uses_inprofic_identity(self):
        response = self.client.get(reverse("pwa_manifest"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].split(";")[0], "application/manifest+json")
        payload = response.json()
        self.assertEqual(payload["name"], "INPROFIC")
        self.assertEqual(payload["id"], "/pwa/inprofic")
        self.assertEqual(payload["theme_color"], "#050733")
        self.assertTrue(any(icon["sizes"] == "512x512" for icon in payload["icons"]))

    def test_tenant_manifest_uses_tenant_name_and_theme_but_inprofic_icons(self):
        business = Business.objects.create(
            name="Northwind Foods",
            slug="northwind-foods",
            background_color="#173B45",
            accent_color="#126E82",
            tagline="Kitchen control",
        )
        from accounts.models import UserBusiness
        from accounts.services import seed_business_roles

        roles = seed_business_roles(business)
        user = CustomUser.objects.create_user(username="manifest-user", password="safe-password-123")
        UserBusiness.objects.create(
            user=user,
            business=business,
            role=roles[CustomUser.ROLE_BUSINESS_ADMIN],
        )
        self.client.force_login(user)
        response = self.client.get(reverse("pwa_manifest_tenant", kwargs={"business_slug": business.slug}))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["name"], "Northwind Foods")
        self.assertEqual(payload["theme_color"], "#173B45")
        self.assertEqual(payload["id"], "/pwa/tenant/northwind-foods")
        self.assertTrue(all("core/pwa/icon-" in icon["src"] for icon in payload["icons"]))

    def test_service_worker_has_root_scope_and_does_not_cache_dynamic_html(self):
        response = self.client.get(reverse("pwa_service_worker"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        script = response.content.decode()
        self.assertIn("request.mode === 'navigate'", script)
        self.assertIn("cache: 'no-store'", script)
        self.assertIn("url.pathname.startsWith('/static/')", script)

    def test_tenant_launch_selects_only_an_authorized_business(self):
        from accounts.models import UserBusiness
        from accounts.services import seed_business_roles

        business = Business.objects.create(name="Launch Bakery", slug="launch-bakery")
        roles = seed_business_roles(business)
        user = CustomUser.objects.create_user(username="launch-user", password="safe-password-123")
        UserBusiness.objects.create(
            user=user,
            business=business,
            role=roles[CustomUser.ROLE_BUSINESS_ADMIN],
        )
        self.client.force_login(user)
        response = self.client.get(reverse("pwa_launch", kwargs={"business_slug": business.slug}))
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["active_business_id"], business.pk)
