# JAINUNE UNIFIED API SPECIFICATION, DEPLOYMENT & TESTING ARCHITECTURE
Document Version: 1.0.0
Domain: RESTful Contracts, WebSocket Protocol, Monorepo Topology, k6 Load Validation, Production CI/CD
Target Stack: FastAPI, Supabase PostgreSQL, Redis 7, Expo React Native, Docker, GitHub Actions, Cloudflare
Compliance: Strictly Zero Emojis, Byte-Exact Schemas, Production-Grade Configurations, Zero Speculative Abstractions

---

## 1. Monorepo Project Structure & Codebase Topology

The complete directory structure for Jainune engineered for scalable development and rapid deployment (< 4 weeks):

```
jainune/
+-- .github/
|   +-- workflows/
|       +-- ci.yml                        # Automated lint, typecheck, pytest, and security scan
|       +-- deploy-prod.yml               # Automated Docker build, push, and AWS ECS/EC2 deploy
|       +-- mobile-build.yml              # Expo EAS build trigger for iOS/Android
+-- backend/
|   +-- app/
|   |   +-- core/
|   |   |   +-- config.py                 # Pydantic BaseSettings loading from .env
|   |   |   +-- database.py               # asyncpg connection pool initialization
|   |   |   +-- redis.py                  # aioredis client connection pool
|   |   |   +-- security.py               # RS256 JWT decoding, password/OTP hashing
|   |   +-- models/
|   |   |   +-- schemas/                  # Pydantic v2 request/response DTOs
|   |   |   |   +-- auth.py
|   |   |   |   +-- user.py
|   |   |   |   +-- feed.py
|   |   |   |   +-- interaction.py
|   |   |   |   +-- chat.py
|   |   |   |   +-- payment.py
|   |   |   +-- domain/                   # Domain entities and SQL mappings
|   |   +-- routers/
|   |   |   +-- auth.py                   # /v1/auth endpoints (OTP, tokens)
|   |   |   +-- onboarding.py             # /v1/onboarding (22-step flow)
|   |   |   +-- users.py                  # /v1/users (profile CRUD, preferences)
|   |   |   +-- feed.py                   # /v1/feed (BRRE people-finding engine)
|   |   |   +-- interactions.py           # /v1/interactions (likes, passes, comments)
|   |   |   +-- telemetry.py              # /v1/telemetry (implicit dwell/voice signals)
|   |   |   +-- chats.py                  # /v1/chats (conversations, messages)
|   |   |   +-- websockets.py             # /v1/ws (real-time chat, presence)
|   |   |   +-- subscriptions.py          # /v1/subscriptions (Razorpay checkout)
|   |   |   +-- media.py                  # /v1/media (presigned S3 upload URLs)
|   |   |   +-- arcade.py                 # /v1/arcade (Serendipity Wheel, Dilemmas)
|   |   +-- services/
|   |   |   +-- core_people_finder.py     # L0-L4 multi-stage reciprocal recommendation engine
|   |   |   +-- stable_marriage.py        # Gale-Shapley deferred acceptance solver
|   |   |   +-- media_processor.py        # S3 presigning, EXIF stripping, WebP convert
|   |   |   +-- payment_service.py        # Razorpay HMAC verification, order generation
|   |   |   +-- dignity_engine.py         # Thompson sampling 35-impression floor
|   |   +-- workers/
|   |   |   +-- telemetry_worker.py       # Redis stream consumer for Online EMA updates
|   |   |   +-- daily_compatible.py       # Celery cron for 00:00 IST Gale-Shapley run
|   |   |   +-- ephemeral_reaper.py       # Redis keyspace listener for 60s voice deletion
|   |   +-- dependencies.py               # FastAPI Depends: DB, Redis, CurrentUser
|   |   +-- main.py                       # FastAPI application entrypoint and middleware
|   +-- migrations/                       # Supabase / Flyway SQL migration scripts
|   |   +-- 0001_initial_schema.sql
|   |   +-- 0002_postgis_pgvector.sql
|   |   +-- 0003_rls_security_policies.sql
|   +-- tests/
|   |   +-- conftest.py                   # Pytest fixtures, test DB containers
|   |   +-- unit/
|   |   |   +-- test_reciprocal_math.py
|   |   |   +-- test_dignity_engine.py
|   |   |   +-- test_stable_marriage.py
|   |   +-- integration/
|   |   |   +-- test_auth_pipeline.py
|   |   |   +-- test_feed_endpoint.py
|   |   |   +-- test_payment_webhook.py
|   |   +-- load/
|   |       +-- k6_feed_benchmark.js      # k6 test validating 1,200 RPS sub-30ms p95
|   +-- Dockerfile                        # Multi-stage production build
|   +-- docker-compose.yml                # Local development environment
|   +-- docker-compose.prod.yml           # Production service topology
|   +-- requirements.txt
|   +-- requirements-dev.txt
+-- mobile/
|   +-- src/
|   |   +-- api/                          # Axios / Fetch client with token refresh interceptors
|   |   |   +-- client.ts
|   |   |   +-- authApi.ts
|   |   |   +-- feedApi.ts
|   |   |   +-- chatApi.ts
|   |   +-- components/
|   |   |   +-- core/                     # Hairline buttons, inputs, typography
|   |   |   +-- feed/                     # Spatial Orbit Feed, Match Cards, Voice Prompts
|   |   |   +-- arcade/                   # Serendipity Wheel, Dilemma Duel Cards
|   |   |   +-- chat/                     # Kinetic 4-phase ritual, Ephemeral Voice Player
|   |   +-- hooks/
|   |   |   +-- useFeed.ts                # Feed query with prefetch buffer management
|   |   |   +-- useTelemetry.ts           # Auto dwell time and voice play tracker
|   |   |   +-- useWebSocket.ts           # Realtime chat channel hook
|   |   +-- navigation/                   # React Navigation 6 / Expo Router
|   |   +-- screens/
|   |   |   +-- OnboardingScreen.tsx
|   |   |   +-- DiscoveryFeedScreen.tsx
|   |   |   +-- DailyCompatibleScreen.tsx
|   |   |   +-- ChatDetailScreen.tsx
|   |   |   +-- JainunePlusPaywallScreen.tsx
|   |   +-- theme/                        # Design tokens (colors, typography, 8pt spacing)
|   +-- app.json                          # Expo configuration
|   +-- package.json
+-- deploy/
|   +-- cloudflare/
|   |   +-- waf_rules.json                # Cloudflare firewall rate limits and bot rules
|   +-- nginx/
|       +-- nginx.conf                    # Reverse proxy with SSL termination and buffers
```

---

## 2. API Design Principles & Global Standards

1. **Protocol**: HTTPS / TLS 1.3 for all REST endpoints; WSS for WebSocket channels.
2. **Base URL**: `https://api.jainune.com/v1`
3. **Authentication**: Bearer Token in `Authorization` header (`Authorization: Bearer <access_token>`).
4. **Content-Type**: `application/json; charset=utf-8` (except multipart uploads for media presign).
5. **Standard Response Envelope**:
```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "meta": {
    "timestamp": "2026-09-05T00:00:00Z",
    "request_id": "req_01HPX7K98F3A2B1C"
  }
}
```
6. **Standard Error Envelope**:
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "AUTHENTICATION_FAILED",
    "message": "Invalid OTP code submitted.",
    "details": []
  },
  "meta": {
    "timestamp": "2026-09-05T00:00:00Z",
    "request_id": "req_01HPX7K98F3A2B1C"
  }
}
```

---

## 3. Core API Endpoint Specifications

### 3.1 Authentication & Onboarding

#### `POST /v1/auth/otp/request`
Initiates phone number verification by generating a 6-digit cryptographic OTP and sending via MSG91 SMS gateway.

- **Rate Limit**: 3 requests per phone per hour.
- **Request Body**:
```json
{
  "phone_number": "+919820098200"
}
```
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "phone_number": "+919820098200",
    "retry_after_seconds": 60,
    "expires_in_seconds": 180
  },
  "error": null,
  "meta": { "timestamp": "2026-09-05T00:00:00Z", "request_id": "req_01" }
}
```

#### `POST /v1/auth/otp/verify`
Validates submitted OTP using constant-time comparison against Redis HMAC. Issues RS256 JWT tokens.

- **Request Body**:
```json
{
  "phone_number": "+919820098200",
  "otp": "492018"
}
```
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "user_id": "e7b9a5c8-1122-4a55-9b22-83b56789abcd",
    "is_new_user": false,
    "onboarding_completed": true,
    "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "rt_98fa01b2c3d4e5f6...",
    "expires_in": 900
  },
  "error": null,
  "meta": { "timestamp": "2026-09-05T00:00:00Z", "request_id": "req_02" }
}
```

#### `POST /v1/auth/token/refresh`
Exchanges a valid refresh token for a fresh 15-minute access token and rotated refresh token.

- **Request Body**:
```json
{
  "refresh_token": "rt_98fa01b2c3d4e5f6..."
}
```
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJSUzI1Ni...",
    "refresh_token": "rt_new_token_value...",
    "expires_in": 900
  },
  "error": null,
  "meta": { "timestamp": "2026-09-05T00:00:00Z", "request_id": "req_03" }
}
```

---

### 3.2 Discovery, Recommendations & People Finding

#### `GET /v1/feed`
Executes the sub-25ms Behavioral Reciprocal Recommendation Engine (BRRE) pipeline. Returns top candidate batch with PostGIS geodetic distance, revealed affinity, and dignity floor candidates.

- **Headers**: `Authorization: Bearer <token>`
- **Query Parameters**:
  * `limit` (int, default=15, max=30)
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "candidates": [
      {
        "id": "c1a2b3c4-5678-490a-bcde-1234567890ab",
        "first_name": "Aanya",
        "age": 25,
        "city": "Mumbai",
        "state": "Maharashtra",
        "distance_display": "4 km away",
        "dietary_strictness": "pure_jain",
        "eats_root_vegetables": false,
        "eats_onion_garlic": false,
        "community_sect": "shwetambar_murtipujak",
        "education": "CA / CFA",
        "profession": "Investment Banking",
        "open_to_relocation": true,
        "photos": [
          {
            "id": "p1",
            "url": "https://cdn.jainune.com/users/c1a2.../photo_1.webp",
            "order": 0
          }
        ],
        "prompts": [
          {
            "id": "pr1",
            "question": "A Jain value I practice daily",
            "answer": "Navkar mantra before beginning work and strictly no dinner after sunset."
          }
        ],
        "voice_snapshot": {
          "id": "vs1",
          "audio_url": "https://cdn.jainune.com/users/c1a2.../voice_snapshot.m4a",
          "duration_seconds": 7.0
        },
        "compatibility": {
          "values_alignment_percentage": 94,
          "shared_traditions": ["Paryushan Chauviharr", "Navkar Jaap"]
        }
      }
    ],
    "batch_id": "batch_8819af92",
    "exhausted": false
  },
  "error": null,
  "meta": { "timestamp": "2026-09-05T00:00:00Z", "request_id": "req_04" }
}
```

#### `POST /v1/interactions/action`
Records an explicit interaction (like or pass). Handles likes attached to a specific prompt, photo, or voice snapshot with an optional comment.

- **Request Body**:
```json
{
  "target_user_id": "c1a2b3c4-5678-490a-bcde-1234567890ab",
  "action": "like",
  "target_element_type": "prompt",
  "target_element_id": "pr1",
  "comment": "Completely relate to Chauviharr! Where in Mumbai do you live?",
  "voice_note_id": null
}
```
- **Response `200 OK` (Immediate Match)**:
```json
{
  "success": true,
  "data": {
    "action": "like",
    "is_match": true,
    "chat_id": "chat_f9a8b7c6-1122-3344-5566-778899aabbcc",
    "match_timestamp": "2026-09-05T00:00:02Z",
    "momentum_window_hours": 72
  },
  "error": null,
  "meta": { "timestamp": "2026-09-05T00:00:02Z", "request_id": "req_05" }
}
```

#### `POST /v1/telemetry/interaction-event`
Sub-5ms async sink recording micro-dwell durations, voice listen ratios, and pass velocity for online EMA vector updates.

- **Request Body**:
```json
{
  "target_user_id": "c1a2b3c4-5678-490a-bcde-1234567890ab",
  "action": "like",
  "total_dwell_ms": 7820,
  "photo_dwell_ms": 3200,
  "prompt_dwell_ms": 4620,
  "voice_played_ratio": 1.0,
  "comment_char_count": 64
}
```
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": { "status": "buffered" },
  "error": null,
  "meta": { "timestamp": "2026-09-05T00:00:03Z", "request_id": "req_06" }
}
```

#### `GET /v1/matches/daily-compatible`
Returns the single, algorithmically locked "Most Compatible" match calculated by the nightly 00:00 IST Gale-Shapley Stable Marriage run.

- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "candidate": {
      "id": "b9c8d7e6-1234-5678-90ab-cdef12345678",
      "first_name": "Rohan",
      "age": 27,
      "city": "Ahmedabad",
      "state": "Gujarat",
      "community_sect": "shwetambar_murtipujak",
      "dietary_strictness": "pure_jain",
      "compatibility_rationale": "Highest reciprocal mutual rank in Western India cluster: shared family values, identical Chauviharr adherence, open to Mumbai/Ahmedabad relocation."
    },
    "pairing_algorithm": "gale_shapley_deferred_acceptance",
    "locked_until": "2026-09-05T23:59:59Z"
  },
  "error": null,
  "meta": { "timestamp": "2026-09-05T00:00:04Z", "request_id": "req_07" }
}
```

---

### 3.3 Interactive Features & Arcade APIs

#### `POST /v1/arcade/wheel/spin`
Consumes 1 Serendipity Wheel spin (INR 19 via instant microtransaction or included weekly token). Atomically pairs user with another spinning user in under 10ms via Redis queue.

- **Request Body**:
```json
{
  "client_nonce": "nonce_77af98"
}
```
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "outcome": "match_revealed",
    "matched_user": {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "first_name": "Kinjal",
      "city": "Surat",
      "voice_snapshot_url": "https://cdn.jainune.com/users/a1b2.../spark_sample.m4a"
    },
    "remaining_spins": 2
  },
  "error": null,
  "meta": { "timestamp": "2026-09-05T00:00:05Z", "request_id": "req_08" }
}
```

#### `GET /v1/dilemma/daily`
Fetches the active Pan-India cultural dilemma duel question of the day.

- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "dilemma_id": "duel_2026_09_05",
    "question": "At weddings, would you insist on a strictly 100% Jain catering setup with zero night-time service?",
    "option_a": "Yes, absolutely non-negotiable for traditions.",
    "option_b": "Flexible, daytime Jain setup with quiet accommodations.",
    "total_community_votes": 4820,
    "user_vote": null
  },
  "error": null,
  "meta": { "timestamp": "2026-09-05T00:00:06Z", "request_id": "req_09" }
}
```

---

### 3.4 Media & Presigned Uploads

#### `POST /v1/media/presign-upload`
Generates a cryptographically signed S3 PUT URL with strict content-type validation and 60-second expiration.

- **Request Body**:
```json
{
  "media_type": "photo",
  "content_type": "image/webp",
  "file_size_bytes": 2450000
}
```
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "upload_url": "https://jainune-media-quarantine.s3.ap-south-1.amazonaws.com/quarantine/e7b9.../f91a.webp?X-Amz-Signature=...",
    "media_id": "med_f91a2b3c4d5e",
    "s3_key": "quarantine/e7b9.../f91a.webp",
    "expires_in_seconds": 60
  },
  "error": null,
  "meta": { "timestamp": "2026-09-05T00:00:07Z", "request_id": "req_10" }
}
```

---

### 3.5 Payments & Jainune+ Subscriptions (Razorpay)

#### `POST /v1/subscriptions/order/create`
Generates a server-authoritative Razorpay payment order for Jainune+ or Serendipity Wheel packs.

- **Request Body**:
```json
{
  "plan_id": "jainune_plus_quarterly"
}
```
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "order_id": "order_NX81hp7K98F3A2",
    "amount_paisa": 99900,
    "currency": "INR",
    "key_id": "rzp_live_production_key_id",
    "plan_name": "Jainune+ Quarterly (INR 333/month)",
    "prefill": {
      "contact": "+919820098200"
    }
  },
  "error": null,
  "meta": { "timestamp": "2026-09-05T00:00:08Z", "request_id": "req_11" }
}
```

---

## 4. Real-Time WebSocket Protocol Specification

### 4.1 Connection & Ticket Handshake
To prevent ambient cookie attacks (CSWSH), connections require a single-use 30-second ticket acquired via REST:
`POST /v1/ws/ticket` -> returns `{"ticket": "tkt_8819a7fbc2..."}`.

Connect:
`WSS wss://api.jainune.com/v1/ws?ticket=tkt_8819a7fbc2...`

### 4.2 WebSocket Message Protocol (JSON Frames)

#### Client -> Server: Join Conversation Channel
```json
{
  "action": "join_chat",
  "chat_id": "chat_f9a8b7c6-1122-3344-5566-778899aabbcc"
}
```

#### Client -> Server: Send Text Message
```json
{
  "action": "send_message",
  "chat_id": "chat_f9a8b7c6-1122-3344-5566-778899aabbcc",
  "client_msg_id": "msg_local_8910",
  "content": "Jai Jinendra! Glad we matched."
}
```

#### Server -> Client: Message Delivery ACK
```json
{
  "event": "message_delivered",
  "chat_id": "chat_f9a8b7c6-1122-3344-5566-778899aabbcc",
  "client_msg_id": "msg_local_8910",
  "server_msg_id": "srv_01HPX8819",
  "created_at": "2026-09-05T00:00:10Z"
}
```

#### Server -> Client: Inbound Message Broadcast
```json
{
  "event": "new_message",
  "chat_id": "chat_f9a8b7c6-1122-3344-5566-778899aabbcc",
  "message_id": "srv_01HPX8819",
  "sender_id": "c1a2b3c4-5678-490a-bcde-1234567890ab",
  "content": "Jai Jinendra! Glad we matched.",
  "created_at": "2026-09-05T00:00:10Z"
}
```

---

## 5. Comprehensive Testing Specification & Automation

### 5.1 Pytest Unit & Reciprocal Mathematics Test Suite

```python
# backend/tests/unit/test_reciprocal_math.py
import pytest
import numpy as np

def calculate_reciprocal_score(p_a_b: float, p_b_a: float) -> float:
    return float(np.sqrt(p_a_b * p_b_a))

def test_reciprocal_geometric_collapsing():
    """Verify that asymmetric affinity collapses toward zero."""
    # User A loves User B (0.95), User B rejects User A (0.05)
    score_asymmetric = calculate_reciprocal_score(0.95, 0.05)
    # Balanced mutual interest (0.60 each)
    score_balanced = calculate_reciprocal_score(0.60, 0.60)

    assert score_asymmetric < 0.22
    assert score_balanced == 0.60
    assert score_balanced > (2.7 * score_asymmetric)

def test_dietary_dealbreaker_elimination():
    """Ensure pure Jain users never match with non-vegetarians."""
    viewer = {"diet": "pure_jain", "onion_garlic": False}
    candidate_non_veg = {"diet": "vegetarian", "onion_garlic": True}

    is_dealbreaker = (viewer["diet"] == "pure_jain" and candidate_non_veg["diet"] != "pure_jain")
    assert is_dealbreaker is True
```

### 5.2 k6 High-Throughput Load Testing Script (Sub-30ms p95 SLA)

```javascript
// backend/tests/load/k6_feed_benchmark.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 200 },  // Ramp-up to 200 VUs
    { duration: '1m',  target: 1200 }, // Peak traffic: 1,200 requests/sec
    { duration: '30s', target: 0 },    // Ramp-down
  ],
  thresholds: {
    // Hard SLA: 95% of feed requests must complete within 30ms
    http_req_duration: ['p(95)<30'],
    http_req_failed: ['rate<0.001'],    // Error rate must be under 0.1%
  },
};

const BASE_URL = 'http://api.jainune.local/v1';
const TEST_JWT = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...';

export default function () {
  const params = {
    headers: {
      'Authorization': `Bearer ${TEST_JWT}`,
      'Content-Type': 'application/json',
    },
  };

  const res = http.get(`${BASE_URL}/feed?limit=15`, params);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'latency under 30ms': (r) => r.timings.duration < 30,
    'has candidates': (r) => JSON.parse(r.body).data.candidates.length > 0,
  });

  sleep(0.1);
}
```

---

## 6. Production Deployment & Infrastructure Specification

### 6.1 Multi-Stage Production Dockerfile

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgeos-dev \
    libproj-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final Runtime Image
FROM python:3.11-slim AS runner

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgeos-c1v5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

USER nobody

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
    CMD curl -f http://localhost:8000/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--loop", "uvloop", "--http", "httptools"]
```

### 6.2 Production `docker-compose.prod.yml`

```yaml
version: '3.8'

services:
  api:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: always
    environment:
      - DATABASE_URL=postgresql://jainune_admin:${DB_PASSWORD}@supabase-db.internal:5432/postgres?sslmode=require
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis.internal:6379/0
      - RAZORPAY_KEY_ID=${RAZORPAY_KEY_ID}
      - RAZORPAY_KEY_SECRET=${RAZORPAY_KEY_SECRET}
      - AWS_S3_BUCKET=jainune-media-prod
      - AWS_REGION=ap-south-1
    ports:
      - "8000:8000"
    deploy:
      resources:
        limits:
          cpus: '3.0'
          memory: 4096M
        reservations:
          cpus: '1.0'
          memory: 1024M
    depends_on:
      - redis

  redis:
    image: redis:7.2-alpine
    restart: always
    command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}", "--maxmemory", "1536mb", "--maxmemory-policy", "allkeys-lru"]
    volumes:
      - redis_data:/data
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 2048M

  telemetry_worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: always
    command: ["python", "-m", "app.workers.telemetry_worker"]
    environment:
      - DATABASE_URL=postgresql://jainune_admin:${DB_PASSWORD}@supabase-db.internal:5432/postgres?sslmode=require
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis.internal:6379/0
    depends_on:
      - redis

volumes:
  redis_data:
```

### 6.3 Automated GitHub Actions CI/CD Pipeline (`.github/workflows/ci.yml`)

```yaml
name: Production CI/CD Pipeline

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test_and_audit:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg15
        env:
          POSTGRES_DB: jainune_test
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Setup Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install Dependencies
        run: |
          pip install --upgrade pip
          pip install -r backend/requirements.txt
          pip install -r backend/requirements-dev.txt

      - name: Security Vulnerability Scan (pip-audit & bandit)
        run: |
          pip-audit --strict
          bandit -r backend/app/ -ll

      - name: Run Pytest Test Suite
        env:
          DATABASE_URL: postgresql://test_user:test_password@localhost:5432/jainune_test
          REDIS_URL: redis://localhost:6379/0
        run: |
          pytest backend/tests/ -v --cov=backend/app --cov-report=term-missing

  deploy_production:
    needs: test_and_audit
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ap-south-1

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and Push Docker Image
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          ECR_REPOSITORY: jainune-backend
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG -t $ECR_REGISTRY/$ECR_REPOSITORY:latest backend/
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest

      - name: Deploy to AWS ECS Service
        run: |
          aws ecs update-service --cluster jainune-production --service jainune-api --force-new-deployment
```

### 6.4 Cloudflare WAF, Rate Limiting & Edge Shield Rules

| Priority | Rule Expression | Action | Justification |
| :--- | :--- | :--- | :--- |
| **1** | `(http.request.uri.path eq "/v1/auth/otp/request" and rate > 3 per 60s by ip)` | **Block (429)** | Prevents SMS gateway financial draining / OTP bombing |
| **2** | `(http.request.uri.path eq "/v1/feed" and rate > 25 per 60s by ip)` | **Managed Challenge** | Halts automated profile scrapers |
| **3** | `(ip.geoip.country ne "IN" and http.request.uri.path contains "/v1/auth")` | **Managed Challenge** | Mitigates credential stuffing from foreign botnets |
| **4** | `(http.request.uri.path eq "/v1/payments/webhook" and not ip.src in {123.108.0.0/16, 52.66.0.0/16})` | **Block (403)** | Restricts webhook endpoints to Razorpay CIDR blocks |

---

## 7. Production Environment Configuration Matrix (`.env.production.example`)

```ini
# ENVIRONMENT & RUNTIME
ENVIRONMENT=production
DEBUG=false
APP_VERSION=1.0.0
ALLOWED_ORIGINS=["https://app.jainune.com","jainune://"]

# DATABASE (SUPABASE POSTGRESQL 15+)
DATABASE_URL=postgresql://jainune_admin:SECURE_DB_PASSWORD@db.supabase.co:5432/postgres?sslmode=require
DATABASE_POOL_MIN_SIZE=5
DATABASE_POOL_MAX_SIZE=25
DATABASE_STATEMENT_TIMEOUT_MS=2000

# IN-MEMORY CACHE (REDIS 7+)
REDIS_URL=redis://:SECURE_REDIS_PASSWORD@redis.jainune.internal:6379/0
REDIS_POOL_MAX_CONNECTIONS=50

# AUTHENTICATION & SECURITY
JWT_ALGORITHM=RS256
JWT_PRIVATE_KEY_PATH=/etc/secrets/jwt_rsa.key
JWT_PUBLIC_KEY_PATH=/etc/secrets/jwt_rsa.pub
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30
OTP_PEPPER_SECRET=32_BYTE_HEX_PEPPER_STRING_HERE

# AWS ASSET STORAGE (S3 + CLOUDFLARE CDN)
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=AKIA_PRODUCTION_KEY
AWS_SECRET_ACCESS_KEY=PRODUCTION_SECRET_KEY
AWS_S3_QUARANTINE_BUCKET=jainune-media-quarantine
AWS_S3_PRODUCTION_BUCKET=jainune-media-production
CDN_PUBLIC_BASE_URL=https://cdn.jainune.com

# SMS GATEWAY (MSG91)
MSG91_AUTH_KEY=MSG91_AUTH_KEY_HERE
MSG91_OTP_TEMPLATE_ID=TEMPLATE_ID_HERE

# PAYMENT GATEWAY (RAZORPAY)
RAZORPAY_KEY_ID=rzp_live_key_id_here
RAZORPAY_KEY_SECRET=rzp_live_secret_here
RAZORPAY_WEBHOOK_SECRET=razorpay_webhook_secret_here
```
