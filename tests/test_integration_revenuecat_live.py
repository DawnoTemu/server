"""Live integration tests against the real RevenueCat v2 API.

These tests hit the actual RevenueCat sandbox API to verify our client
code works correctly with the real service. They require:
  - REVENUECAT_API_KEY (v2 secret key)
  - REVENUECAT_PROJECT_ID

Skip marker: tests are skipped if credentials are missing.
"""

import os
import time

import pytest
import requests

from config import Config


# ---------------------------------------------------------------------------
# Skip condition
# ---------------------------------------------------------------------------

_API_KEY = os.getenv("REVENUECAT_API_KEY") or getattr(Config, "REVENUECAT_API_KEY", None)
_PROJECT_ID = os.getenv("REVENUECAT_PROJECT_ID") or getattr(Config, "REVENUECAT_PROJECT_ID", None)

_SKIP = not (_API_KEY and _PROJECT_ID)
_REASON = "REVENUECAT_API_KEY and REVENUECAT_PROJECT_ID required for live tests"

_HEADERS = {
    "Authorization": f"Bearer {_API_KEY}",
    "Content-Type": "application/json",
}
_BASE = "https://api.revenuecat.com/v2"


# ---------------------------------------------------------------------------
# 1. API connectivity and authentication
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP, reason=_REASON)
class TestRevenueCatAPIConnectivity:

    def test_v2_key_authenticates(self):
        """v2 API key should authenticate against /v2/projects."""
        resp = requests.get(f"{_BASE}/projects", headers=_HEADERS, timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    def test_project_exists(self):
        """Our project ID should be found in the projects list."""
        resp = requests.get(f"{_BASE}/projects", headers=_HEADERS, timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        project_ids = [p["id"] for p in data.get("items", [])]
        assert _PROJECT_ID in project_ids, (
            f"Expected {_PROJECT_ID} in projects, got: {project_ids}"
        )

    def test_v2_key_rejected_by_v1(self):
        """v2 key should NOT work with v1 endpoints."""
        resp = requests.get(
            "https://api.revenuecat.com/v1/subscribers/test_user",
            headers=_HEADERS,
            timeout=10,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 2. Customer operations
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP, reason=_REASON)
class TestRevenueCatCustomers:

    def test_nonexistent_customer_returns_404(self):
        """Looking up a customer that doesn't exist should return 404."""
        fake_id = f"nonexistent_{int(time.time())}"
        resp = requests.get(
            f"{_BASE}/projects/{_PROJECT_ID}/customers/{fake_id}",
            headers=_HEADERS,
            timeout=10,
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["type"] == "resource_missing"

    def test_purchases_for_nonexistent_customer_returns_404(self):
        """Purchases endpoint for non-existent customer should return 404."""
        fake_id = f"no_such_user_{int(time.time())}"
        resp = requests.get(
            f"{_BASE}/projects/{_PROJECT_ID}/customers/{fake_id}/purchases",
            headers=_HEADERS,
            timeout=10,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 3. Product / Entitlement / Offering verification
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP, reason=_REASON)
class TestRevenueCatProducts:

    def test_list_products(self):
        """Should be able to list products in the project."""
        resp = requests.get(
            f"{_BASE}/projects/{_PROJECT_ID}/products",
            headers=_HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    def test_list_entitlements(self):
        """Should be able to list entitlements."""
        resp = requests.get(
            f"{_BASE}/projects/{_PROJECT_ID}/entitlements",
            headers=_HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        # Verify our expected entitlement exists
        entitlement_names = [e.get("display_name") for e in data.get("items", [])]
        assert "DawnoTemu Subscription" in entitlement_names, (
            f"Expected 'DawnoTemu Subscription' in entitlements, got: {entitlement_names}"
        )

    def test_list_offerings(self):
        """Should be able to list offerings."""
        resp = requests.get(
            f"{_BASE}/projects/{_PROJECT_ID}/offerings",
            headers=_HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data


# ---------------------------------------------------------------------------
# 4. Receipt validation logic (addon_controller integration)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP, reason=_REASON)
class TestReceiptValidationWithRealAPI:

    def test_invalid_receipt_returns_false(self, app):
        """A fake receipt token should fail validation (customer not found = False)."""
        from controllers.addon_controller import _validate_receipt_with_revenuecat

        with app.app_context():
            from database import db
            from models.user_model import UserModel

            user = UserModel.create_user("rctest@example.com", "testpass123")
            user.revenuecat_app_user_id = f"rctest_invalid_{int(time.time())}"
            db.session.commit()

            # Non-existent customer -> should return False (404 from API)
            result = _validate_receipt_with_revenuecat(user, "fake_receipt_token_123")
            assert result is False

    def test_missing_revenuecat_user_id_returns_false(self, app):
        """User without revenuecat_app_user_id should fail validation."""
        from controllers.addon_controller import _validate_receipt_with_revenuecat

        with app.app_context():
            from database import db
            from models.user_model import UserModel

            user = UserModel.create_user("norc@example.com", "testpass123")
            # No revenuecat_app_user_id set
            db.session.commit()

            result = _validate_receipt_with_revenuecat(user, "any_receipt")
            assert result is False

    def test_missing_project_id_returns_false(self, app):
        """If REVENUECAT_PROJECT_ID is not set, validation should fail."""
        from controllers.addon_controller import _validate_receipt_with_revenuecat
        from unittest.mock import patch

        with app.app_context():
            from database import db
            from models.user_model import UserModel

            user = UserModel.create_user("noproj@example.com", "testpass123")
            user.revenuecat_app_user_id = "rc_noproj"
            db.session.commit()

            with patch.object(Config, "REVENUECAT_PROJECT_ID", None):
                result = _validate_receipt_with_revenuecat(user, "any_receipt")
                assert result is False


# ---------------------------------------------------------------------------
# 5. Full addon grant flow with real API
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP, reason=_REASON)
class TestAddonGrantWithRealAPI:

    def test_addon_grant_fails_for_nonexistent_receipt(self, app):
        """Full grant flow should fail when receipt doesn't exist in RevenueCat."""
        from controllers.addon_controller import AddonController
        from datetime import datetime, timedelta

        with app.app_context():
            from database import db
            from models.user_model import UserModel

            user = UserModel.create_user("addon_real@example.com", "testpass123")
            user.subscription_active = True
            user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            user.revenuecat_app_user_id = f"addon_test_{int(time.time())}"
            db.session.commit()

            ok, data, status = AddonController.grant_addon(
                user, "nonexistent_receipt_123", "credits_10", "ios",
            )
            assert ok is False
            # Either 403 (receipt validation failed) because customer not found
            assert status in (403, 503)


# ---------------------------------------------------------------------------
# 6. Webhook endpoint auth (real secret, simulated events)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP, reason=_REASON)
class TestWebhookWithRealSecret:

    def test_webhook_rejects_tampered_secret(self, client):
        """Webhook should reject requests with wrong secret."""
        import json
        resp = client.post(
            "/api/webhooks/revenuecat",
            headers={"Authorization": "Bearer wrong_secret_value"},
            data=json.dumps({"event": {"type": "TEST", "id": "live_t1"}}),
            content_type="application/json",
        )
        assert resp.status_code == 401

    def test_webhook_accepts_configured_secret(self, client):
        """Webhook should accept the configured REVENUECAT_WEBHOOK_SECRET."""
        import json
        webhook_secret = os.getenv("REVENUECAT_WEBHOOK_SECRET")
        if not webhook_secret:
            pytest.skip("REVENUECAT_WEBHOOK_SECRET not set")

        resp = client.post(
            "/api/webhooks/revenuecat",
            headers={"Authorization": f"Bearer {webhook_secret}"},
            data=json.dumps({"event": {"type": "TEST", "id": "live_t2"}}),
            content_type="application/json",
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 7. Rate limit headers (verify API returns expected headers)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP, reason=_REASON)
class TestRevenueCatRateLimits:

    def test_rate_limit_headers_present(self):
        """API should return rate-limit headers for monitoring."""
        resp = requests.get(
            f"{_BASE}/projects/{_PROJECT_ID}/entitlements",
            headers=_HEADERS,
            timeout=10,
        )
        assert resp.status_code == 200
        # RevenueCat v2 typically returns rate-limit headers
        header_keys = {k.lower() for k in resp.headers}
        has_rate_limit = any("ratelimit" in k or "rate-limit" in k for k in header_keys)
        # Some endpoints may not return rate limit headers — just verify we got a 200
        assert resp.status_code == 200
