# Comprehensive 3-Part Deep Audit & Cross-System Flow Synthesis

**Date:** September 13, 2026  
**Audited Systems:** Backend (FastAPI, asyncpg, Redis, Celery), Database (PostgreSQL 16, PostGIS, pgvector), Mobile (React Native, Expo, TypeScript), Edge & Proxy (Cloudflare WAF, Nginx), Third-Party Integrations (Razorpay, StoreKit 2, Google Play RTDN, Firebase Cloud Messaging, AWS S3).

---

## Part 1: Audit Against AUDIT.md (14 Invariants & Prior Findings)

| # | Invariant / Finding | Architectural Gate | Code Implementation & Verification | Status |
|---|---|---|---|---|
| 1 | **Admin Schema Column Alignment** | `admin.py` must query exact columns present in `users` table | `backend/app/routers/admin.py:102-210`: Non-superadmin queries explicitly select `id, phone_number, email, first_name, date_of_birth, gender, dietary_strictness, community_sect, city, state, bio, job_title, company, education, account_status, subscription_tier, trust_score, created_at, updated_at, last_active_at, location_zone, is_photo_verified, is_paused, suspend_until, deleted_at`. Sensitive vectors and tokens (`fcm_token`, `revealed_preference_vector`, `google_id`, `apple_id`) stripped for non-superadmins. | **VERIFIED** |
| 2 | **Daily Compatible Lock Lua Owner Check** | Distributed lock must be released only by the token owner | `backend/app/workers/daily_compatible.py:220-235`: Lock acquisition generates unique UUID token (`lock_token = uuid.uuid4().hex`). Finally block releases via atomic Lua script checking `redis.call("get", KEYS[1]) == ARGV[1]` before `del`. Prevents race release on task overrun. | **VERIFIED** |
| 3 | **Media Delete Retry Set** | Failed S3 media deletions must persist to durable retry set | `backend/app/routers/media.py:350-375` & `backend/app/services/account_service.py:225-240`: Failed keys during S3 delete are appended to `s3:failed_deletions` in Redis for asynchronous background drain. | **VERIFIED** |
| 4 | **Reaper Error Parsing** | Ephemeral reaper must catch S3 ClientError and parse partial batch failures | `backend/app/workers/ephemeral_reaper.py:105-135`: Catches `(BotoCoreError, ClientError, Exception)`. Parses `resp.get("Errors", [])` to separate failed keys, writes them to `s3:failed_deletions`, and updates `s3_purged = TRUE` only for successfully deleted IDs. | **VERIFIED** |
| 5 | **Two-Phase Push Notification Dedup** | Push dispatch must claim in-flight token before send and rollback on failure | `backend/app/workers/notification_worker.py:45-80`: `_check_and_lock_dedup` checks `notify:dedup:{key}` and acquires `notify:inflight:{key}` with `nx=True`. On delivery success, `_commit_dedup` sets durable key. On delivery exception, `_rollback_dedup` executes Lua compare-and-delete. | **VERIFIED** |
| 6 | **Multi-Device Session Table (`user_devices`)** | Multi-device FCM tokens must persist independently and prune on failure | `backend/app/routers/users.py:370-395` & `backend/app/services/push_notifications.py:108-160`: `user_devices` persists per-device tokens `(user_id, token, device_id, platform)`. `get_user_device_tokens` fetches all active tokens. `prune_invalid_device_token` deletes invalid/unregistered tokens across both `user_devices` and `users`. | **VERIFIED** |
| 7 | **Daily Compatible 5000-User Memory Cap** | Working set in memory must be bounded during matching runs | `backend/app/workers/daily_compatible.py:65-80`: Keyset pagination `WHERE id > $1 ORDER BY id ASC LIMIT ...` with hard cutoff `MAX_ELIGIBLE_USERS = 5000`. Prevents heap exhaustion during scale. | **VERIFIED** |
| 8 | **Canonical Single Redis Chat Channel** | WebSocket and REST endpoints must use uniform channel format | `backend/app/routers/chats.py:510-535` & `backend/app/routers/websockets.py:20-50`: REST endpoint publishes to `chat:{chat_id}`. WebSocket handler subscribes to `chat:{chat_id}`. Zero split channels. | **VERIFIED** |
| 9 | **Location Waitlist Phone Binding** | Waitlist entries must bind strictly to authenticated identity | `backend/app/routers/location.py:129-145`: Phone number is pulled directly from verified token (`current_user.get("phone_number")`). Caller cannot submit arbitrary phone numbers. | **VERIFIED** |
| 10 | **Cloudflare WAF Webhook Exemptions** | Payment webhooks must bypass browser challenges and bot mitigations | `deploy/cloudflare/waf_rules.json`: `/v1/subscriptions/webhook` and `/v1/subscriptions/store-notification` exempted from managed challenges and JS detection to allow server-to-server HTTP POSTs from Razorpay/Apple/Google. | **VERIFIED** |
| 11 | **Nginx Unbuffered WebSocket + Keepalive** | WS connections must not buffer frames and must keep connection open | `deploy/nginx/nginx.conf`: `proxy_buffering off;`, `proxy_http_version 1.1;`, `proxy_set_header Upgrade $http_upgrade;`, `proxy_read_timeout 3600s;`. | **VERIFIED** |
| 12 | **CI Healthcheck Polling Loop** | Production deployment must poll `/health` with timeout | `.github/workflows/deploy-prod.yml`: 10-iteration loop with 6s sleep verifying HTTP 200 from `/health` before traffic shift. | **VERIFIED** |
| 13 | **Mobile Build Env Injection** | CI mobile workflow must inject build secrets into `.env` | `.github/workflows/mobile-build.yml`: Environment variables (`EXPO_PUBLIC_API_URL`, `EXPO_PUBLIC_WS_URL`) injected before running EAS build / test. | **VERIFIED** |
| 14 | **Robots.txt & SEO Crawling Rules** | Search crawlers allowed on landing/legal, blocked from admin/internal | `backend/app/routers/legal.py`: `/robots.txt` endpoint allows `/`, `/terms`, `/privacy`, disallows `/admin/`, `/v1/`, `/docs`, `/openapi.json`. Proper `<meta name="robots" content="index, follow">` served on public legal pages. | **VERIFIED** |

---

## Part 2: Audit Against logical-correctness-audit (6 Pillars & 6 Boundary Archetypes)

### Pillar 1: Domain State Consistency
- **Subscription Expiration:** `payment_service.get_effective_user_tier(user_id, conn)` checks `subscription_valid_until < NOW()`. When expired, user immediately drops to `free` tier limits (10 daily likes, zero super-connects) in-flight during API calls, without waiting for the 15-minute background reaper task.
- **Account Ban / Deactivation:** `_assert_account_active(row)` in `auth.py` blocks login for `banned`, `deleted`, or `suspended` users. WebSocket handler checks `account_status in ('banned', 'deleted')` and drops connection immediately with code 4003. `interactions.py` checks target user status and returns 404 for deactivated targets.
- **Soft-Deleted User Isolation:** Soft-deleted accounts have `deleted_at IS NOT NULL` and `account_status = 'deleted'`. Excluded from:
  - Discovery Feed (`core_people_finder.py:400` filters `account_status = 'active' AND deleted_at IS NULL`)
  - Interaction Target lookups (`interactions.py:200` blocks interaction if target deleted)
  - Daily Compatible batching (`daily_compatible.py:70` filters `account_status = 'active'`)
- **Onboarding State Machine:** Users cannot reach Discovery Feed or interact without `onboarding_completed = TRUE`. Mandatory fields verified at Step 22 (`first_name`, `dob`, `gender`, `show_me`, `looking_for`, `dietary_strictness`, `community_sect`, `city`, `state`, snapped `location`, and verified `photo`).

### Pillar 2: Cross-Datastore Synchronization (PostgreSQL vs Redis)
- **Profile & Prompts Dual-Write:** On profile edit (`PATCH /me`) or prompts update (`PUT /me/prompts`), PostgreSQL transaction commits first. Upon commit, Redis cache keys `profile:{user_id}` and `feed:cache:{user_id}` are deleted immediately.
- **Swipe Quota Rollback Parity:** In `interactions.py`, if a database commit fails after incrementing the Redis like quota, the `except` block catches the exception and executes `await redis.decr(like_key)` to restore user quota parity.
- **Impression Buffering Durability:** `core_people_finder.py` buffers profile impressions in `buffer:user_impressions_48h`. Async flush uses atomic Lua `RENAME` to `temp_key`, flushes to PostgreSQL via `executemany`, and restores Redis buffer on DB error. Orphaned keys from previous crashed workers are detected and recovered via `orphan_pattern = "buffer:user_impressions_48h:flushing:*"`.
- **TTL Hygiene:** All volatile Redis keys carry strict TTLs:
  - WebSocket tickets: 30s
  - Feed cache: 3600s
  - Daily likes quota: midnight IST expiration
  - Payment locks: 30s
  - Rate limit counters: 60s sliding window

### Pillar 3: Concurrency & TOCTOU Races
- **Swipe Limit Double-Deduction:** `interactions.py:180` executes `SELECT id FROM users WHERE id = $1 FOR UPDATE` inside a database transaction, locking the caller row. Serializes concurrent swipe requests and prevents negative credit balances or exceeded daily quotas.
- **Simultaneous Mutual Match:** When User A and User B swipe right at the exact same millisecond, pair canonicalization sorts UUIDs (`pair = sorted([str(actor_id), str(target_id)])`). PostgreSQL `INSERT INTO matches ... ON CONFLICT (user_a, user_b) DO UPDATE` and `INSERT INTO chats ... ON CONFLICT (match_id) DO UPDATE` ensures exactly one match record and one chat thread exist.
- **Payment Webhook Idempotency:** Double-gated:
  1. Redis distributed locks on `lock:payment:order:{order_id}` and `lock:payment:proc:{payment_id}` with 30s TTL.
  2. Redis processed marker `payment:processed:{payment_id}` with 24-hour TTL.
  3. PostgreSQL `payment_intents` row lock `FOR UPDATE` verifying existing status is not `captured`.
- **Single-Use WebSocket Ticket:** In `websockets.py`, ticket consumption executes atomic Redis `GETDEL` (or Lua `_GETDEL_LUA`). Prevents replay of intercepted ticket tokens.

### Pillar 4: False Security Traps
- **Multi-Device Session Replacement:** Single active refresh token per account with concurrency protection. When a user logs in on Device B, Device A's old token hash is flagged in Redis (`auth:replaced_by_login:{old_token_hash}`) with 30-day TTL. When Device A presents the old token, it receives clear `401: Session expired due to login from another device` rather than a generic error or false theft alert. If an unreplaced rotated token is reused past the 15s grace window, theft detection purges all refresh tokens.
- **Rate Limiting Architecture:** Sliding-window rate limiter using Redis sorted sets. Employs IP rate limiting and subnet `/24` masking (`get_client_subnet(ip)`) to thwart distributed bot nets rotating through IP blocks.
- **Injection Sanitization:**
  - Gotra input validated against strict community gotra canonical list.
  - User profiles (bio, company, prompts) sanitized against HTML/script injection.
  - SQL queries use strictly parameterized placeholders (`$1, $2, ...`), zero dynamic string formatting of user input.

### Pillar 5: Client Protocol & State Leakage
- **WebSocket Connection Lifecycle:** `useWebSocket.ts` acquires credentials via POST `/v1/ws/ticket` (no JWT in URL). Ping/pong heartbeat runs every 30s. Reconnect backoff resets on successful connection.
- **AppState & Screen Lifecycle Cleanup:** When app transitions to background or unmounts, `AppState.addEventListener` triggers `cleanup()`: clears ping timer, clears reconnect timer, closes WebSocket connection, and removes listeners to prevent zombie socket leaks.
- **Deep-Link Intent Buffering:** `AppNavigator.tsx` implements `routeOrQueue`. Incoming push notifications and deep links received before auth check or before navigation tree mounts are safely queued in `pendingIntentRef` and dispatched once `navigationRef.isReady()`.

### Pillar 6: Third-Party SDK & Lifecycle States
- **Razorpay Webhooks:** HMAC-SHA256 signature verification over raw request body using constant-time comparison (`hmac.compare_digest`).
- **App Store / Google Play Webhooks:** Server-to-server endpoint `/v1/subscriptions/store-notification` enforces secret check via `X-Store-Webhook-Token`.
- **FCM Token Pruning:** `push_notifications.py` traps FCM invalid token responses (`UNREGISTERED`, `BAD_DEVICE_TOKEN`) and immediately invokes `prune_invalid_device_token()`, nullifying dead tokens in `user_devices` and `users`.

### Boundary Defect Archetypes Verification
- **Archetype 1 (Destructive Default Semantics):** All `DELETE` and `UPDATE` SQL queries require explicit primary keys. User-facing account deletion forces soft-delete; hard purge is restricted to admin workflows.
- **Archetype 2 (Cold-Boot vs Runtime Races):** Addressed in `AppNavigator.tsx` via `routeOrQueue` buffering.
- **Archetype 3 (Dormant Native Bridges):** `app.json` contains required native plugins: `expo-camera`, `expo-location`, `expo-notifications`, `expo-secure-store`.
- **Archetype 4 (CI vs Generated Drift):** Build workflows execute linting, type checks, and test suites directly against source files.
- **Archetype 5 (Security Defense Inversion):** If `store_webhook_secret` is empty or unset, `/v1/subscriptions/store-notification` raises HTTP 403 (fails closed).
- **Archetype 6 (Cross-Screen Contract Drift):** `MainStackParams` strictly types route arguments (`Chat: { matchId: string; otherUser: ... }`). All navigation calls pass required parameters.

---

## Part 3: Audit of Edge Cases, Loopholes, Missings & Security Vulnerabilities

### 1. Financial Audit Compliance (DPDP & RBI Regulations)
- **Mechanism:** During account purge (`purge_user_account`), personal profile and media are deleted, but financial records from `payment_intents` and `arcade_transactions` are archived to `financial_audit_logs` with a mandatory 7-year retention interval (`NOW() + INTERVAL '7 years'`). User ID on active payment records is nullified to prevent FK cascade loss.
- **Active Subscription Purge Lockout:** If a user with an active paid subscription attempts account deletion, the system blocks the hard purge and downgrades to a soft deactivation until the billing cycle expires, preventing unresolvable chargebacks.

### 2. Location Privacy & Geohash Snapping
- **Mechanism:** User coordinates submitted at onboarding (Step 11) or verification are intercepted by PostgreSQL trigger `trg_snap_user_location`. The trigger calculates the Geohash-6 centroid and stores only the centroid point. Raw device coordinates are never written to disk or returned to clients.
- **Geofenced Operations:** Location router verifies coordinates against active launch zones (Mumbai MMR, Pune PCMC, Bengaluru). Non-covered users are placed on the city waitlist bound to their authenticated phone number.

### 3. Chat Safety & Out-of-Band Contact Leakage Protection
- **Mechanism:** `chat_safety_filter.py` normalizes text with character substitution mapping (unrolling leetspeak, numbers as letters, invisible zero-width spaces). Regex filters identify phone numbers (Indian 10-digit formats with prefixes), emails, URLs, UPI handles, and competitor app names (`tinder`, `bumble`, `hinge`, `shaadi`, `jeevansathi`). Obfuscated platform references are masked with `#` before broadcast.

### 4. Ephemeral Message & Media Lifecycle
- **Mechanism:** Ephemeral chat messages expire after their TTL. Celery beat task `reap_ephemeral_media` sweeps rejected and pending media older than 1 hour, deletes quarantine S3 objects in batches, logs partial deletion errors to Redis, and marks PostgreSQL records `s3_purged = TRUE`.

---

## Part 4: Cross-System & Full-Flow Behavior Notings

```
[Mobile Client] ──── (HTTPS / TLS 1.3) ────> [Cloudflare WAF / Edge]
                                                      │
                                             (Reverse Proxy)
                                                      ▼
                                              [Nginx Ingress]
                                                      │
                                             (Unix / TCP Upstream)
                                                      ▼
                                            [FastAPI Application]
                                              │               │
                            (PostGIS / SQL)   ▼               ▼   (PubSub / Lock / Quota)
                                      [PostgreSQL 16]   [Redis Cluster]
                                              │               │
                                              ▼               ▼
                                       [Celery Workers] ──> [AWS S3 / FCM / Razorpay]
```

### Flow 1: Auth & Device Registration Flow
1. **Request:** User submits phone number or email with Turnstile token and honeypot field.
2. **Edge & Bot Defense:** Cloudflare checks Turnstile. Backend validates Turnstile, checks IP/subnet sliding-window rate limit, and verifies honeypot is empty.
3. **OTP Dispatch:** 6-digit cryptographic OTP hashed with HMAC-SHA256 and stored in Redis (`auth:otp:{phone}`, TTL 300s). Dispatched via SMS gateway.
4. **Verification:** User submits OTP. Stored hash compared via `hmac.compare_digest`.
5. **Session Issue:** JWT access token (15m expiry) and refresh token (30d expiry) issued. Refresh token hash stored in PostgreSQL `refresh_tokens`. Old session recorded in Redis (`auth:replaced_by_login:{hash}`).
6. **Device Registration:** Client calls `POST /v1/users/me/fcm-token` passing FCM token, device ID, and platform. Persisted to `user_devices` table for multi-device push routing.

### Flow 2: Onboarding & Profile Verification Flow
1. **Step Progression:** User advances through Steps 1 to 21 via sequential `PATCH /v1/onboarding/step/{N}` endpoints. Each step enforces rate limits and validates step-specific schemas.
2. **Location Snapping:** Step 11 submits coordinates. PostGIS database trigger snaps coordinates to Geohash-6 centroid point (~1.2km precision) before writing to PostgreSQL.
3. **Media Upload:** User requests presigned S3 upload URL (`POST /v1/media/upload/presign`). File uploaded directly to quarantine S3 bucket. Media processor validates magic bytes, strips EXIF metadata, scans for NSFW/face presence, and promotes approved photos to production CDN bucket.
4. **Finalization:** Step 22 confirms all mandatory fields, presence of approved photo, and location. Updates `onboarding_completed = TRUE` and `account_status = 'active'`. User behavior vector initialized.

### Flow 3: Discovery Feed & Match Engine Flow
1. **Feed Request:** Client calls `GET /v1/feed`. Checked against Redis 5-minute session cache via atomic Lua pop script.
2. **Pipeline Execution:** On cache miss, 5-stage BRRE pipeline executes PostGIS distance calculation and pgvector cosine similarity against candidate pool. Filters out blocked users, unmatched users, already swiped profiles, and inactive accounts.
3. **Impression Buffering:** Shown candidate IDs increment Redis hash `buffer:user_impressions_48h`. Flushed asynchronously to PostgreSQL via atomic Lua rename without locking caller threads.
4. **Interaction (Swipe):** Client calls `POST /v1/interactions/action`. Acquired row lock on `users` table via `FOR UPDATE`. Checks daily like limits in Redis and decrements remaining super-connect credits if applicable.
5. **Mutual Match Detection:** If mutual like detected, canonical sorted UUIDs determine `user_a` and `user_b`. PostgreSQL transaction inserts `matches` and `chats` records idempotently. Dispatches `notify_new_match` Celery task.

### Flow 4: Real-Time Chat & Media Flow
1. **Handshake:** Client calls `POST /v1/ws/ticket` to obtain a single-use 30-second random ticket.
2. **WebSocket Connect:** Client connects to `wss://api.jainune.com/v1/ws/chat/{chat_id}?ticket=wst_...`.
3. **Ticket Redemption:** Server consumes ticket atomically via Redis `GETDEL`. Validates chat membership and active account status in PostgreSQL. Subscribes to Redis pub/sub channel `chat:{chat_id}`.
4. **Message Dispatch:** User sends message via `POST /v1/chats/{chat_id}/messages`. Content evaluated by `chat_safety_filter.py`. Clean message committed to PostgreSQL `messages` table and published to Redis channel `chat:{chat_id}`.
5. **Fan-Out & Push:** Connected WebSocket clients receive real-time JSON frame. Celery worker checks if recipient is active; if offline, dispatches FCM push notification via `notification_worker` with two-phase deduplication.

### Flow 5: Subscription, Payments & Webhook Flow
1. **Order Creation:** Client requests plan purchase (`POST /v1/subscriptions/order`). Razorpay order generated; `payment_intents` record created with status `created`.
2. **Client Completion:** Client collects payment via Razorpay SDK and receives signature.
3. **Server-to-Server Webhook:** Razorpay dispatches `payment.captured` event to `POST /v1/subscriptions/webhook`.
4. **Verification & Lock:** Backend verifies HMAC-SHA256 signature using raw request bytes. Acquires Redis locks `lock:payment:order` and `lock:payment:proc`.
5. **Entitlement Activation:** PostgreSQL transaction marks `payment_intents` as `captured`, updates `users.subscription_tier` and `subscription_valid_until`, and credits bonus super-connects. Redis idempotency key set for 24 hours.

### Flow 6: Block, Report & Moderation Flow
1. **User Block:** Caller blocks user via `POST /v1/users/{id}/block`. Inserted into `user_blocks`. Match status updated to `blocked`.
2. **Thread Eviction:** Redis publishes `chat_closed` eviction frame to `chat:{chat_id}`. WebSocket handler drops both client connections with code 4003.
3. **Feed Invalidation:** Cache keys `feed:cache:{blocker_id}` and `feed:cache:{blocked_id}` deleted immediately. Future feed queries exclude both user IDs in both directions.

### Flow 7: Account Deletion & GDPR/DPDP Purge Flow
1. **Deletion Request:** User calls `DELETE /v1/users/me`. Evaluates active subscription status.
2. **Active Billing Protection:** If paid tier is active, downgrades to soft-delete (`account_status = 'deactivated'`) to preserve billing dispute records until term expires.
3. **Financial Archiving:** Financial transactions copied to `financial_audit_logs` with 7-year regulatory retention.
4. **Resource Purge:** S3 media objects deleted from quarantine and production buckets; failed keys added to `s3:failed_deletions`. Database transaction cascades deletion across `user_media`, `user_prompts`, `interactions`, `matches`, `chats`, and `users`. Redis cache and rate limit keys purged via scan.
