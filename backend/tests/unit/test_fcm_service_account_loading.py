import json
import os
from unittest.mock import patch

import pytest
from app.core.config import Settings
from app.services import push_notifications


def test_load_fcm_from_raw_json_env():
    fake_sa = {
        "type": "service_account",
        "project_id": "test-fcm-raw-project",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC3\n-----END PRIVATE KEY-----\n",
        "client_email": "firebase-adminsdk@test-fcm-raw-project.iam.gserviceaccount.com",
    }
    raw_json = json.dumps(fake_sa)

    # Reset caches
    push_notifications._cached_sa = None
    push_notifications._cached_project_id = None

    with patch.dict(os.environ, {"FCM_SERVICE_ACCOUNT_JSON": raw_json}):
        with patch.object(push_notifications.settings, "fcm_service_account_json", raw_json):
            sa = push_notifications._load_service_account()
            assert sa["project_id"] == "test-fcm-raw-project"
            assert sa["client_email"] == fake_sa["client_email"]

            endpoint = push_notifications._get_fcm_endpoint()
            assert "test-fcm-raw-project" in endpoint
            assert endpoint == "https://fcm.googleapis.com/v1/projects/test-fcm-raw-project/messages:send"


def test_load_fcm_from_file_path(tmp_path):
    fake_sa = {
        "type": "service_account",
        "project_id": "test-fcm-file-project",
        "client_email": "firebase-adminsdk@test-fcm-file-project.iam.gserviceaccount.com",
    }
    sa_file = tmp_path / "fcm_creds.json"
    sa_file.write_text(json.dumps(fake_sa), encoding="utf-8")

    push_notifications._cached_sa = None
    push_notifications._cached_project_id = None

    with patch.dict(os.environ, {}, clear=True):
        with patch.object(push_notifications.settings, "fcm_service_account_json", ""):
            with patch.object(push_notifications.settings, "fcm_service_account_path", str(sa_file)):
                sa = push_notifications._load_service_account()
                assert sa["project_id"] == "test-fcm-file-project"


def test_load_fcm_missing_raises_file_not_found():
    push_notifications._cached_sa = None
    push_notifications._cached_project_id = None

    with patch.dict(os.environ, {}, clear=True):
        with patch.object(push_notifications.settings, "fcm_service_account_json", ""):
            with patch.object(push_notifications.settings, "fcm_service_account_path", "/nonexistent/fcm.json"):
                with pytest.raises(FileNotFoundError):
                    push_notifications._load_service_account()


def test_config_production_validator_accepts_raw_json():
    # In production, providing raw JSON in fcm_service_account_json must pass validation
    # even when fcm_service_account_path does not exist on disk
    fake_sa = {"project_id": "prod-fcm", "client_email": "sa@prod-fcm.iam.gserviceaccount.com"}
    raw_json = json.dumps(fake_sa)

    # Valid settings with fcm_service_account_json
    s = Settings(
        environment="production",
        database_url="postgresql://user:pass@prod-db.supabase.co:6543/postgres",
        supabase_url="https://prod.supabase.co",
        supabase_service_role_key="prod_service_role_key_long_string",
        jwt_secret_key="a_very_secure_random_key_that_is_at_least_32_bytes_long",
        razorpay_key_id="rzp_live_1234567890",
        razorpay_key_secret="live_secret_key_abcdef",
        razorpay_webhook_secret="live_webhook_secret_abcdef",
        turnstile_secret_key="0x4AAAAAA...",
        sentry_dsn="https://public@sentry.io/12345",
        google_client_id="prod-google-client-id.apps.googleusercontent.com",
        smtp_host="smtp.sendgrid.net",
        store_webhook_secret="live_store_secret",
        cloudflare_origin_secret="live_cf_origin_secret",
        fcm_service_account_path="/nonexistent/path/on/render.json",
        fcm_service_account_json=raw_json,
        otp_pepper_secret="a_very_secure_otp_pepper_secret_32_chars",
        msg91_auth_key="live_msg91_auth_key_12345",
        metrics_secret_token="live_metrics_secret_token_12345",
    )
    assert s.fcm_service_account_json == raw_json
