-- Down Migration 0021: Revert store subscriptions and billing status

DROP TABLE IF EXISTS store_subscriptions;
ALTER TABLE users DROP COLUMN IF EXISTS billing_status;
