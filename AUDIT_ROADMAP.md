# Jainune Production Audit Roadmap & Handoff Guide

## 1. Audit Strategy Overview
Production readiness divided into two sequential tiers:
- **Tier 1: Code Logic & Functional Hardening** (Resolving logic traps, race conditions, type mismatches, and schema regressions).
- **Tier 2: Real-World Production Chaos & Resilience Hardening** (~20–30 domain audits testing infrastructure, load, security, and third-party failovers).

---

## 2. Current Progress Checkpoint
- **Status**: Rounds 1–5 complete.
- **Test Suite**: 124 unit tests passing with 0 errors and 0 regressions.
- **Git Commit**: Round 5 pushed on `main`.
- **Domains Audited So Far**:
  - Dignity Engine & report brigading defense.
  - PostGIS location verifier & anti-spoofing coordinates.
  - Razorpay payment verification & multiprovider idempotency.
  - Media uploads, S3 EXIF stripping, and atomic photo reordering.
  - WebSocket session validation (caller/recipient account status gates).
  - Admin moderation, refresh token purging, and Redis session cleanup.
  - Chat safety filters & recipient status validation.
  - Celery notification worker column compatibility.
  - `liked-me` paywall preservation & target user ID masking.
  - Serendipity wheel spin speed-chat match/chat creation.
  - Ephemeral reaper stale match expiration & chat closure sync.
  - FCM v1 string typing and CDN URL formatting.
  - **Round 5**: Auth lifecycle gates for banned/deleted/suspended users across all providers (phone OTP, email OTP, Google, Apple), signup concurrency `ON CONFLICT` race mitigation, token refresh inactive user purging, profile update & unblock feed cache purging, and interactions target profile existence validation.

---

## 3. Tier 1: Remaining Code Logic Audits (4 Passes Remaining)
Targeting absolute zero remaining logic defects in source files:
- **Round 5 [COMPLETED]**:
  - `auth.py`: Banned/deleted/suspended account gates, signup concurrency duplicate handling, refresh token account check.
  - `users.py` & `location.py`: Feed cache invalidation on profile mutations, unblocking self-guard, location coordinate change cache purge.
  - `interactions.py`: Target profile existence & active status verification prior to credits deduction.
- **Round 6**:
  - `backend/app/routers/legal.py` & DPDP export format compliance, data anonymization queries.
  - `backend/app/workers/daily_compatible.py`: Gale-Shapley stable marriage pairing edge cases with uneven preference lists.
- **Round 7**:
  - Mobile TypeScript store edge cases (`authStore.ts`, `onboardingStore.ts`, `billingService.ts`), offline state persistence, and unhandled Promise rejections.
- **Round 8**:
  - `backend/app/routers/arcade.py` & `app/services/dignity_engine.py`: Dilemma voting race conditions, badge award quotas.
- **Round 9**:
  - Final end-to-end integration pass across full auth -> onboarding -> feed -> chat -> payment lifecycle.

---

## 4. Tier 2: Real-World Production Hardening (20–30 Domain Audits)

### Phase 1: Load, Concurrency & State Pressure (4–5 Runs)
- 10,000 concurrent WebSocket connections stress test.
- Asyncpg database connection pool exhaustion under 500 req/s bursts.
- Redis pub/sub memory leak and channel backlog audit.
- High-concurrency wallet deduction races (preventing double-spend on credits/tokens).

### Phase 2: Third-Party Failures & Webhook Chaos (5–6 Runs)
- **Razorpay**: Dropped webhooks, delayed payment confirmations, forged webhook signatures, and refund webhooks.
- **MSG91**: Complete SMS gateway downtime, timeout retry storms, and Indian DLT template rejection fallbacks.
- **Apple StoreKit & Google Play Billing**: Subscription grace periods, billing retries, account holds, and refund revocations.
- **FCM / APNs**: Stale/invalid device token cleanup worker, Apple APNs bad device token handling.

### Phase 3: PostGIS Spatial & pgvector Scale (3–4 Runs)
- Benchmark spatial KNN queries (`<->` operator) with 100,000 mock user points.
- Verify GIST index utilization with combined attribute filters (age, sect, diet).
- Test HNSW / IVFFLAT pgvector index rebuilds without locking read queries.

### Phase 4: Pentest, OWASP & Attack Surface (5–6 Runs)
- Comprehensive IDOR audit: verify all UUID endpoints check caller ownership.
- Rate limit evasion tests via header manipulation (`X-Forwarded-For` spoofing).
- SQL injection / PostGIS query string audit.
- Malicious media payload tests (ZIP bombs, corrupted WebP headers, EXIF GPS leaks).

### Phase 5: Mobile Real-Device Stress & Native Edge Cases (5–7 Runs)
- Low-memory terminations during camera capture and photo upload on budget Android devices.
- Mid-flow permission revokes (location, notifications, camera).
- App backgrounding / foregrounding during active WebSocket chat or checkout.
- Seamless network handoffs (Wi-Fi to 4G/5G, flight mode, packet loss).

### Phase 6: Infrastructure, CI/CD & Deployment (3–4 Runs)
- Docker image minimization and non-root security container execution.
- Production environment variable auditing (ensuring no hardcoded defaults).
- Automated database migration rollback tests (`0001` through `0010`).
- Sentry error grouping and Prometheus metrics exporter validation.

---

## 5. Future Session Handoff Instructions
When resuming in a future session:
1. Verify baseline test suite: `python -m unittest discover -s tests/unit -p "test_*.py"` (must be >= 115 passing).
2. Check current audit tier and round against this document.
3. Proceed sequentially through the remaining Tier 1 rounds before opening Tier 2 production chaos testing.
