"""
Responsiveness tests for list pages that previously required horizontal
scrolling on small/tablet screens (User Management and Feed Inventory).

These render the real pages in a headless browser at several viewport widths
and assert the document does not overflow horizontally. They are skipped
automatically if Playwright (or its browser binaries) is unavailable so they
never break collection of the rest of the suite.
"""
import os

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.contrib.auth import get_user_model

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from unittest import skipUnless

PLAYWRIGHT_AVAILABLE = sync_playwright is not None

USERNAME = "responsive_test"
PASSWORD = "ResponsivePass1!"


@skipUnless(PLAYWRIGHT_AVAILABLE, "Playwright is not installed")
class NoHorizontalScrollTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        User = get_user_model()
        cls.user, _ = User.objects.get_or_create(
            username=USERNAME,
            defaults={
                "email": "responsive_test@example.com",
                "full_name": "Responsive Test",
                "role": User.Role.SUPER_ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        cls.user.set_password(PASSWORD)
        cls.user.is_staff = True
        cls.user.is_superuser = True
        cls.user.role = User.Role.SUPER_ADMIN
        cls.user.save()

    def _client(self):
        # Reuse Django's test client to obtain a valid session cookie, then
        # inject it into the browser so we hit the authenticated admin pages.
        from django.test import Client

        client = Client()
        assert client.login(username=USERNAME, password=PASSWORD)
        return client.session.session_key

    def _overflow(self, page):
        return page.evaluate(
            "() => {"
            "  const de = document.documentElement;"
            "  return Math.max(0, de.scrollWidth - de.clientWidth);"
            "}"
        )

    def _measure_pages(self, widths):
        from django.test import Client

        client = Client()
        client.login(username=USERNAME, password=PASSWORD)
        session_key = client.session.session_key

        pages = {
            "User Management": "/admin-dashboard/users/",
            "Feed Inventory": "/admin-dashboard/farm-management/feed-inventory/",
        }
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(java_script_enabled=False)
            ctx.add_cookies(
                [{"name": "sessionid", "value": session_key, "domain": "127.0.0.1", "path": "/"}]
            )
            page = ctx.new_page()
            page.set_default_timeout(20000)
            results = {}
            for name, path in pages.items():
                for w in widths:
                    page.set_viewport_size({"width": w, "height": 900})
                    page.goto(self.live_server_url + path, wait_until="domcontentloaded")
                    page.wait_for_timeout(300)
                    results[(name, w)] = self._overflow(page)
            browser.close()
            return results

    def test_no_horizontal_scroll(self):
        # Tolerance of 3px accounts for the vertical scrollbar width / sub-pixel
        # rounding; a real overflow (tens of px) fails loudly.
        results = self._measure_pages([375, 768, 1200])
        failures = {k: v for k, v in results.items() if v > 3}
        self.assertEqual(
            failures,
            {},
            f"Horizontal overflow detected: {failures}",
        )
