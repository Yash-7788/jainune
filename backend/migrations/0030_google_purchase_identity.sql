-- Google Play's purchaseToken is the stable purchase/subscription identity and
-- can be longer than an order ID. Store it in the existing unique provider
-- transaction identity column without truncation.
ALTER TABLE store_subscriptions
    ALTER COLUMN original_transaction_id TYPE TEXT;
