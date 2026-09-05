from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Runtime
    environment: str = "development"
    debug: bool = False
    app_version: str = "1.0.0"
    allowed_origins: List[str] = ["http://localhost:3000", "jainune://"]

    # Database
    database_url: str = "postgresql://postgres:password@localhost:5432/jainune_dev"
    database_pool_min_size: int = 5
    database_pool_max_size: int = 25
    database_statement_timeout_ms: int = 2000

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_pool_max_connections: int = 50

    # JWT / Auth
    jwt_algorithm: str = "RS256"
    jwt_private_key_path: str = "/etc/secrets/jwt_rsa.key"
    jwt_public_key_path: str = "/etc/secrets/jwt_rsa.pub"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    otp_pepper_secret: str = "default_test_pepper_secret_32_bytes_len"

    # AWS S3
    aws_region: str = "ap-south-1"
    aws_access_key_id: str = "test_aws_key"
    aws_secret_access_key: str = "test_aws_secret"
    aws_s3_quarantine_bucket: str = "jainune-media-quarantine"
    aws_s3_production_bucket: str = "jainune-media-production"
    cdn_public_base_url: str = "https://cdn.jainune.com"

    # MSG91
    msg91_auth_key: str = "test_msg91_key"
    msg91_otp_template_id: str = "test_msg91_template"

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


settings = Settings()
