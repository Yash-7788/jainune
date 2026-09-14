"""
Celery application factory + beat schedule.

Workers are launched separately from the FastAPI server:

  # Worker (processes tasks)
  celery -A app.celery_app worker --loglevel=info --concurrency=4 -Q default,notifications,batch

  # Beat (enqueues periodic tasks)
  celery -A app.celery_app beat --loglevel=info --scheduler celery.beat.PersistentScheduler

Beat schedule:
  every 1  min   → flush_telemetry_buffer
  every 5  min   → reap_ephemeral_media
  every 15 min   → downgrade_expired_subscriptions
  every 1  hour  → reap_stale_matches + aggregate_hourly_metrics
  every 24 hours → run_daily_compatible + purge_deleted_users
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "jainune",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.worker_pool",
        "app.workers.telemetry_worker",
        "app.workers.ephemeral_reaper",
        "app.workers.daily_compatible",
        "app.workers.notification_worker",
    ],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="Asia/Kolkata",
    enable_utc=True,
    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    # Routing: push notifications and daily heavy batch matching on isolated queues
    task_routes={
        "app.workers.notification_worker.*": {"queue": "notifications"},
        "app.workers.daily_compatible.*": {"queue": "batch"},
        "app.workers.*": {"queue": "default"},
    },
    # Result expiry
    result_expires=3600,
    # Beat schedule
    beat_schedule={
        "flush-telemetry-every-minute": {
            "task": "app.workers.telemetry_worker.flush_telemetry_buffer",
            "schedule": 60.0,  # every 60 seconds
        },
        "reap-ephemeral-media-every-5min": {
            "task": "app.workers.ephemeral_reaper.reap_ephemeral_media",
            "schedule": 300.0,
        },
        "downgrade-expired-subscriptions-every-15min": {
            "task": "app.workers.ephemeral_reaper.downgrade_expired_subscriptions",
            "schedule": 900.0,
        },
        "reap-stale-matches-hourly": {
            "task": "app.workers.ephemeral_reaper.reap_stale_matches",
            "schedule": crontab(minute=0),  # top of every hour
        },
        "aggregate-hourly-metrics-hourly": {
            "task": "app.workers.telemetry_worker.aggregate_hourly_metrics",
            "schedule": crontab(minute=5),  # top of every hour + 5m
        },
        "run-daily-compatible-2am": {
            "task": "app.workers.daily_compatible.run_daily_compatible",
            "schedule": crontab(hour=2, minute=0),
        },
        "purge-deleted-users-3am": {
            "task": "app.workers.ephemeral_reaper.purge_deleted_users",
            "schedule": crontab(hour=3, minute=0),
        },
        "send-daily-digest-notif-8am": {
            "task": "app.workers.notification_worker.send_daily_digest",
            "schedule": crontab(hour=8, minute=0),
        },
        "reap-stale-payment-intents-hourly": {
            "task": "app.workers.ephemeral_reaper.reap_stale_payment_intents",
            "schedule": crontab(minute=30),  # every hour at :30
        },
        "reap-stale-processing-media-every-10min": {
            "task": "app.workers.ephemeral_reaper.reap_stale_processing_media",
            "schedule": 600.0,
        },
        "reap-failed-s3-deletions-hourly": {
            "task": "app.workers.ephemeral_reaper.reap_failed_s3_deletions",
            "schedule": crontab(minute=15),
        },
        "purge-stale-location-waitlist-daily": {
            "task": "app.workers.ephemeral_reaper.purge_stale_location_waitlist",
            "schedule": crontab(hour=4, minute=0),
        },
    },
)
