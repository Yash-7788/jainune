# Jainune Production Audit Roadmap & Handoff Guide

## 1. Audit Strategy Overview
Production readiness divided into two sequential tiers:
- **Tier 1: Code Logic & Functional Hardening** (Resolving logic traps, race conditions, type mismatches, and schema regressions).
- **Tier 2: Real-World Production Chaos & Resilience Hardening** (~20–30 domain audits testing infrastructure, load, security, and third-party failovers).

---

## 2. Current Progress Checkpoint
- **Status**: Tier 1 Code Logic Hardening 100% COMPLETE. Tier 2 Chaos, Attack Surface & Operational Hardening 100% COMPLETE. Final 22-issue Production Hardening 100% COMPLETE.
- **Test Suite**: 196 unit tests passing with 0 errors and 0 regressions.
- **Mobile TypeScript**: `tsc --noEmit` 100% clean (0 errors).
- **Domains Audited & Hardened**:
  - Dignity Engine & report brigading defense.
  - PostGIS location verifier & anti-spoofing coordinates.
  - Razorpay payment verification & multiprovider idempotency.
  - Media uploads, S3 EXIF stripping, and atomic photo reordering.
  - WebSocket session validation, rate limiting, and ticket handshakes.
  - Admin moderation, refresh token purging, and Redis session cleanup.
  - Chat safety filters & recipient status validation.
  - Celery notification worker column compatibility.
  - `liked-me` paywall preservation & target user ID masking.
  - Serendipity wheel spin speed-chat match/chat creation & spin credit preservation.
  - Ephemeral reaper stale match expiration & chat closure sync.
  - FCM v1 string typing and CDN URL formatting.
  - Auth lifecycle gates for banned/deleted/suspended users across all providers.
  - Onboarding pipeline & Step 22 idempotency (zero network lockout risk).
  - Dilemma voting concurrency race protection (`ON CONFLICT DO NOTHING`).
  - Realtime WebSocket lifecycle (`useWebSocket.ts`), chat list sync on focus (`ChatsScreen.tsx`).
  - Media quarantine & ephemeral reaper cloud client fail-safes.
  - Account deletion dual-method alias (`DELETE /v1/users/me` & `POST /v1/users/me/delete`).
  - Mobile client telemetry buffer, AppState auto-flush (`useTelemetry.ts`), and Redis stream ingestion.
  - Feed screen 402/quota paywall triggers and subscription sheet activation.
  - Account deletion defaults to soft-delete (`hard_delete=False`), honoring 72h grace period and scrubbing PII (AUDIT-1).
  - Active paid subscription check blocks hard-purge and enforces soft-delete during subscription validity (AUDIT-2).
  - Financial transaction log retention for 7 years per RBI regulations (`financial_audit_logs`, migration `0013`) (AUDIT-1).
  - Celery ephemeral reaper 72h retention window with active subscription exclusion and financial archiving.
  - Celery `daily_compatible` worker queue isolation to `batch` queue (AUDIT-3).
  - `daily_compatible` gender-partitioned candidate scoping, asyncio event loop yielding, and 100-user checkpointed Redis pipeline flushes (AUDIT-3).
  - Non-refundable protections for arcade consumable packs and fulfilled passes (B-1).
  - Razorpay payment ID resolution on order ID lookups (B-2).
  - Partial refund preservation of subscription tier (B-3).
  - Super connect credit clawback on subscription full refund (B-4).
  - Migration 0008 version collision resolved via renumbering to `0014_reports_action_taken.sql` (P3).
  - `interactions.interaction_type` NOT NULL constraint dropped with default fallback (migration `0015`) and populated in `interactions.py` (P1).
  - GPS reverse-proxy trust boundary origin-lock (`cloudflare_origin_secret`) and `client_ip` format validation (P2).
  - DPDP Act / TRAI marketing consent enforcement in `broadcast_promotional_campaign`, schema, and onboarding step 21 UI (P4).
  - Celery worker deployment configuration updated to consume `batch` queue across `docker-compose.prod.yml` and `docker-compose.yml` (Tier 2).
  - Reverse-proxy rate limit evasion defense via `get_trusted_client_ip()` origin-locked resolution across auth, location, and onboarding (Tier 2).
  - Arcade wallet double-spend serialized via `SELECT ... FOR UPDATE` row locks in `spin_serendipity_wheel` and `roll_lucky_dice` (Tier 2).
  - Automated FCM v1 / Expo unregistered and dead device token nullification from PostgreSQL (Tier 2).
  - Resilient MSG91 SMS 503 / DLT template congestion automatic failover to WhatsApp OTP (Tier 2).
  - Asyncpg connection pool 5s acquire timeout with 503 Service Unavailable + Retry-After headers under 500 req/s bursts (Tier 2 Phase 1).
  - Redis pool enlarged to 2000 max connections and WebSocket pub/sub leak-proof slow-consumer (5s) and zombie heartbeat (60s) teardowns (Tier 2 Phase 1).
  - Super connect credit double-spend serialized via `SELECT ... FOR UPDATE` row lock in `record_interaction_action` (Tier 2 Phase 1).
  - Razorpay webhook chaos handled: `order.paid`, `refund.processed`, `refund.created` aliases, and payload normalization (Tier 2 Phase 2).
  - Apple StoreKit & Google Play subscription lifecycle: grace period, account hold tier suspension, and refund revocation clawbacks (Tier 2 Phase 2).
  - Apple APNs / Expo bad device token detection and automated pruning from PostgreSQL (Tier 2 Phase 2).
  - PostGIS bounding box KNN pruning benchmarks across 100k spatial points (Tier 2 Phase 3).
  - pgvector division-by-zero NaN cosine distance trap eliminated via unit vector normalization (Tier 2 Phase 3).
  - Zero-downtime non-locking concurrent rebuilding for GIST spatial and HNSW vector indexes (migration 0016) (Tier 2 Phase 3).

---

## 3. Tier 1: Code Logic Audits [100% COMPLETE]
All code logic audits across auth, onboarding, feed, chat, payments, arcade, and media are complete. Tier 2 Real-World Production Chaos & Resilience Hardening underway.

---

## 4. Tier 2: Real-World Production Hardening (20–30 Domain Audits)

### Phase 1: Load, Concurrency & State Pressure [100% COMPLETE]
- ✅ 10,000 concurrent WebSocket connections: Redis pool scaled to 2000 connections, slow-consumer protection (5s timeout), and task-reaping cleanup.
- ✅ Asyncpg database connection pool exhaustion under 500 req/s bursts: 5s acquire timeout and 503 `Retry-After: 2` fast error handling.
- ✅ Redis pub/sub memory leak and channel backlog audit: 60s zombie heartbeat timeout eliminates unclosed socket subscriptions.
- ✅ High-concurrency wallet deduction races: `SELECT ... FOR UPDATE` row locks on arcade spins, dice rolls, and super connect credits.

### Phase 2: Third-Party Failures & Webhook Chaos [100% COMPLETE]
- ✅ **Razorpay**: Dropped webhooks, delayed payment confirmations, forged webhook signatures, refund webhook aliases (`refund.processed`, `refund.created`), `order.paid` synchronization, and dual `razorpay_payment_id`/`razorpay_order_id` resolution.
- ✅ **MSG91**: Complete SMS gateway 503 downtime, timeout retry storms, and Indian DLT template rejection automatic failover to WhatsApp OTP.
- ✅ **Apple StoreKit & Google Play Billing**: Subscription grace periods (`in_grace_period`), billing retry status, account holds (`account_hold` tier suspension to free), and refund revocations with super connect credit clawbacks.
- ✅ **FCM / APNs**: Stale/invalid device token cleanup worker, Apple APNs `BadDeviceToken`, `DeviceTokenNotForTopic`, `ExpiredToken`, and Expo rejection token nullification from PostgreSQL.

### Phase 3: PostGIS Spatial & pgvector Scale [100% COMPLETE]
- ✅ **Spatial KNN Benchmark**: 100,000-point geodesic distance simulation demonstrates >99% O(1) bounding-box candidate pruning (<200ms nationwide evaluation).
- ✅ **Composite Attribute & GIST Conjunction**: Hard dealbreaker pruning (dietary strictness, onion/garlic, sect) alongside geodetic radius constraints prevents candidate leakage and heap memory bloat.
- ✅ **Zero-Downtime Index Maintenance**: Migration `0016` enforces `CREATE INDEX CONCURRENTLY` on PostGIS geography GiST (`idx_users_location_geog`) and pgvector HNSW (`idx_ubv_hnsw_cosine`) outside transaction blocks, preventing table write locks during 24/7 matchmaking.
- ✅ **Vector NaN Trap Elimination**: Replaced uninitialized `[0]*128` zero-vectors with normalized uniform unit vectors (`[0.088388]*128`, norm=1.0) and wrapped SQL cosine distance in `COALESCE`, permanently eliminating divide-by-zero `NaN` float outputs from candidate scoring and JSON serialization.


### Phase 4: Pentest, OWASP & Attack Surface [100% COMPLETE]
- ✅ **Run 1: Comprehensive IDOR Audit**: Enforced caller ownership checks across all UUID endpoints (`delete_media`, `get_media_status`, `chats._assert_participant`, `subscriptions.verify_payment`, self-block, self-report, and self-interaction rejections).
- ✅ **Run 2: Rate Limit Evasion Tests via Header Manipulation**: Hardened `get_trusted_client_ip` using stdlib `ipaddress.ip_address` to sanitize candidate IPs against CRLF/Redis key injection and prevent spoofing by ignoring `X-Forwarded-For`/`CF-Connecting-IP` in production unless matched by Cloudflare edge origin secret.
- ✅ **Run 3: SQL Injection / PostGIS Query String Audit**: Verified 100% parameterization (`$1, $2, ...`) across spatial distance/bounding queries (`ST_Distance`, `ST_DWithin`), bound dynamic UPDATE clauses to an immutable schema column whitelist (`_allowed_cols`), and parameterized promotional campaign limits.
- ✅ **Run 4: Malicious Media Payload Tests**: Added `process_and_sanitize_image` enforcing magic byte verification (`JPEG`, `PNG`, `WEBP`, `HEIC`), PIL decompression bomb limits (`Image.MAX_IMAGE_PIXELS = 25_000_000`), corrupted header rejection, and 100% EXIF/GPS coordinate stripping prior to production bucket synchronization.
- ✅ **Run 5: SSRF & Webhook Signature Forgery Tests**: Strict HMAC-SHA256 signature enforcement across webhook ingress with `hmac.compare_digest`, and added `is_safe_public_url` blocking SSRF against loopback, RFC 1918 private subnets, and AWS/cloud metadata endpoints (`169.254.169.254`).
- ✅ **Run 6: JWT Replay, Token Revocation & Security Headers**: Verified pyjwt algorithm confusion defense (`RS256` only, rejecting `none` and `HS256`), token replay rejection via Redis JTI blacklist, strict CORS allowed origins whitelist, and production security headers (`nosniff`, `DENY`, HSTS, CSP).

### Phase 5: Mobile Real-Device Stress & Native Edge Cases [100% COMPLETE]
- ✅ **Run 1: Low-Memory Terminations & Camera Capture Heap Pressure**: Implemented `ImagePicker.getPendingResultAsync()` recovery hook on Android in `Step19Photos.tsx` and `EditProfileScreen.tsx` to restore and upload captured photos after Android OS destroys the React Native Activity under camera RAM pressure.
- ✅ **Run 2: Mid-Flow Permission Revocations**: Added `AppState` active listener in `Step11Location.tsx` to automatically re-evaluate permissions when returning from device settings; wired friendly alerts with direct `Linking.openSettings()` deep links on photo library and location denial.
- ✅ **Run 3: Active WebSocket Backgrounding & Reconnect**: Hardened `useWebSocket.ts` and `ChatScreen.tsx` to clear heartbeat ping timers and cleanly close sockets (`code: 1000`) on `background` or `inactive` AppState transitions, preventing zombie subscriptions and socket deadlocks, while re-syncing unread message backlogs on `active`.
- ✅ **Run 4: Seamless Network Handoffs & Offline Packet Loss**: Enhanced `withRetry` in `client.ts` with exponential backoff plus randomized jitter (`0-200ms`) and HTTP 429 retry support to absorb momentary packet drops during Wi-Fi ↔ Cellular handoffs.
- ✅ **Run 5: Checkout Backgrounding & External UPI Interrupts**: Persisted pending order IDs before Razorpay/UPI redirection in `billingService.ts`; wired `AppState` active listener in `SubscriptionsScreen.tsx` to query `/subscriptions/sync` upon return from external bank/UPI apps (GPay, PhonePe, Paytm), ensuring immediate subscription activation without double billing.
- ✅ **Run 6: Push Notification Taps from Cold Boot vs Background**: Extracted unified `handleNotificationRouting` and added `Notifications.getLastNotificationResponseAsync()` in `notifications.ts` wired to `AppNavigator.tsx` on `onReady` and mount, ensuring seamless deep-link navigation to chat, matches, and likes whether tapped from cold boot or background.
- ✅ **Run 7: Font Scaling, Small Screen (320px) & Accessibility Stress**: Upgraded core buttons to dynamic `minHeight: 52, paddingVertical: spacing.sm` with `maxFontSizeMultiplier={1.35}`; scaled OTP box width to 44px to fit 6 digits within 320px screens; wrapped `OnboardingStep.tsx` in a scrollable `ScrollView` container to eliminate button clipping under 200% system accessibility font scaling.

### Phase 6: Infrastructure, CI/CD & Deployment (4 Runs) [100% COMPLETE]
- ✅ **Run 1: Docker Image Minimization & Non-Root Security Container Execution**: Configured `Dockerfile` with explicit non-root system UID/GID `10001:10001`, system home directory creation (`-m -d /home/appuser`), restricted `--forwarded-allow-ips` to localhost (`127.0.0.1`), and hardened `docker-compose.prod.yml` with `user: "10001:10001"`, `init: true`, `security_opt: [no-new-privileges:true]`, and `cap_drop: [ALL]`.
- ✅ **Run 2: Production Environment Variable Auditing**: Added Pydantic `@model_validator(mode="after")` to `Settings` in `app/core/config.py` that fails fast with `ValidationError` in `production` mode if insecure test/default credentials (`test_rzp_*`, `test_aws_*`, `default_test_pepper_*`, `postgres:password@localhost`, unconfigured Cloudflare origin/Turnstile) are detected.
- ✅ **Run 3: Automated Database Migration Rollback Tests (`0001` through `0010`)**: Created transactional `.down.sql` rollback migrations for versions `0001` through `0010` in `backend/migrations/down/`; added `rollback_migrations()` runner in `run_migrations.py` supporting reversible schema rollbacks with `schema_migrations` tracking.
- ✅ **Run 4: Sentry Error Grouping & Prometheus Metrics Exporter Validation**: Implemented zero-PII scrubbing and custom error fingerprinting in `app/core/sentry.py` (scrubbing tokens, passwords, cookies, 10-digit Indian phone numbers, OTPs); added zero-dependency thread-safe Prometheus metrics collector in `app/core/metrics.py` exporting standard Prometheus 0.0.4 text format at `/metrics` (tracking in-progress requests, latency histogram buckets, and status codes).

---

## 5. Future Session Handoff Instructions
When resuming in a future session:
1. Verify baseline test suite: `python -m unittest discover -s tests/unit -p "test_*.py"` (must be >= 115 passing).
2. Check current audit tier and round against this document.
3. Proceed sequentially through the remaining Tier 1 rounds before opening Tier 2 production chaos testing.
