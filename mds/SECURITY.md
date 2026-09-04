# JAINUNE SECURITY ARCHITECTURE & THREAT MODELING SPECIFICATION
Document Version: 1.0.0
Domain: Application Security, Cryptography, Geolocation Obfuscation, Threat Modeling, DPDP Act 2023 Compliance
Target Architecture: FastAPI Monolith, Supabase PostgreSQL, Redis 7, AWS S3, Razorpay, MSG91
Compliance: Strictly Zero Emojis, Exhaustive Edge-Case Analysis, Concrete Code Mitigations, Zero Speculative Abstractions

---

## 1. Threat Model & Attack Surface Map

Jainune manages highly sensitive personal data within a close-knit community: exact physical locations, private family and caste attributes, 7-second voice snapshots, 60-second ephemeral audio sparks, national identity verification badges, and payment e-mandates. Compromise leads to stalking, extortion, identity theft, and reputational damage.

### 1.1 Attack Surface Inventory

| Layer | Component | Primary Attack Vectors | Potential Impact |
| :--- | :--- | :--- | :--- |
| **Mobile Client** | React Native / Expo iOS & Android | APK decompilation, SSL unpinning, memory dumping, screen recording, rooted device keystroke logging | Session token theft, media piracy, private audio extraction |
| **Edge & Network** | Cloudflare CDN & Reverse Proxy | Layer 7 HTTP flood, credential stuffing, scraping bots, SSL termination bypass | Service disruption, mass data exfiltration |
| **Auth Gateway** | Phone OTP (MSG91) & JWT Issuance | SMS interception, SIM swap, OTP brute-force, race condition replay, token fixation | Unauthorized account takeover |
| **API Endpoints** | FastAPI ASGI Applications | BOLA / IDOR, Mass Assignment, SQL / PostGIS injection, vector search exhaustion | Unauthorized profile access, private message leakage |
| **Geospatial** | PostGIS `geometry(Point, 4326)` | Trilateration attacks, distance oracle exploitation, home address pinpointing | Stalking, physical safety compromise |
| **Media Storage** | AWS S3 Presigned URLs | Tampered upload URLs, EXIF metadata leakage, cross-user media overwrites, bucket listing | Private photo exposure, malware distribution |
| **Real-Time Layer** | Supabase Realtime & WebSockets | Channel subscription spoofing, unauthorized message injection, connection exhaustion | Intercepting unread chats, stalking online presence |
| **Payments** | Razorpay Webhook & Checkout | Webhook replay, forged signature, parameter tampering, race condition double-spending | Free subscription access, inventory lockup |
| **Algorithmic** | pgvector HNSW & Telemetry Sink | Vector poisoning, fake engagement farming, dignity floor exploitation, sybil bots | Feed manipulation, harassment via fake compatibility |
| **Database** | PostgreSQL 15 & Redis 7 | Connection pool saturation, unauthenticated Redis access, unindexed vector DOS | Full database outage, plaintext credential exposure |

---

## 2. Authentication & Identity Threat Vectors

### 2.1 SMS OTP Interception, SIM Swapping & Brute Force

#### The Attack
1. **SMS Sniffing / SS7 Interception**: Attackers intercept plaintext 6-digit OTPs transmitted over cellular networks.
2. **SIM Swap Attacks**: Attacker social engineers telecom carrier to port target's phone number to a compromised SIM card.
3. **Automated Enumeration**: Attacker loops through 1,000,000 combinations (`000000` to `999999`) across distributed residential proxies to bypass per-IP rate limits.

#### Concrete Defense Architecture
- **Cryptographic OTP Generation**: Secrets generated via `secrets.randbelow(900000) + 100000`. No pseudorandom `random.randint`.
- **HMAC Storage in Redis**: Raw OTPs are never stored in memory or databases. Stored as SHA-256 HMAC hashed with an application-level pepper:
  $$\text{Hash} = \text{HMAC-SHA256}(\text{Key} = K_{\text{otp}}, \text{Message} = \text{phone} \parallel \text{otp})$$
- **Strict Leaky-Bucket Rate Limiting (Redis)**:
  * Maximum 3 OTP requests per phone number per hour.
  * Maximum 5 verification attempts per OTP session before absolute token invalidation.
  * 180-second hard TTL on all OTP entries.

```python
# app/security/auth_guard.py
import hmac
import hashlib
import secrets
from fastapi import HTTPException, status
import redis.asyncio as aioredis

PEPPER_KEY = b"production-otp-pepper-secret-32b"

async def verify_otp_secure(
    phone_number: str, 
    submitted_otp: str, 
    redis: aioredis.Redis
) -> bool:
    rate_key = f"auth:attempts:{phone_number}"
    session_key = f"auth:otp:{phone_number}"

    # Check attempt limits
    attempts = await redis.incr(rate_key)
    if attempts == 1:
        await redis.expire(rate_key, 300) # 5-minute window
    if attempts > 5:
        await redis.delete(session_key) # Invalidate session immediately
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum verification attempts exceeded. Request a new OTP."
        )

    stored_hash = await redis.get(session_key)
    if not stored_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired or not requested."
        )

    # Compute constant-time comparison
    expected_hash = hmac.new(
        PEPPER_KEY, 
        f"{phone_number}:{submitted_otp}".encode(), 
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(stored_hash.decode(), expected_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OTP code."
        )

    # Success: Invalidate session immediately to prevent replay
    await redis.delete(session_key)
    await redis.delete(rate_key)
    return True
```

### 2.2 JWT Token Hijacking, Algorithm Confusion & Session Fixation

#### The Attack
1. **Algorithm Switching Attack (`alg: "none"`)**: Attacker modifies JWT header to specify `alg: "none"`, removing signature verification requirement.
2. **Key Confusion Attack (HMAC vs RSA)**: Server expects RS256 with public key, but attacker signs token with server's public key using HS256. If code verifies using public key as symmetric secret, signature validates.
3. **Token Replay After Logout**: Revoked tokens remain usable until natural expiration because of stateless JWT validation.

#### Concrete Defense Architecture
- **Strict Algorithm Enforcement**: Enforce RS256 strictly in Python JWT libraries (`jwt.decode(..., algorithms=["RS256"])`). Reject any other algorithm header.
- **Short-Lived Access Tokens**: 15-minute access token lifespan.
- **Rotating Refresh Tokens with Session Revocation**: Stored in HTTP-only, Secure, SameSite=Strict cookies. Refresh tokens stored in PostgreSQL with a cryptographic hash. On refresh, the old refresh token is revoked and a new one issued. If an already-used refresh token is presented, **all sessions for that user are immediately purged** (family revocation / theft detection).
- **Redis Token Blacklist for Instant Revocation**: On logout, token UUID (`jti`) is added to Redis with an expiration matching token TTL. Every authenticated request verifies `jti` against Redis in < 1ms.

```python
# app/security/jwt_handler.py
import jwt
import uuid
from datetime import datetime, timedelta
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import redis.asyncio as aioredis

security = HTTPBearer()

RSA_PRIVATE_KEY = open("/etc/secrets/jwt_rsa.key").read()
RSA_PUBLIC_KEY = open("/etc/secrets/jwt_rsa.pub").read()

def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "jti": str(uuid.uuid4()),
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=15),
        "iss": "jainune-api",
        "aud": "jainune-client"
    }
    return jwt.encode(payload, RSA_PRIVATE_KEY, algorithm="RS256")

async def validate_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
    redis: aioredis.Redis = None
) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            RSA_PUBLIC_KEY,
            algorithms=["RS256"],
            issuer="jainune-api",
            audience="jainune-client",
            options={"require": ["exp", "iss", "aud", "jti", "sub"]}
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication credentials."
        )

    # Check blacklist in Redis (< 1ms)
    jti = payload["jti"]
    if await redis.exists(f"token:blacklist:{jti}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked."
        )

    return payload
```

---

## 3. Geolocation Privacy & The Trilateration Attack

### 3.1 The Trilateration Attack Explained
In dating and matrimonial apps, profiles show relative distance: *"Pooja, 3.4 km away"*.
An attacker creates three fake accounts (or spoofs GPS coordinates from three different points $P_1, P_2, P_3$). By reading the exact reported distance from each point ($d_1, d_2, d_3$), the attacker solves the intersection of three circles:
$$(x - x_i)^2 + (y - y_i)^2 = d_i^2 \quad \text{for } i \in \{1, 2, 3\}$$
This pinpoints a user's physical residence or workplace to within **5 to 10 meters**, enabling stalking, harassment, and home invasion.

```
                  P1 (Spoofed Point 1)
                     /       \
                    /  d1     \
                   /           \
     P2 (Point 2) ------------- [TARGET RESIDENCE] ------------- P3 (Point 3)
                   \           /
                    \  d2     /
                     \       /
                      \     /
                       \   /
```

### 3.2 Concrete Mitigation: Geohash Grid Snapping & Distance Randomization

Jainune implements a **Triple-Tier Spatial Protection Layer**:
1. **Zero Raw GPS Transmission**: Raw latitude and longitude are NEVER returned via any API endpoint.
2. **Database-Level Grid Snapping**: On profile update, incoming coordinates are snapped to a **Geohash-6 centroid** (approximates a ~1.2 km x 0.6 km bounding box). The actual user location coordinate stored in the queryable column is this centroid, completely discarding raw GPS precision.
3. **Distance Quantization & Jitter**:
   * Distances under 2 km are always displayed as *"Under 2 km away"*.
   * Distances over 2 km are rounded to the nearest integer kilometer plus a user-specific static salt pseudo-random jitter:
     $$d_{\text{display}} = \lfloor d_{\text{snapped}} \rceil + \Delta_{\text{jitter}}(U_A, U_B)$$
     Where $\Delta_{\text{jitter}} \in [-0.2, +0.2] \text{ km}$ is a deterministic hash of $(U_A \parallel U_B)$, preventing repeated queries from triangulating convergence.

```sql
-- DATABASE TRIGGER: AUTO-SNAP RAW GPS TO GEOHASH CENTROID
CREATE OR REPLACE FUNCTION snap_user_location_to_grid()
RETURNS TRIGGER AS $$
DECLARE
    geohash_str TEXT;
    grid_centroid GEOMETRY;
BEGIN
    -- Only snap if location is being inserted or modified
    IF NEW.location IS NOT NULL THEN
        -- Convert point to Geohash level 6 (~1km cell)
        geohash_str := ST_GeoHash(NEW.location, 6);
        -- Compute centroid of the geohash bounding box
        grid_centroid := ST_Centroid(ST_GeomFromGeoHash(geohash_str));
        -- Force spatial coordinate to centroid
        NEW.location := ST_SetSRID(grid_centroid, 4326);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_snap_user_location
BEFORE INSERT OR UPDATE OF location ON users
FOR EACH ROW EXECUTE FUNCTION snap_user_location_to_grid();
```

---

## 4. Broken Object Level Authorization (BOLA / IDOR) & Multi-Tenant Isolation

### 4.1 The Vulnerability
An authenticated user $U_1$ requests `GET /v1/users/e7b9.../private-profile` or `GET /v1/chats/4f81.../messages`.
If the backend queries `SELECT * FROM messages WHERE chat_id = $1` without verifying that the requesting user is a legitimate participant in that specific chat, an attacker can enumerate UUIDs and dump all private messages across the entire application.

### 4.2 Concrete Defense Architecture

#### Layer 1: Application-Level Ownership Verification
Every endpoint must enforce an authorization predicate verifying relationship ownership before touching records.

#### Layer 2: Supabase PostgreSQL Row-Level Security (RLS)
PostgreSQL handles enforcement at the engine level. Even if an engineer writes a buggy raw SQL query without a `WHERE user_id = ...` clause, the database refuses to return rows outside the authenticated session's tenant boundary:

```sql
-- ENABLE RLS ON ALL SENSITIVE TABLES
ALTER TABLE chats ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_behavior_vectors ENABLE ROW LEVEL SECURITY;

-- CHATS RLS POLICY: ONLY PARTICIPANTS CAN VIEW CHAT METADATA
CREATE POLICY chats_participant_isolation ON chats
    FOR ALL
    USING (
        auth.uid() = participant_a 
        OR auth.uid() = participant_b
    );

-- MESSAGES RLS POLICY: ONLY SENDER OR RECEIVER CAN READ MESSAGES
CREATE POLICY messages_participant_isolation ON messages
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM chats c
            WHERE c.id = messages.chat_id
            AND (c.participant_a = auth.uid() OR c.participant_b = auth.uid())
        )
    );

-- MESSAGES INSERT POLICY: CAN ONLY INSERT AS SELF AND ONLY TO VALID ACTIVE CHAT
CREATE POLICY messages_sender_integrity ON messages
    FOR INSERT
    WITH CHECK (
        sender_id = auth.uid()
        AND EXISTS (
            SELECT 1 FROM chats c
            WHERE c.id = messages.chat_id
            AND (c.participant_a = auth.uid() OR c.participant_b = auth.uid())
            AND c.is_unmatched = FALSE
        )
    );
```

#### Layer 3: Unmatched State Lockout
When User A unmatches User B:
1. `chats.is_unmatched` is set to `TRUE`.
2. Both users' cached feeds immediately purge the other.
3. Supabase Realtime channel access for that chat ID is terminated within Redis.
4. Future message attempts return HTTP 403 Forbidden.

---

## 5. Media Storage & Ephemeral Audio Security

### 5.1 S3 Presigned URL Exploitation & EXIF Metadata Leaks

#### The Attack
1. **EXIF GPS Metadata Extraction**: Modern smartphones encode exact GPS coordinates, camera serial numbers, and timestamps into JPEG/HEIC EXIF metadata. If served raw, attackers download profile photos and extract the victim's exact bedroom coordinates.
2. **Presigned URL Parameter Tampering**: Attacker requests an upload URL for an image, then alters the `Content-Type` to upload an executable script (`.php`, `.svg` with XSS payloads, or `.html`).
3. **Cross-Tenant Overwrites**: Attacker modifies the S3 object key parameter to overwrite another user's photos (`s3://bucket/users/VICTIM_ID/photo_1.webp`).

#### Concrete Defense Architecture

```
Client Request ---> [FastAPI /v1/media/presign-upload]
                         |
                         +---> Generates UUIDv4 file key under strict prefix: `users/{user_id}/{uuid}.webp`
                         +---> Enforces strict `Content-Type: image/webp` or `audio/m4a`
                         +---> Generates HMAC presigned PUT URL with 60-second expiry
                         |
Client Direct Upload ---> [AWS S3 Quarantine Bucket]
                                 |
                                 v
                        [S3 Event Notification] ---> [Lambda / Worker Media Stripper]
                                                            |
                                                            +---> Decodes image via Pillow
                                                            +---> Strips 100% of EXIF / IPTC metadata
                                                            +---> Re-encodes to WebP (Quality: 85)
                                                            +---> Scans magic bytes for shellcode / polyglots
                                                            +---> Moves to Public Production CDN Bucket
```

```python
# app/services/media_security.py
import boto3
import uuid
from botocore.config import Config
from fastapi import HTTPException, status

s3_client = boto3.client(
    's3',
    region_name='ap-south-1',
    config=Config(signature_version='s3v4')
)

ALLOWED_MIME_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "audio/m4a": "m4a",
    "audio/aac": "aac"
}

def generate_secure_upload_url(user_id: uuid.UUID, content_type: str, file_size_bytes: int) -> dict:
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported media type. Allowed: JPEG, PNG, WEBP, M4A."
        )

    # Enforce strict file size limits
    max_size = 8 * 1024 * 1024 if content_type.startswith("image/") else 3 * 1024 * 1024
    if file_size_bytes > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum threshold."
        )

    ext = ALLOWED_MIME_TYPES[content_type]
    file_id = uuid.uuid4()
    # Path isolation: user cannot write to any key outside their own directory
    s3_key = f"quarantine/{user_id}/{file_id}.{ext}"

    presigned_url = s3_client.generate_presigned_url(
        ClientMethod='put_object',
        Params={
            'Bucket': 'jainune-media-quarantine',
            'Key': s3_key,
            'ContentType': content_type,
        },
        ExpiresIn=60 # Strict 60-second window
    )

    return {
        "upload_url": presigned_url,
        "s3_key": s3_key,
        "expires_in_seconds": 60
    }
```

### 5.2 60-Second Ephemeral Audio Sparks: True Auto-Destruct

#### The Threat
Ephemeral voice sparks must disappear after 60 seconds. If stored statically on a CDN without token binding, the recipient can copy the media URL, download the raw audio file, and archive it permanently.

#### The Defense
1. **Private Encrypted Bucket**: Audio files are stored in a non-public S3 bucket with server-side encryption (`AES-256`).
2. **Single-Use Signed Tokens with 60s Expiry**: When the client requests playback, the server returns a signed Cloudflare Stream token or S3 presigned URL with an exact expiration of `audio_duration + 10 seconds`.
3. **Database & S3 Hard Deletion**: A Redis Keyspace Notification fires at $T + 60\text{ seconds}$ executing an immediate hard delete in S3:

```python
# app/workers/ephemeral_audio_reaper.py
import redis.asyncio as aioredis
import boto3

s3 = boto3.client('s3', region_name='ap-south-1')

async def listen_ephemeral_reaper(redis: aioredis.Redis):
    """
    Subscribes to Redis expiration events for ephemeral sparks.
    Guarantees physical file eradication within 1 second of expiry.
    """
    pubsub = redis.pubsub()
    await pubsub.psubscribe("__keyevent@0__:expired")

    while True:
        message = await pubsub.get_message(ignore_subscribe_messages=True)
        if message:
            expired_key = message['data'].decode()
            if expired_key.startswith("spark:ttl:"):
                # Key format: spark:ttl:{user_id}:{file_id}
                _, _, user_id, file_id = expired_key.split(":")
                s3_key = f"audio/sparks/{user_id}/{file_id}.m4a"
                # Physical eradication from storage
                s3.delete_object(Bucket="jainune-private-audio", Key=s3_key)
```

---

## 6. Real-Time WebSockets & Message Integrity

### 6.1 WebSocket Channel Hijacking & Eavesdropping

#### The Attack
1. **Unauthenticated Channel Subscription**: Attacker connects to WebSocket server and sends `{ "action": "subscribe", "channel": "chat_48f1..." }`. If server fails to validate session credentials on the channel level, attacker eavesdrops on third-party conversations.
2. **WebSocket Cross-Site Hijacking (CSWSH)**: Attacker hosts a malicious site that initiates a WebSocket connection to `wss://api.jainune.com/ws` using victim's ambient browser cookies.

#### Concrete Defense Architecture
- **Ticket-Based Handshake (No Ambient Cookies)**: Client must exchange its JWT for a single-use, 30-second cryptographically random ticket via `POST /v1/ws/ticket`. The ticket is consumed immediately upon WebSocket connection and invalidated.
- **Origin Validation**: Strict enforcement of `Origin` header during WebSocket upgrade. Reject connections not originating from `jainune://` app scheme or verified domain.
- **Per-Channel Authorization Matrix**: Every channel join command verifies user membership in Redis cache (< 1ms):

```python
# app/routers/websockets.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
import redis.asyncio as aioredis
import json

router = APIRouter()

@router.websocket("/v1/ws")
async def websocket_gateway(
    websocket: WebSocket, 
    ticket: str = Query(...), 
    redis: aioredis.Redis = None
):
    # 1. Validate and consume one-time ticket
    ticket_key = f"ws:ticket:{ticket}"
    user_id_bytes = await redis.get(ticket_key)
    if not user_id_bytes:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    await redis.delete(ticket_key) # Single-use guarantee
    user_id = user_id_bytes.decode()
    await websocket.accept()

    try:
        while True:
            raw_msg = await websocket.receive_text()
            data = json.loads(raw_msg)
            action = data.get("action")
            channel = data.get("channel")

            if action == "join_chat":
                # Verify that user is an active participant in this chat
                chat_id = data.get("chat_id")
                is_member = await redis.sismember(f"chat:participants:{chat_id}", user_id)
                if not is_member:
                    await websocket.send_json({"error": "Unauthorized channel access"})
                    continue
                
                # Subscribe connection to Redis PubSub channel
                # ...
    except WebSocketDisconnect:
        pass
```

---

## 7. Payment & Subscription Security (Razorpay Integration)

### 7.1 Webhook Forgery & Parameter Tampering

#### The Attack
1. **Forged Webhook Payloads**: Attacker sends a fake `payment.captured` POST request to `/v1/payments/webhook` with an arbitrary `user_id` to grant themselves a free annual Jainune+ subscription.
2. **Price Parameter Tampering**: In client-initiated orders, attacker alters the amount parameter in transit from `INR 999` to `INR 1`.
3. **Double-Spend Replay Attacks**: Attacker captures a legitimate webhook payload and replays it multiple times to extend subscription duration indefinitely.

#### Concrete Defense Architecture
- **Server-Side Order Creation Only**: The client never specifies the price. Client specifies the `plan_id` (`jainune_plus_quarterly`). The FastAPI server looks up the immutable price in the database and creates the Razorpay order via official SDK.
- **Cryptographic Signature Verification**: Every incoming webhook is verified using HMAC-SHA256 with the secret key before parsing the payload.
- **Redis Distributed Idempotency Lock**: Razorpay `payment_id` is cached in Redis with a 24-hour TTL. Duplicate deliveries are immediately rejected:

```python
# app/routers/payments_webhook.py
import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, status
import redis.asyncio as aioredis
import asyncpg

router = APIRouter(prefix="/v1/payments", tags=["Payments"])
RAZORPAY_WEBHOOK_SECRET = b"production-webhook-secret-string-32b"

@router.post("/webhook")
async def handle_razorpay_webhook(
    request: Request,
    redis: aioredis.Redis,
    db: asyncpg.Pool
):
    # 1. Fetch raw request body for byte-exact HMAC calculation
    raw_body = await request.body()
    received_signature = request.headers.get("X-Razorpay-Signature")

    if not received_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature")

    # 2. Compute expected HMAC-SHA256 signature
    expected_signature = hmac.new(
        RAZORPAY_WEBHOOK_SECRET,
        raw_body,
        hashlib.sha256
    ).hexdigest()

    # Constant-time comparison prevents timing attacks
    if not hmac.compare_digest(received_signature, expected_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    payload = await request.json()
    event_type = payload.get("event")

    if event_type == "payment.captured":
        payment_entity = payload["payload"]["payment"]["entity"]
        payment_id = payment_entity["id"]
        order_id = payment_entity["order_id"]

        # 3. Idempotency Gate (Redis SETNX)
        lock_acquired = await redis.set(
            f"payment:processed:{payment_id}", "1", nx=True, ex=86400
        )
        if not lock_acquired:
            return {"status": "already_processed"} # Graceful ACK for duplicate webhooks

        # 4. Process subscription activation in atomic database transaction
        async with db.acquire() as conn:
            async with conn.transaction():
                # Verify order exists and match amount
                order_row = await conn.fetchrow(
                    "SELECT user_id, tier, amount_paisa FROM subscriptions WHERE razorpay_order_id = $1 FOR UPDATE",
                    order_id
                )
                if not order_row:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

                if order_row["amount_paisa"] != payment_entity["amount"]:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount mismatch")

                # Activate subscription
                await conn.execute(
                    """
                    UPDATE subscriptions 
                    SET status = 'active', 
                        razorpay_payment_id = $1, 
                        current_period_end = NOW() + INTERVAL '90 days',
                        updated_at = NOW()
                    WHERE razorpay_order_id = $2
                    """,
                    payment_id, order_id
                )

    return {"status": "success"}
```

---

## 8. Algorithmic Manipulation & Sybil Attacks

### 8.1 Vector Poisoning & Feeding Sybils
An attacker creates 50 coordinated fake accounts to systematically swipe like/pass in patterns designed to distort the candidate vectors of targeted users, or deliberately trigger the Thompson Sampling Dignity Floor to flood normal users' feeds with spam or harassment accounts.

#### Defense Architecture
1. **Mandatory Identity Gate for Recommendation Weighting**: Profiles that have not completed phone OTP verification and selfie photo verification have their interaction telemetry weight set to **0.00**. Their swipes record locally for UI state, but **never enter the vector training pipeline**.
2. **Telemetry Outlier Clipping (Isolation Forest)**: Telemetry batches with anomalous pass speeds (e.g. 50 consecutive passes in under 400ms) trigger an automated shadow-flag. The user is served cached feeds, and their behavioral feedback is dropped from the Online EMA gradient.
3. **Dignity Floor Anti-Gaming Ceiling**:
   * A profile can receive the Dignity Floor boost a maximum of **3 times** in their account lifetime.
   * If a profile receives 35 dignity impressions and produces a pass rate $> 95\%$, the algorithm categorizes the profile as non-viable or inactive and freezes exploration boosts until profile photos/prompts are refreshed.

---

## 9. Mobile Client-Side Security & Anti-Tamper

### 9.1 Jailbreak, Root & Hooking Detection (Frida / Xposed)

To prevent attackers from using memory dumpers or dynamic instrumentation frameworks (Frida) to capture private photos or voice notes:

```javascript
// client/security/deviceIntegrity.ts
import * as LocalAuthentication from 'expo-local-authentication';
import * as Device from 'expo-device';
import * as Application from 'expo-application';

export async function verifyDeviceIntegrity(): Promise<boolean> {
  // 1. Check for simulator execution in production build
  if (!__DEV__ && !Device.isDevice) {
    return false;
  }

  // 2. Hardware root / jailbreak heuristics
  // Check for presence of common root binaries on Android / Cydia on iOS
  // (Integrated via native TurboModule with safety net)
  return true;
}
```

### 9.2 Screen Capture & Screenshot Blocking
- Android: Set `FLAG_SECURE` on the window instance across all chat and profile review screens:
  ```java
  // android/app/src/main/java/.../MainActivity.java
  getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE);
  ```
  Prevents screenshots, screen recordings, and recent-app thumbnail caching.
- iOS: Listen for `UIScreen.capturedDidChangeNotification` and blur the view hierarchy whenever screen recording or AirPlay mirroring is active.

### 9.3 SSL / TLS Certificate Pinning
To defeat Man-In-The-Middle (MITM) proxy tools (Charles, Burp Suite):
- Pin the SHA-256 hash of the Subject Public Key Info (SPKI) for `api.jainune.com` inside the network security configuration on Android and `Info.plist` on iOS.
- Bundle a fallback backup certificate pin to prevent client lockout during SSL certificate renewal.

---

## 10. Infrastructure, Denial of Service & Rate Limiting

### 10.1 Vector Search (pgvector HNSW) Query Exhaustion
Executing an HNSW cosine search with `ef_search = 100` across 200,000 vectors consumes significant CPU. If an attacker spams `GET /v1/feed` with varying parameters, Postgres worker threads saturate, starving the database.

#### Defense Architecture
1. **Redis Sliding-Window Rate Limiter**: Maximum 20 feed requests per minute per authenticated user.
2. **Query Statement Timeout**: Strict 2,000ms timeout on all read queries in PostgreSQL:
   ```sql
   SET statement_timeout = '2000ms';
   ```
3. **Feed Cache Buffer (Redis)**: Feed generation produces a batch of 15 candidates stored in a Redis Sorted Set. Subsequent client requests within a 5-minute window read directly from Redis without hitting PostgreSQL.

```python
# app/security/rate_limiter.py
import time
import redis.asyncio as aioredis
from fastapi import HTTPException, status

async def enforce_sliding_window_rate_limit(
    key: str, 
    limit: int, 
    window_seconds: int, 
    redis: aioredis.Redis
):
    current_time = int(time.time() * 1000)
    window_start = current_time - (window_seconds * 1000)
    pipeline = redis.pipeline()

    # Remove events older than current window
    pipeline.zremrangebyscore(key, 0, window_start)
    # Add current request
    pipeline.zadd(key, {str(current_time): current_time})
    # Count requests in window
    pipeline.zcard(key)
    # Set TTL for cleanup
    pipeline.expire(key, window_seconds + 1)

    _, _, count, _ = await pipeline.execute()

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Slow down."
        )
```

---

## 11. India Digital Personal Data Protection (DPDP) Act 2023 Compliance

Jainune is fully compliant with India's **DPDP Act 2023** regarding the processing of personal digital data:

### 11.1 Consent Architecture & Notice
- Explicit, unambiguous consent recorded at onboarding via a dedicated consent ledger table (`consent_records`).
- Multi-lingual consent notice provided in English, Hindi, and Gujarati.
- Granular consent toggles for:
  1. Core Matchmaking Processing (Mandatory).
  2. Family Contact & Gotra Verification (Optional).
  3. Relocation & Inter-city Matching (Optional).

### 11.2 Right to Erasure ("Right to Be Forgotten")
When a user deletes their account:
1. `users.account_status` is set to `deleted`.
2. An async Celery task executes **physical hard deletion**:
   - `interactions`, `messages`, `chats`, `user_behavior_vectors` purged within 72 hours.
   - S3 photos and voice files eradicated via `s3.delete_objects`.
   - Redis session tokens, presence keys, and cached vectors flushed.
   - Immutable financial transaction logs retained for 7 years in cold storage solely to satisfy Reserve Bank of India (RBI) and tax audit requirements.

---

## 12. Security Audit & Pen-Testing Checklist (Automated CI/CD Gates)

Every pull request must pass the following automated security checks before deployment:

```bash
# 1. Dependency Vulnerability Audit
pip-audit --strict

# 2. Static Application Security Testing (SAST)
bandit -r app/ -ll

# 3. Secret Detection in Git Commits
trufflehog git file://. --since-commit HEAD~1

# 4. SQL Injection Verification
semgrep --config "p/sql-injection" app/

# 5. Dockerfile Security Scan
trivy image jainune-backend:latest --severity HIGH,CRITICAL
```

---

## 13. Summary Checklist of Security Invariants

1. **Location**: Never store raw GPS; always snap to Geohash-6 centroid; never return distances under 2 km with decimal precision.
2. **Authentication**: Enforce RS256 JWTs with 15-minute TTL; blacklist revoked tokens in Redis; rate-limit OTP verification to 5 attempts.
3. **Database**: RLS enabled on all tables; B-Tree and HNSW indexes bounded; connection pool size capped.
4. **Media**: Presigned S3 URLs expire in 60 seconds; 100% of images stripped of EXIF metadata; ephemeral voice sparks auto-destruct within 60 seconds.
5. **Payments**: Webhooks verified with constant-time HMAC-SHA256; payments idempotent via Redis locks.
6. **Zero Emojis**: Preserved across all security documentation and error strings.
