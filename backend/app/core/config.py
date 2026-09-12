from typing import List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Runtime
    environment: str = "development"
    debug: bool = False
    app_version: str = "1.0.0"
    allowed_origins: List[str] = ["http://localhost:3000", "https://app.jainune.com", "https://jainune.com"]
    sentry_dsn: str = ""
    metrics_secret_token: str = ""

    # Database
    database_url: str = "postgresql://postgres:password@localhost:5432/jainune_dev"
    database_pool_min_size: int = 5
    database_pool_max_size: int = 50
    database_statement_timeout_ms: int = 2000

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_pool_max_connections: int = 2000

    # JWT / Auth
    jwt_algorithm: str = "RS256"
    jwt_private_key_path: str = "/etc/secrets/jwt_rsa.key"
    jwt_public_key_path: str = "/etc/secrets/jwt_rsa.pub"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    jwt_secret_key: str = "default_jwt_hmac_secret_32_bytes_len"
    otp_pepper_secret: str = "default_test_pepper_secret_32_bytes_len"
    google_client_id: str = ""
    apple_bundle_id: str = "com.jainune.app"

    # AWS S3
    aws_region: str = "ap-south-1"
    aws_access_key_id: str = "test_aws_key"
    aws_secret_access_key: str = "test_aws_secret"
    aws_s3_quarantine_bucket: str = "jainune-media-quarantine"
    aws_s3_production_bucket: str = "jainune-media-production"
    cdn_public_base_url: str = "https://cdn.jainune.com"

    # MSG91 (SMS & WhatsApp)
    msg91_auth_key: str = "test_msg91_key"
    msg91_otp_template_id: str = "test_msg91_template"
    msg91_whatsapp_template_id: str = "test_msg91_wa_template"
    msg91_promotional_flow_id: str = ""

    # Email (SMTP / Transactional)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from_address: str = "noreply@jainune.com"
    email_from_name: str = "Jainune"

    # Razorpay
    razorpay_key_id: str = "test_rzp_key"
    razorpay_key_secret: str = "test_rzp_secret"
    razorpay_webhook_secret: str = "test_rzp_webhook_secret"

    # Firebase Cloud Messaging (push notifications)
    fcm_service_account_path: str = "/etc/secrets/fcm_service_account.json"
    fcm_project_id: str = "jainune-prod"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Cloudflare Turnstile & Origin Protection
    turnstile_secret_key: str = ""
    cloudflare_origin_secret: str = ""

    # App Store / Google Play Store Webhook Secret (BUG-026)
    store_webhook_secret: str = ""
    webhook_secret: str = ""

    @model_validator(mode="after")
    def audit_production_environment(self) -> "Settings":
        if self.environment.lower() == "production":
            errors = []
            if "default_test_pepper" in self.otp_pepper_secret or len(self.otp_pepper_secret) < 32:
                errors.append("otp_pepper_secret must be set to a cryptographically secure key (>=32 chars) without default/test values")
            if "postgres:password@localhost" in self.database_url or "jainune_dev" in self.database_url:
                errors.append("database_url must point to a production database, not local dev/default credentials")
            if self.razorpay_key_id in ("test_rzp_key", "") or self.razorpay_key_id.startswith("rzp_test_") or self.razorpay_key_id.startswith("test_"):
                errors.append("razorpay_key_id must be a live production key (cannot use test/default key in production)")
            if self.razorpay_key_secret in ("test_rzp_secret", "") or self.razorpay_key_secret.startswith("test_"):
                errors.append("razorpay_key_secret must be a live production secret (cannot use test/default secret in production)")
            if self.aws_access_key_id in ("test_aws_key", "") or self.aws_access_key_id.startswith("test_"):
                errors.append("aws_access_key_id must be configured with a production IAM key")
            if self.aws_secret_access_key in ("test_aws_secret", "") or self.aws_secret_access_key.startswith("test_"):
                errors.append("aws_secret_access_key must be configured with a production IAM secret")
            if self.msg91_auth_key in ("test_msg91_key", "") or self.msg91_auth_key.startswith("test_"):
                errors.append("msg91_auth_key must be configured with production MSG91 credentials")
            if not self.cloudflare_origin_secret:
                errors.append("cloudflare_origin_secret must be set to enforce reverse-proxy origin validation in production")
            if not self.turnstile_secret_key:
                errors.append("turnstile_secret_key must be set for Cloudflare Turnstile anti-bot verification in production")
            if not self.sentry_dsn:
                errors.append("sentry_dsn must be configured for error tracking and observability in production")
            if not self.metrics_secret_token or len(self.metrics_secret_token) < 16:
                errors.append("metrics_secret_token must be configured with a secure token (>=16 chars) in production")
            if not self.google_client_id or self.google_client_id.startswith("test_") or "mock" in self.google_client_id:
                errors.append("google_client_id must be set to a valid production OAuth client ID in production")
            if not self.apple_bundle_id or self.apple_bundle_id.startswith("test_") or "mock" in self.apple_bundle_id:
                errors.append("apple_bundle_id must be configured with the production bundle ID in production")
            if not self.smtp_host:
                errors.append("smtp_host must be configured for email OTP delivery in production")
            import os
            if not self.fcm_service_account_path or not os.path.isfile(self.fcm_service_account_path):
                errors.append(f"fcm_service_account_path '{self.fcm_service_account_path}' not found")
            if not self.jwt_secret_key or self.jwt_secret_key == "default_jwt_hmac_secret_32_bytes_len" or len(self.jwt_secret_key) < 32:
                errors.append("jwt_secret_key must be set to a cryptographically random secret (>=32 chars) without default values; used for refresh-token grace HMAC")
            if not self.razorpay_webhook_secret or self.razorpay_webhook_secret in ("test_rzp_webhook_secret", "") or self.razorpay_webhook_secret.startswith("test_"):
                errors.append("razorpay_webhook_secret must be set to a production Razorpay webhook signing secret (cannot use test/default value in production)")
            if not self.store_webhook_secret:
                errors.append("store_webhook_secret must be set in production; without it all App Store / Google Play subscription lifecycle events are silently rejected (403)")
            elif self.store_webhook_secret.startswith("test_") or "mock" in self.store_webhook_secret:
                errors.append("store_webhook_secret cannot use test/mock credentials in production")

            if errors:
                raise ValueError(
                    f"Production environment variable audit failed ({len(errors)} errors):\n"
                    + "\n".join(f"  - {err}" for err in errors)
                )
        return self


settings = Settings()
