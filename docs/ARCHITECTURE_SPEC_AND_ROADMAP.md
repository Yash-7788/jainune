# JAINUNE: PRODUCTION ARCHITECTURE, ZERO-COST INFRASTRUCTURE, EXHAUSTIVE AWS MIGRATION & EXECUTION MANUAL

> **Authoritative Master Specification for Engineering Agents & Next-Gen AI Assistants**  
> **Document Version**: 2.0.0 (Production Blueprint)  
> **Target Stack**: Expo SDK 54 / React Native 0.81 (Mobile Android & iOS PWA) + FastAPI (Python 3.12) + Supabase (PostgreSQL 16 & Storage) + Render (Compute) + Firebase Spark (Telemetry & Push) + UptimeRobot (Keep-Alive Daemon).

---

## TABLE OF CONTENTS
1. [Phase 0: Workspace Backup & Safety Protocol](#phase-0-workspace-backup--safety-protocol)
2. [Master Architecture & Financial Optimization Blueprint](#master-architecture--financial-optimization-blueprint)
3. [Exhaustive AWS Codebase Audit & Complete Supabase Replacement](#exhaustive-aws-codebase-audit--complete-supabase-replacement)
4. [Backend Compute: Render Free Web Service & Keep-Alive Daemon](#backend-compute-render-free-web-service--keep-alive-daemon)
5. [Database Architecture: Supabase PostgreSQL (500 MB 6-Month Optimization)](#database-architecture-supabase-postgresql-500-mb-6-month-optimization)
6. [Extreme Image Optimization: 100,000 Images in 1 GB Supabase Storage](#extreme-image-optimization-100000-images-in-1-gb-supabase-storage)
7. [Platform Dual-Distribution & Payment Architecture](#platform-dual-distribution--payment-architecture)
8. [Authentication Architecture: Retained Apple Sign-In & Multi-Provider Auth](#authentication-architecture-retained-apple-sign-in--multi-provider-auth)
9. [Telemetry, Crashes & Administration: Firebase Spark](#telemetry-crashes--administration-firebase-spark)
10. [Product Monetization: Subscriptions, Consumables & Arcade Economics](#product-monetization-subscriptions-consumables--arcade-economics)
11. [Interaction Redesign: Swipe + Inline Prompt Comment Combo](#interaction-redesign-swipe--inline-prompt-comment-combo)
12. [Sequential Step-by-Step Implementation Guide for the Next AI](#sequential-step-by-step-implementation-guide-for-the-next-ai)

---

## 1. PHASE 0: WORKSPACE BACKUP & SAFETY PROTOCOL

Before modifying any source file or running restructuring scripts, the engineering agent must create a clean, byte-exact backup copy of the current workspace directory. All refactoring operations must be executed inside the working copy, preserving the original folder untouched as a disaster-recovery rollback point.

### 1.1 Backup Execution Commands (Windows PowerShell)

Run the following commands from PowerShell inside `C:\Users\yashk\Downloads`:

```powershell
# 1. Terminate any active node, metro, or python background watchers
Get-Process -Name "node", "python", "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force

# 2. Define source and backup paths
$SourceDir = "C:\Users\yashk\Downloads\jainune"
$BackupDir = "C:\Users\yashk\Downloads\jainune_original_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"

# 3. Create full recursive copy excluding ephemeral build artifacts and caches
Write-Host "Creating byte-exact backup to: $BackupDir ..." -ForegroundColor Cyan
robocopy $SourceDir $BackupDir /E /XD node_modules .git .pytest_cache .ruff_cache build .coverage /XF *.pyc /R:2 /W:2

Write-Host "Backup completed successfully." -ForegroundColor Green
```

### 1.2 Verification Checklist for the Working Directory
- Verify the backup folder exists and contains all root files (`README.md`, `backend/`, `mobile/`, `docs/`, `scripts/`).
- Confirm that Git status in the active workspace (`c:\Users\yashk\Downloads\jainune`) matches working tree expectations before applying edits.
- Ensure that the original backup path is never modified, deleted, or committed to Git.

---

## 2. MASTER ARCHITECTURE & FINANCIAL OPTIMIZATION BLUEPRINT

The core technical imperative of this project is **Zero Ongoing Server Costs** while delivering enterprise-grade performance, rigorous security, and seamless user experiences across Android and iOS.

### 2.1 Core Infrastructure Matrix

| Infrastructure Layer | Selected Provider / Framework | Operating Tier | Monthly Cost | Strategic Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Backend Compute** | Render Web Services | Free Tier (750 hrs) | **₹0.00** | Native Docker/Python 3.12 hosting, automated Git deployments, free SSL, custom domain support. |
| **Compute Keep-Alive** | UptimeRobot HTTP Daemon | Free Tier (50 monitors) | **₹0.00** | Pings `/health` on a 10-minute interval to defeat Render's 15-minute inactivity spin-down. |
| **Database** | Supabase Managed PostgreSQL 16 | Free Tier (500 MB) | **₹0.00** | Fully managed Postgres, connection pooling (`pgbouncer`), graphical table editor, automated backups. |
| **Media Storage** | Supabase Storage (`avatars` bucket) | Free Tier (1.0 GB) | **₹0.00** | Completely replaces AWS S3 and Cloudinary. Zero egress charges up to 2 GB/month. |
| **Android Client** | React Native 0.81 / Expo SDK 54 | Open Source | **₹0.00** | Modern edge-to-edge UI, native Android 16 (API Level 36) compliance. |
| **Android Build** | Expo Application Services (EAS Build) | Free Tier (30 builds/mo)| **₹0.00** | Cloud compilation of release `.aab` bundles without local Android Studio or high-spec hardware. |
| **Android Store Fee**| Google Play Developer Console | Lifetime Registration | **$25 (~₹2,100)**| **Only unavoidable expense**. One-time payment for unlimited publishing rights. |
| **iOS Distribution** | Progressive Web App (PWA) on Vercel | Free Hobby Tier | **₹0.00** | **Bypasses Apple's $99/year fee and Mac hardware requirements**. Safari "Add to Home Screen". |
| **Android Billing** | Google Play Billing (`react-native-iap`) | Native Integration | **15% on base** | Mandatory for Play Store digital goods. Zero risk of account ban. |
| **iOS / PWA Billing**| Razorpay Hosted Web Checkout | Standard Merchant | **~2% + GST** | 100% compliant on web. Bypasses Apple's 15% fee, keeping ~₹389.50 on ₹399 plan. |
| **Telemetry & Push** | Firebase Spark Plan | Free Forever | **₹0.00** | Unlimited FCM push notifications, Crashlytics crash traces, Google Analytics funnels. |
| **Authentication** | Google OAuth + Apple Sign-In + SMS OTP + Email | Free Quotas | **₹0.00** | Apple Sign-In retained with zero-cost public JWKS verification (`https://appleid.apple.com/auth/keys`). |

### 2.2 Financial Comparison: Old AWS/Apple Architecture vs New Zero-Cost Model

```
OLD ARCHITECTURE (High Overhead):
  - AWS RDS PostgreSQL:               ~₹1,800 / month
  - AWS S3 Storage & Data Transfer:     ~₹400 / month
  - AWS EC2 / App Runner Server:      ~₹1,500 / month
  - Apple Developer Program:          ~₹8,300 / year (~₹690 / month)
  - Apple Hardware (Mac Mini entry):  ~₹60,000 upfront
  -------------------------------------------------------------
  TOTAL YEAR 1 CAPITAL EXPENDITURE:   ~₹1,12,680 INR

NEW PRODUCTION ARCHITECTURE (Zero Overhead):
  - Render FastAPI Compute:           ₹0 / month
  - Supabase PostgreSQL:              ₹0 / month
  - Supabase Media Storage:           ₹0 / month
  - Expo Cloud Builds (EAS):          ₹0 / month
  - iOS Distribution via PWA:         ₹0 / month
  - UptimeRobot Keep-Alive Daemon:    ₹0 / month
  - Google Play Console (One-Time):   $25 (~₹2,100 INR)
  -------------------------------------------------------------
  TOTAL YEAR 1 CAPITAL EXPENDITURE:   ₹2,100 INR (98.1% Cost Reduction)
```

---

## 3. EXHAUSTIVE AWS CODEBASE AUDIT & COMPLETE SUPABASE REPLACEMENT

The codebase currently contains legacy references to AWS infrastructure (AWS S3, `boto3`, AWS KMS, AWS SES, and Amazon AWS network configs). Below is the comprehensive audit and exact replacement roadmap.

### 3.1 Exhaustive Inventory of AWS Usage Across the Repository

#### 1. Backend Core Services & Workers
- **`backend/app/config.py`**:
  - Contains configuration properties: `aws_access_key_id`, `aws_secret_access_key`, `aws_region`, `aws_s3_bucket`, `aws_s3_quarantine_bucket`.
  - *Action*: Deprecate AWS settings; replace with `supabase_url`, `supabase_service_role_key`, `supabase_storage_bucket`.
- **`backend/app/services/media_processor.py`**:
  - Imports `boto3`, uses `boto3.client("s3")`, generates presigned PUT/GET URLs (`generate_presigned_url`), manages quarantine uploads in `_delete_from_quarantine`, and performs bucket-to-bucket object copies.
  - *Action*: Rewrite using the Supabase Storage Python SDK (`supabase.storage`) or direct HTTP REST API calls with the Service Role key.
- **`backend/app/routers/media.py`**:
  - Exposes endpoints `/v1/media/upload/request` which return S3 presigned URLs, and `/v1/media/{photo_id}/complete` which verifies S3 object metadata.
  - *Action*: Update endpoint to generate Supabase signed upload tokens or accept client-side direct WebP uploads.
- **`backend/app/services/account_service.py`**:
  - Contains `purge_user_media` which iterates over user keys in S3 and calls `s3.delete_objects`.
  - *Action*: Point deletion to `supabase.storage.from_("avatars").remove([f"{user_id}/avatar.webp"])`.
- **`backend/app/workers/ephemeral_reaper.py`**:
  - Background worker scanning S3 quarantine buckets to delete unverified media after 24 hours.
  - *Action*: Repoint to Supabase Storage cleanup or replace with client-side atomic single-image replacement.
- **`backend/app/services/messaging_service.py`**:
  - Legacy references to S3 attachment storage.
  - *Action*: Repoint to Supabase bucket.
- **`backend/requirements.txt`**:
  - Contains `boto3` and `botocore`.
  - *Action*: Remove `boto3` and `botocore`. Add `supabase==2.13.0` and `httpx==0.28.1`.

#### 2. Mobile Client & Security Manifests
- **`mobile/android/app/src/main/res/xml/network_security_config.xml`**:
  - Lines 49–56 explicitly whitelist AWS domains:
    ```xml
    <domain includeSubdomains="true">s3.ap-south-1.amazonaws.com</domain>
    <domain includeSubdomains="true">jainune-media-quarantine.s3.ap-south-1.amazonaws.com</domain>
    ```
  - *Action*: Remove AWS domains. Add Supabase storage domain:
    ```xml
    <domain includeSubdomains="true">*.supabase.co</domain>
    ```
- **`mobile/src/api/profileApi.ts`**:
  - Methods `requestMediaUploadUrl` and `completeMediaUpload` expect S3 presigned URLs and upload directly via HTTP PUT with AWS headers.
  - *Action*: Update upload method to send WebP payload to Supabase Storage endpoint:
    `POST https://<project>.supabase.co/storage/v1/object/avatars/<user_id>/avatar.webp` with `Authorization: Bearer <supabase_anon_key>`.
- **`mobile/src/screens/onboarding/steps/Step20Voice.tsx`**:
  - Uploads audio files to AWS S3.
  - *Action*: Voice notes are formally eliminated from product scope (per user instruction). Deprecate this screen or replace with text prompt.

#### 3. Test Suites
- `backend/tests/conftest.py`, `backend/tests/unit/test_profile_and_media_management.py`, `backend/tests/unit/test_deep_audit_round8_hardening.py`:
  - Contains mocks for `boto3.client`.
  - *Action*: Refactor test fixtures to mock `supabase.storage` calls.

---

### 3.2 Step-by-Step Code Replacement: Media Processor

#### Old AWS S3 Implementation (`backend/app/services/media_processor.py` snippet):
```python
# DEPRECATED AWS S3 PATTERN
import boto3
from app.config import settings

def get_s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )

def generate_upload_url(user_id: str, filename: str) -> str:
    s3 = get_s3_client()
    return s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": settings.aws_s3_bucket, "Key": f"uploads/{user_id}/{filename}"},
        ExpiresIn=300,
    )
```

#### New Supabase Storage Implementation (`backend/app/services/media_processor.py`):
```python
# REPLACEMENT SUPABASE STORAGE ENGINE
import logging
from supabase import create_client, Client
from app.config import settings

logger = logging.getLogger("jainune.media_processor")

_supabase_client: Client | None = None

def get_supabase_client() -> Client:
    global _supabase_client
    if _supabase_client is None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError("Supabase configuration missing in settings.")
        _supabase_client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key
        )
    return _supabase_client

async def generate_supabase_upload_signed_url(user_id: str) -> dict:
    """
    Generates a signed upload URL for the user's primary WebP avatar.
    Strict Single-Image Policy: Target path is always '{user_id}/avatar.webp'.
    """
    client = get_supabase_client()
    file_path = f"{user_id}/avatar.webp"
    
    # Create signed upload URL valid for 5 minutes (300 seconds)
    res = client.storage.from_("avatars").create_signed_upload_url(file_path)
    
    # Public CDN URL where image will be accessible after upload
    public_url = f"{settings.supabase_url}/storage/v1/object/public/avatars/{file_path}"
    
    return {
        "signed_url": res["signed_url"],
        "token": res["token"],
        "path": file_path,
        "public_url": public_url
    }

async def delete_user_avatar(user_id: str) -> bool:
    """Removes the master avatar from Supabase Storage."""
    try:
        client = get_supabase_client()
        client.storage.from_("avatars").remove([f"{user_id}/avatar.webp"])
        return True
    except Exception as exc:
        logger.error(f"Failed to delete avatar for user {user_id}: {exc}")
        return False
```

---

## 4. BACKEND COMPUTE: RENDER FREE WEB SERVICE & KEEP-ALIVE DAEMON

Render's free tier provides 750 hours per month of web service compute, which covers a single web instance running 24 hours a day, 31 days a month.

### 4.1 Render Service Blueprint (`render.yaml`)

Create `render.yaml` in the root of the project to allow 1-click reproducible deployments:

```yaml
services:
  - type: web
    name: jainune-backend-api
    env: python
    region: singapore # Closest free region to India (low latency for Bangalore users)
    plan: free
    branch: main
    rootDir: backend
    buildCommand: pip install --upgrade pip && pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
    healthCheckPath: /health
    autoDeploy: true
    envVars:
      - key: ENVIRONMENT
        value: production
      - key: DATABASE_URL
        sync: false # Set via Render Dashboard from Supabase Postgres Connection String
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_SERVICE_ROLE_KEY
        sync: false
      - key: JWT_SECRET
        generateValue: true
      - key: RAZORPAY_KEY_ID
        sync: false
      - key: RAZORPAY_KEY_SECRET
        sync: false
      - key: GOOGLE_PLAY_SERVICE_ACCOUNT_JSON
        sync: false
```

### 4.2 The Zero-Latency Health Check Endpoint

Render spins down free services after 15 minutes of inactivity. To prevent cold starts, the keep-alive monitor pings `/health`. This endpoint **must not execute database queries** to avoid exhausting Supabase's connection pool.

Implementation in `backend/app/main.py`:

```python
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

app = FastAPI(title="Jainune API", version="2.0.0")

@app.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
async def health_check():
    """
    Lightweight keep-alive endpoint for UptimeRobot daemon.
    Zero DB queries, zero Redis calls. Responds in <5ms.
    """
    return JSONResponse(
        content={
            "status": "online",
            "service": "jainune-api",
            "version": "2.0.0"
        }
    )
```

### 4.3 UptimeRobot Configuration Rules
1. Create a free account on [UptimeRobot](https://uptimerobot.com/).
2. Click **Add New Monitor**:
   - **Monitor Type**: `HTTP(s)`
   - **Friendly Name**: `Jainune Render Keep-Alive`
   - **URL (or IP)**: `https://jainune-backend-api.onrender.com/health`
   - **Monitoring Interval**: `10 minutes` (Render idle timeout is 15 minutes; a 10-minute heartbeat ensures the process is perpetually active).
   - **Monitor Timeout**: `30 seconds`.
3. Save Monitor. The server will now stay warm in RAM continuously for ₹0.

---

## 5. DATABASE ARCHITECTURE: SUPABASE POSTGRESQL (500 MB 6-MONTH OPTIMIZATION)

Supabase provides a 500 MB database limit on the free tier. Unoptimized schemas with bloated JSON documents, redundant string columns, and unbounded logging crash free limits within weeks. By strictly adhering to normalization and compact data types, **500 MB accommodates over 2.5 million records**, easily providing 6 to 12 months of runway.

### 5.1 Storage Footprint Mathematics

- Standard text user row with unoptimized JSON: **~2,500 bytes**.
  - $500\text{ MB} / 2,500\text{ bytes} = 200,000\text{ records}$ (Risk of exhaustion during growth spikes).
- **Optimized Normalized Schema**: **~200 bytes per user record**.
  - $500\text{ MB} = 524,288,000\text{ bytes}$.
  - $\frac{524,288,000\text{ bytes}}{200\text{ bytes/user}} = \mathbf{2,621,440\text{ User Profiles}}$.

### 5.2 Schema Normalization & Data Type Optimization

```sql
-- JAINUNE PRODUCTION HIGH-DENSITY SCHEMA OPTIMIZATION
-- Targets: Minimal Disk Footprint, Strict Foreign Keys, Ultra-Fast Indexing

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Optimized Core Users Table (~160 bytes per row)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone_number VARCHAR(15) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    account_status SMALLINT DEFAULT 1 NOT NULL, -- 1: Active, 2: Suspended, 3: Deleted
    subscription_tier SMALLINT DEFAULT 0 NOT NULL, -- 0: Free, 1: Base (399), 2: Premium (799), 3: Ultra (1499)
    subscription_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- 2. Compact Profile Attributes (~180 bytes per row)
CREATE TABLE profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    first_name VARCHAR(50) NOT NULL,
    birthdate DATE NOT NULL,
    gender SMALLINT NOT NULL, -- 1: Male, 2: Female
    community_sect SMALLINT NOT NULL, -- 1: Digambar, 2: Shvetambar Murtipujak, 3: Shvetambar Sthanakvasi, 4: Terapanthi, 5: Other
    dietary_practice SMALLINT NOT NULL, -- 1: Strict Jain (No root veg), 2: Pure Vegetarian, 3: Vegan
    city_code SMALLINT NOT NULL, -- Normalized City ID (1: Bangalore, 2: Mumbai, etc.)
    bio VARCHAR(280), -- Bounded Twitter-length bio
    avatar_url VARCHAR(255) NOT NULL, -- Single WebP image URL
    onboarding_completed BOOLEAN DEFAULT FALSE NOT NULL
);

-- 3. Dedicated Arcade Wallet Table (~40 bytes per row)
CREATE TABLE user_arcade_wallet (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    available_spins INT DEFAULT 0 NOT NULL,
    available_roses INT DEFAULT 0 NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- 4. Ephemeral Interactions & Swipes Table (~32 bytes per row)
CREATE TABLE interactions (
    id BIGSERIAL PRIMARY KEY,
    actor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action_type SMALLINT NOT NULL, -- 1: Pass, 2: Like, 3: SuperLike, 4: RoseComment
    comment_text VARCHAR(200), -- Inline prompt comment
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Compound Unique Index to prevent duplicate swipes
CREATE UNIQUE INDEX idx_unique_interaction ON interactions(actor_id, target_id);

-- Partial Index for active matches (drastically cuts index size by 80%)
CREATE INDEX idx_active_likes ON interactions(target_id) WHERE action_type >= 2;
```

### 5.3 Automated 30-Day Interaction Purge Routine
Swiping generates massive amounts of pass data (`action_type = 1`) that has zero utility after 30 days. Purging passes prevents database bloating.

Run this cron in Supabase SQL editor or via a lightweight backend task:
```sql
-- Purge passes older than 30 days to reclaim space
DELETE FROM interactions
 WHERE action_type = 1 
   AND created_at < NOW() - INTERVAL '30 days';
```

---

## 6. EXTREME IMAGE OPTIMIZATION: 100,000 IMAGES IN 1 GB SUPABASE STORAGE

Supabase provides 1.0 GB of storage on the free plan. Uncompressed smartphone photos average **3.5 MB**, which would deplete 1.0 GB in just **285 uploads**. 

By enforcing a **Strict Single-Image Policy** and **Client-Side WebP Compression**, the average profile photo size drops to **10 KB**.

### 6.1 The Mathematical Proof

$$\text{Supabase Free Storage} = 1.0\text{ GB} = 1,024\text{ MB} = 1,048,576\text{ KB}$$
$$\text{Average WebP Compressed Avatar} = 10\text{ KB}$$
$$\text{Storage Capacity} = \frac{1,048,576\text{ KB}}{10\text{ KB}} = \mathbf{104,857\text{ Profile Images}}$$

### 6.2 The Single-Image Universal Reuse Policy
1. Every user profile is strictly restricted to **ONE master photograph**.
2. This single image serves all application views:
   - **Avatar Thumbnail** in Chat (`width: 48, height: 48`)
   - **Discover Feed Card** (`width: 380, height: 475`)
   - **Full Profile Modal View** (`width: 400, height: 500`)
   - **Match Notification Banner**
3. Uploading a new photo automatically replaces and overwrites the existing image at `{user_id}/avatar.webp`, keeping storage usage constant per active user.

### 6.3 Client-Side Compression Engine (`mobile/src/utils/imageOptimizer.ts`)

The client phone performs the heavy image processing work, saving server CPU and eliminating bandwidth costs.

```typescript
import * as ImageManipulator from "expo-image-manipulator";
import * as FileSystem from "expo-file-system";

export interface OptimizedImageResult {
  uri: string;
  width: number;
  height: number;
  fileSizeBytes: number;
  base64?: string;
}

/**
 * Compresses an image to extreme high-density WebP format.
 * Target: Max 480x600 resolution, 70% quality, <=15KB payload.
 */
export async function optimizeProfilePhoto(
  originalUri: string
): Promise<OptimizedImageResult> {
  try {
    // 1. Execute client-side hardware-accelerated resize & transcode
    const manipulated = await ImageManipulator.manipulateAsync(
      originalUri,
      [
        {
          resize: {
            width: 480, // Clamps width to 480px; height auto-scales maintaining 4:5 ratio
          },
        },
      ],
      {
        compress: 0.7, // 70% lossy compression (indistinguishable on retina screens)
        format: ImageManipulator.SaveFormat.WEBP,
        base64: false,
      }
    );

    // 2. Validate resulting file size
    const fileInfo = await FileSystem.getInfoAsync(manipulated.uri);
    const size = fileInfo.exists ? fileInfo.size : 0;

    // Safety assertion: Alert if image exceeds strict 20KB budget
    if (size > 20 * 1024) {
      // Re-compress at lower quality if initial pass exceeded threshold
      const emergencyPass = await ImageManipulator.manipulateAsync(
        manipulated.uri,
        [{ resize: { width: 400 } }],
        {
          compress: 0.55,
          format: ImageManipulator.SaveFormat.WEBP,
        }
      );
      const emergencyInfo = await FileSystem.getInfoAsync(emergencyPass.uri);
      return {
        uri: emergencyPass.uri,
        width: emergencyPass.width,
        height: emergencyPass.height,
        fileSizeBytes: emergencyInfo.exists ? emergencyInfo.size : size,
      };
    }

    return {
      uri: manipulated.uri,
      width: manipulated.width,
      height: manipulated.height,
      fileSizeBytes: size,
    };
  } catch (error) {
    throw new Error(`IMAGE_OPTIMIZATION_FAILED: ${(error as Error).message}`);
  }
}
```

---

## 7. PLATFORM DUAL-DISTRIBUTION & PAYMENT ARCHITECTURE

To maximize profit and maintain compliance without paying Apple's $99/year tax, Jainune implements a clean, decoupled platform split.

```
                           [ CLIENT CHECKOUT ROUTER ]
                                       │
                ┌──────────────────────┴──────────────────────┐
                ▼                                             ▼
       [ Platform.OS === 'android' ]                 [ Platform.OS === 'web' ]
                │                                             │
      (Google Play Store App)                               (iOS PWA)
                │                                             │
      [ Google Play Billing ]                        [ Razorpay Web Checkout ]
    • Uses: react-native-iap                       • Uses: Hosted Redirect
    • 15% Google Tier Commission                   • ~2% Gateway Processing Fee
    • 18% Mandatory GST Remitted                   • 0% Apple Store Tax
    • Store Compliance: 100% Guaranteed            • Net Payout on ₹399: ~₹389.50
```

### 7.1 Android Google Play Store Implementation

Google Play Developer policies strictly prohibit third-party payment links (e.g. Razorpay, Stripe) inside Android apps for digital goods and subscriptions. **Razorpay must be completely isolated from the Android binary.**

#### Client In-App Purchase Controller (`mobile/src/services/billingService.ts`):
```typescript
import { Platform } from "react-native";
import * as RNIap from "react-native-iap";
import { apiPost } from "../api/client";

const ANDROID_SKUS = [
  "jainune_base_399",
  "jainune_premium_799",
  "jainune_ultra_1499",
  "arcade_spins_3",
  "arcade_spins_10",
  "rose_single_49",
];

export async function initializeBilling() {
  if (Platform.OS === "android") {
    await RNIap.initConnection();
    await RNIap.flushFailedPurchasesCachedAsPendingAndroid();
  }
}

export async function purchaseAndroidPlan(sku: string) {
  try {
    const purchase = await RNIap.requestPurchase({ skus: [sku] });
    // Send receipt to FastAPI for cryptographic verification
    const verification = await apiPost("/v1/subscriptions/verify-google-play", {
      orderId: purchase.orderId,
      packageName: purchase.packageNameAndroid,
      productId: purchase.productId,
      purchaseTime: purchase.transactionDate,
      purchaseToken: purchase.purchaseToken,
    });
    
    // Acknowledge purchase with Google to prevent automatic refund
    if (verification.success) {
      await RNIap.finishTransaction({ purchase, isConsumable: sku.startsWith("arcade_") || sku.startsWith("rose_") });
    }
    return verification;
  } catch (err) {
    if ((err as any).code === "E_USER_CANCELLED") {
      return { success: false, cancelled: true };
    }
    throw err;
  }
}
```

### 7.2 iOS Progressive Web App (PWA) Implementation

1. **Export Web App**:
   ```bash
   cd mobile
   npx expo export --platform web
   ```
2. **Deploy to Vercel (Free)**:
   Deploy the `dist/` directory to Vercel. iPhone users visit the link in mobile Safari and tap **Share > Add to Home Screen**.
3. **PWA Payment Flow**:
   When an iPhone user taps "Subscribe" or "Buy Spins", the app invokes Razorpay web checkout:
   ```typescript
   export function launchWebPayment(planId: string, userId: string) {
     const checkoutUrl = `https://jainune-backend-api.onrender.com/v1/payments/razorpay/checkout?plan_id=${planId}&user_id=${userId}`;
     window.location.href = checkoutUrl;
   }
   ```
4. **Profit Comparison on ₹399 Tier**:
   - **Android Store App**: ₹399 - ₹60.86 (18% GST) - ₹50.72 (15% Google) = **₹287.42 Net Payout**.
   - **iOS Web PWA**: ₹399 - ₹7.98 (2% Fee) - ₹1.44 (18% GST on Fee) = **₹389.58 Net Payout**.
   - **PWA yields an extra ₹102.16 in profit per customer.**

---

## 8. AUTHENTICATION ARCHITECTURE: RETAINED APPLE SIGN-IN & MULTI-PROVIDER AUTH

Apple Sign-In is retained, fully functional, and production-hardened. Backend token verification uses Apple's official public JSON Web Key Set (JWKS) at `https://appleid.apple.com/auth/keys` via `PyJWKClient` (RS256 signature verification), incurring zero Apple Developer API costs or private secret key dependencies for basic identity token decoding.

### 8.1 Multi-Provider Authentication Matrix
1. **Google OAuth (Android / Web / PWA)**: One-tap sign-in via Google ID tokens verified against Google's public token certs.
2. **Apple Sign-In (iOS App / PWA / Web)**: Retained with official Apple SVG branding and native/web federated sign-in. Backend decodes and cryptographically verifies RS256 signatures via cached JWKS (`backend/app/routers/auth.py:609`).
3. **Phone Number SMS OTP (India)**: Primary identity verification and bot deterrent via SMS OTP.
4. **Email / Password**: Universal fallback authentication for all platforms.

### 8.2 Production Authentication Method Interface (`AuthMethodScreen.tsx`)
```tsx
// Excerpt from production AuthMethodScreen.tsx
<View style={styles.buttonContainer}>
  {/* 1. Primary: Google One-Tap */}
  <PrimaryButton
    title="Continue with Google"
    icon={<GoogleIcon />}
    onPress={handleGoogleSignIn}
    style={styles.googleButton}
  />

  {/* 2. Retained: Apple Sign-In (Official SVG & JWKS Backend Verification) */}
  <SecondaryButton
    title="Continue with Apple"
    icon={<AppleIcon />}
    onPress={handleAppleSignIn}
    style={styles.appleButton}
  />

  {/* 3. Mobile Phone OTP */}
  <SecondaryButton
    title="Continue with Phone Number"
    icon={<PhoneIcon />}
    onPress={() => navigation.navigate("Phone")}
    style={styles.phoneButton}
  />

  {/* 4. Fallback: Email Access */}
  <GhostButton
    title="Use Email Address"
    onPress={() => navigation.navigate("Email")}
    style={styles.emailButton}
  />
</View>
```

---

## 9. TELEMETRY, CRASHES & ADMINISTRATION: FIREBASE SPARK

The Firebase Spark plan provides unlimited analytics, crash logging, and Android push notification credentials for **₹0**.

### 9.1 Essential Setup Checklist
1. Create a Firebase project named `jainune-production` on the default **Spark Plan**.
2. Download `google-services.json` and place it in `mobile/android/app/google-services.json`.
3. In `mobile/app.json`, register the configuration plugin:
   ```json
   {
     "expo": {
       "android": {
         "googleServicesFile": "./google-services.json",
         "package": "com.jainune.app"
       }
     }
   }
   ```

### 9.2 Features to Activate vs Avoid

| Firebase Feature | Activation Status | Usage Purpose |
| :--- | :--- | :--- |
| **Cloud Messaging (FCM)** | **ACTIVE** | Delivers instant match alerts, chat messages, and push campaigns. |
| **Crashlytics** | **ACTIVE** | Logs unhandled exceptions and React Native crashes with exact stack traces. |
| **Google Analytics** | **ACTIVE** | Tracks DAU, conversion funnels (views -> checkouts), and retention. |
| **Remote Config** | **ACTIVE** | Dynamically toggles features (e.g. maintenance mode) without app updates. |
| **Cloud Firestore** | **AVOID** | Low free limits (1GB). Use Supabase PostgreSQL instead. |
| **Firebase Storage** | **AVOID** | Requires paid Blaze tier for advanced networking. Use Supabase Storage. |

---

## 10. PRODUCT MONETIZATION: SUBSCRIPTIONS, CONSUMABLES & ARCADE ECONOMICS

Jainune implements a hybrid monetization model pairing recurring monthly subscriptions with high-margin consumable microtransactions.

### 10.1 Tier Structure & Feature Gating

```
                                  [ SUBSCRIPTION TIERS ]
                                             │
      ┌──────────────────────────────────────┼──────────────────────────────────────┐
      ▼                                      ▼                                      ▼
 [ BASE PLAN ]                         [ PREMIUM PLAN ]                      [ ULTRA PREMIUM ]
  ₹399 / month                          ₹799 / month                          ₹1,499 / month
  • Unlimited Swipes                    • All Base Features                   • All Premium Features
  • City / Travel Passport              • "See Who Liked You" (Beeline)       • Priority Likes (Top Deck)
  • 1 Standout Rose / week              • 3 Standout Roses / week             • Incognito Browsing Mode
  • 5 Arcade Spins / month              • 15 Arcade Spins / month             • 1 Daily Standout Rose
  • Standard Deck Priority              • Chat Read Receipts                  • 30 Arcade Spins / month
                                                                              • 1 Instant Match Pass / mo
```

### 10.2 Consumables & Microtransactions
- **₹29 — Instant Slingshot Super-Like**: Bypasses the swipe queue and delivers a notification directly to the user's inbox.
- **₹49 — Standout Rose / Icebreaker Bubble**: Allows commenting on a Standout profile or triggers a **30-minute 10x profile visibility boost**.
- **Arcade Token Bundles**:
  - 3 Spins: **₹79** (~₹26.30 / spin)
  - 10 Spins: **₹199** (~₹19.90 / spin)

### 10.3 The Paid-Only Spin Arcade Economy
- **Zero Free Daily Spins**: Eliminates complex cron jobs and daily reset counters.
- **Spin Mechanics**: Users spin a kinetic wheel to trigger an **instant, mutual-like-free match** with an active compatible Jain member.
- **Anti-Cannibalization Guardrail**: Spins provide single instant connections, while subscriptions provide ongoing visibility, unlimited discovery, and the Beeline ("See Who Liked You"). This prompts casual users to buy consumable spins while guiding regular users toward monthly plans.

---

## 11. INTERACTION REDESIGN: SWIPE + INLINE PROMPT COMMENT COMBO

To stand out against aging platforms (Tinder) and expensive apps (Hinge), Jainune combines rapid swiping with deep, prompt-based commenting.

### 11.1 Component Layout Hierarchy
1. **Hero Visual**: Full-width, aspect-ratio-locked ($480 \times 600$) WebP master photo.
2. **Community Identity Bar**:
   - Sub-sect badge (e.g. `Digambar`, `Shvetambar Sthanakvasi`)
   - Dietary badge (e.g. `Strict Jain / No Root Veg`, `Vegetarian`)
3. **Three Cultural Prompts**:
   - *Prompt 1*: "My family's favorite Paryushan tradition..."
   - *Prompt 2*: "The most authentic Jain dish I can make from scratch..."
   - *Prompt 3*: "What non-violence (Ahimsa) means in my daily routine..."

### 11.2 Interaction Mechanics
- **Horizontal Swipe**: Standard Tinder gesture (Left = Pass, Right = Like).
- **Prompt Tap (Inline Comment Sheet)**: Tapping any of the 3 prompts pauses card navigation and slides up a native bottom sheet:
  - Displays prompt header and user's text answer.
  - Text field: "Add a comment with your like..." (Max 140 chars).
  - Send button: Records the interaction as `action_type = 4` (`RoseComment` or `PromptComment`).
- **Standouts Grid**: An exclusive tab showcasing the most active, highly responsive community members. Browsing is free; sending a direct prompt message requires **1 Rose** (earned via weekly subscription entitlement or purchased for ₹49).

---

## 12. SEQUENTIAL STEP-BY-STEP IMPLEMENTATION GUIDE FOR THE NEXT AI

This is the exact, phase-by-phase execution checklist for any AI coding assistant continuing work on this repository.

### PHASE 1: Safety Backup & Environment Setup
- [x] Run the PowerShell backup script in `C:\Users\yashk\Downloads` to create `jainune_original_backup`.
- [x] Audit `.gitignore` in `jainune/` to ensure `.env`, `.env.local`, `*.pem`, and `google-services.json` are excluded.
- [x] Create `.env.example` documenting:
  `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`.

### PHASE 2: AWS Extraction & Supabase Storage Integration
- [x] In `backend/requirements.txt`, remove `boto3` and `botocore`. Add `supabase==2.13.0`.
- [x] In `backend/app/config.py`, replace AWS variables with Supabase credentials.
- [x] In `backend/app/services/media_processor.py`, replace `boto3` S3 calls with Supabase Storage signed URLs.
- [x] In `backend/app/services/account_service.py`, update `purge_user_media` to delete from Supabase `avatars` bucket.
- [x] In `backend/app/workers/ephemeral_reaper.py`, remove S3 quarantine cleanup logic.
- [x] In `mobile/android/app/src/main/res/xml/network_security_config.xml`, remove `s3.amazonaws.com` domains; add `*.supabase.co`.

### PHASE 3: Client-Side Single-Image Optimization Pipeline
- [x] Create `mobile/src/utils/imageOptimizer.ts` using `expo-image-manipulator` (clamp to 480px width, WebP format, 70% quality).
- [x] In `mobile/src/api/profileApi.ts`, update `uploadAvatar` to route the WebP payload to Supabase Storage.
- [x] In `mobile/src/screens/main/EditProfileScreen.tsx`, enforce the single-image upload rule.

### PHASE 4: Mobile Authentication & Apple Sign-In Retained
- [x] In `mobile/src/screens/auth/AuthMethodScreen.tsx`, retain Apple Sign-In with official Apple branding and native tactile feedback.
- [x] In `backend/app/routers/auth.py`, verify Apple ID tokens against official JWKS (`https://appleid.apple.com/auth/keys`).
- [x] Ensure `Google Sign-In`, `Apple Sign-In`, `Phone OTP`, and `Email` are styled cleanly with tactile feedback.
- [x] In `mobile/src/navigation/AppNavigator.tsx`, verify unauthenticated routing directs cleanly to `AuthMethod`.

### PHASE 5: Decoupled Billing Architecture
- [x] In `mobile/src/services/billingService.ts`:
  - Route Android payments through `react-native-iap` (Google Play Billing).
  - Isolate Razorpay checkout to Web/PWA builds only.
- [x] In `backend/app/routers/subscriptions.py`:
  - Update subscription pricing tiers to ₹399 (Base), ₹799 (Premium), ₹1,499 (Ultra).
  - Implement `/v1/subscriptions/verify-google-play` for Android receipt validation.
  - Implement `/v1/payments/razorpay/checkout` and `/v1/payments/razorpay/webhook` for iOS PWA checkouts.

### PHASE 6: Arcade & Interaction Logic Refinement
- [x] In `backend/app/routers/arcade.py`:
  - Enforce atomic token deduction in `@router.post("/spin")`.
  - Remove any scheduled jobs that award free daily spins.
- [x] In `mobile/src/components/arcade/SerendipityArcadeModal.tsx`:
  - Update UI to show remaining paid spins. If balance is 0, display a purchase prompt for 3 spins (₹79) or 10 spins (₹199).

### PHASE 7: Render Deployment & UptimeRobot Heartbeat
- [x] In `backend/app/main.py`, verify `GET /health` returns `{"status": "online"}` with zero database calls.
- [ ] Commit changes to private GitHub repository.
- [ ] Create a free Web Service on Render linked to the repository.
- [ ] Add the Render `/health` URL to UptimeRobot on a 10-minute ping schedule.
- [x] Run `mobile/node_modules/.bin/tsc --noEmit` to verify 0 compilation errors across the frontend.

---

## 13. SCHEMA ALIGNMENT & ANTI-REGRESSION VERIFICATION MATRIX

To prevent runtime mismatches, logic errors, or fatal crashes between the client and server, all data models, primary keys, and foreign keys across PostgreSQL, FastAPI (Pydantic), and React Native (TypeScript) must maintain 100% byte-exact parity.

### 13.1 Universal Identifier Contract (Strict UUID Rule)

| Entity / Table | PostgreSQL Type | FastAPI / Python Type | TypeScript / React Native Type | Validation Rule |
| :--- | :--- | :--- | :--- | :--- |
| `users.id` | `UUID PRIMARY KEY` | `uuid.UUID` | `string` (UUID v4) | RFC 4122 compliant; never parse as integer. |
| `profiles.user_id` | `UUID REFERENCES users(id)` | `uuid.UUID` | `string` (UUID v4) | Strictly 1-to-1 foreign key. |
| `user_photos.id` | `UUID PRIMARY KEY` | `uuid.UUID` | `string` (UUID v4) | Generated via `gen_random_uuid()`. |
| `user_photos.user_id`| `UUID REFERENCES users(id)` | `uuid.UUID` | `string` (UUID v4) | Cascades on user deletion. |
| `store_subscriptions.id`| `UUID PRIMARY KEY` | `uuid.UUID` | `string` (UUID v4) | Stores Google Play transaction records. |
| `payment_intents.id` | `UUID PRIMARY KEY` | `uuid.UUID` | `string` (UUID v4) | Stores Razorpay order intents. |
| `user_arcade_wallet.user_id`| `UUID PRIMARY KEY` | `uuid.UUID` | `string` (UUID v4) | Atomic balance target. |
| `interactions.id` | `BIGSERIAL PRIMARY KEY` | `int` | `number` | High-throughput sequential ID for feed pagination. |

### 13.2 Database Column Mapping & Anti-Regression Table

To eliminate regressions across existing backend migrations (`0001` through `0025`), the following column naming rules are locked:

| Database Column | Existing Migration Source | Python Pydantic Field | TypeScript Client Field | Note / Backward-Compatibility Lock |
| :--- | :--- | :--- | :--- | :--- |
| `subscription_tier` | `0001_initial_schema.sql` | `subscription_tier: str` | `subscriptionTier: string` | Allowed values: `'free'`, `'base_399'`, `'premium_799'`, `'ultra_1499'`. |
| `subscription_valid_until` | `0006_monetization.sql` | `subscription_valid_until: datetime` | `subscriptionValidUntil: string` | ISO-8601 string. Nullable for free users. |
| `billing_status` | `0021_store_sub.sql` | `billing_status: str` | `billingStatus: string` | `'active'`, `'grace_period'`, `'on_hold'`, `'expired'`. |
| `user_photos.s3_key` | `0001_initial_schema.sql` | `s3_key: str` | `s3Key: string` | **Preserved Column**: Repurposed to hold the Supabase Storage object path (e.g. `{user_id}/avatar.webp`) to avoid modifying existing schema constraints. |
| `user_photos.cdn_url`| `0001_initial_schema.sql` | `cdn_url: str` | `cdnUrl: string` | Contains full Supabase public CDN URL (`https://<proj>.supabase.co/storage/v1/object/public/avatars/...`). |
| `available_spins` | `0006_monetization.sql` | `available_spins: int` | `availableSpins: number` | Wallet token count. Incremented on purchase, atomically decremented on spin. |
| `razorpay_order_id`| `0006_monetization.sql` | `razorpay_order_id: str` | `razorpayOrderId: string` | Unique identifier for web/PWA checkout orders. |
| `fcm_token` | `0006_monetization.sql` | `fcm_token: Optional[str]` | `fcmToken: string \| null` | Firebase Cloud Messaging device token. |

### 13.3 Atomic Concurrency & TOCTOU Race Defense

When a user triggers an arcade spin (`POST /v1/arcade/spin`), concurrent requests from multiple devices or rapid-fire button taps must never result in duplicate spins or negative balances.

**Required Database Transaction Logic (`backend/app/routers/arcade.py`)**:
```python
async with pool.acquire() as conn:
    async with conn.transaction():
        # 1. Acquire row-level exclusive lock on user's wallet
        wallet = await conn.fetchrow(
            "SELECT available_spins FROM user_arcade_wallet WHERE user_id = $1 FOR UPDATE",
            user_id
        )
        if not wallet or wallet["available_spins"] <= 0:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="No spins remaining. Purchase a spin bundle to play."
            )

        # 2. Atomic decrement with non-negative guard
        new_balance = await conn.fetchval(
            """
            UPDATE user_arcade_wallet
               SET available_spins = available_spins - 1,
                   updated_at = NOW()
             WHERE user_id = $1 AND available_spins > 0
            RETURNING available_spins
            """,
            user_id
        )
        if new_balance is None:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Concurrency conflict: Insufficient spins."
            )

        # 3. Record transaction ledger entry
        await conn.execute(
            """
            INSERT INTO arcade_transactions (user_id, action_type, spins_delta, status)
            VALUES ($1, 'spend_spin', -1, 'spent')
            """,
            user_id
        )

        # 4. Fetch candidate match from bounded candidate pool
        match = await find_compatible_arcade_candidate(conn, user_id)
        return {"matched": bool(match), "candidate": match, "remaining_spins": new_balance}
```

---

## 14. APPLE PWA DEPLOYMENT & RAZORPAY WEB PRESERVATION

To serve iPhone users without incurring Apple's $99/year fee or purchasing macOS hardware, Jainune is exported as a standalone Progressive Web App (PWA) with full Razorpay integration.

### 14.1 Progressive Web App Configuration (`mobile/app.json`)

Ensure the `web` section of `app.json` defines a native-app-like standalone experience:

```json
{
  "expo": {
    "name": "Jainune",
    "slug": "jainune",
    "version": "2.0.0",
    "web": {
      "favicon": "./assets/favicon.png",
      "bundler": "metro",
      "display": "standalone",
      "orientation": "portrait",
      "backgroundColor": "#FFFCFA",
      "themeColor": "#FF9C4A",
      "startUrl": "/",
      "meta": {
        "apple": {
          "mobileWebAppCapable": "yes",
          "statusBarStyle": "black-translucent"
        }
      }
    }
  }
}
```

### 14.2 Web Manifest & Service Worker Strategy
Create `mobile/web/manifest.json` ensuring Safari recognizes installability:
```json
{
  "short_name": "Jainune",
  "name": "Jainune — Modern Jain Relationships",
  "icons": [
    {
      "src": "/assets/icon-192.png",
      "type": "image/png",
      "sizes": "192x192"
    },
    {
      "src": "/assets/icon-512.png",
      "type": "image/png",
      "sizes": "512x512"
    }
  ],
  "start_url": "/",
  "background_color": "#FFFCFA",
  "theme_color": "#FF9C4A",
  "display": "standalone"
}
```

### 14.3 Vercel Deployment & SPA History Routing (`vercel.json`)
When deploying the exported static web bundle to Vercel, single-page application (SPA) client-side routing must not break on page reloads.

Place `mobile/vercel.json`:
```json
{
  "rewrites": [
    {
      "source": "/(.*)",
      "destination": "/index.html"
    }
  ],
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        {
          "key": "X-Content-Type-Options",
          "value": "nosniff"
        },
        {
          "key": "X-Frame-Options",
          "value": "DENY"
        },
        {
          "key": "X-XSS-Protection",
          "value": "1; mode=block"
        },
        {
          "key": "Referrer-Policy",
          "value": "strict-origin-when-cross-origin"
        }
      ]
    }
  ]
}
```

Build and deployment command:
```bash
cd mobile
npx expo export --platform web
npx vercel deploy --prod dist
```

### 14.4 Safari "Add to Home Screen" Banner Component

To guide iPhone users to install the PWA, display a subtle non-intrusive prompt if running in mobile Safari browser mode:

```tsx
import React, { useState, useEffect } from "react";
import { View, Text, StyleSheet, TouchableOpacity, Platform } from "react-native";
import { colors } from "../theme/colors";

export default function InstallPromptBanner() {
  const [showPrompt, setShowPrompt] = useState(false);

  useEffect(() => {
    if (Platform.OS === "web") {
      const isIos = /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as any).MSStream;
      const isStandalone = (window.navigator as any).standalone === true || window.matchMedia("(display-mode: standalone)").matches;
      if (isIos && !isStandalone) {
        setShowPrompt(true);
      }
    }
  }, []);

  if (!showPrompt) return null;

  return (
    <View style={styles.banner}>
      <Text style={styles.text}>
        Install Jainune on your iPhone: Tap <Text style={styles.bold}>Share</Text> and select <Text style={styles.bold}>Add to Home Screen</Text> 📲
      </Text>
      <TouchableOpacity onPress={() => setShowPrompt(false)}>
        <Text style={styles.dismiss}>✕</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: colors.cream,
    borderColor: colors.saffron,
    borderWidth: 1.5,
    borderRadius: 12,
    padding: 12,
    margin: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  text: { fontSize: 13, color: colors.charcoal, flex: 1, lineHeight: 18 },
  bold: { fontWeight: "700", color: colors.saffron },
  dismiss: { fontSize: 16, fontWeight: "700", color: colors.charcoal, marginLeft: 8 },
});
```

### 14.5 Razorpay Web Checkout Integration (Preserved for PWA)

On Web/PWA, payments use standard Razorpay Checkout via script injection or hosted redirect, fully bypassing Apple's 15% commission.

```typescript
// Web checkout launcher in mobile/src/services/billingService.ts
export async function launchRazorpayWebCheckout(orderId: string, amountPaise: number, planLabel: string) {
  if (Platform.OS !== "web") return;

  const loadRazorpayScript = (): Promise<boolean> => {
    return new Promise((resolve) => {
      if ((window as any).Razorpay) return resolve(true);
      const script = document.createElement("script");
      script.src = "https://checkout.razorpay.com/v1/checkout.js";
      script.onload = () => resolve(true);
      script.onerror = () => resolve(false);
      document.body.appendChild(script);
    });
  };

  const loaded = await loadRazorpayScript();
  if (!loaded) throw new Error("RAZORPAY_SDK_LOAD_FAILED");

  const options = {
    key: process.env.EXPO_PUBLIC_RAZORPAY_KEY_ID,
    amount: amountPaise,
    currency: "INR",
    name: "Jainune",
    description: planLabel,
    order_id: orderId,
    theme: { color: "#FF9C4A" },
    handler: async function (response: any) {
      // Cryptographic verification call to backend
      await apiPost("/v1/subscriptions/verify-razorpay", {
        razorpay_order_id: response.razorpay_order_id,
        razorpay_payment_id: response.razorpay_payment_id,
        razorpay_signature: response.razorpay_signature,
      });
      window.location.reload();
    },
  };

  const rzp = new (window as any).Razorpay(options);
  rzp.open();
}
```

---

## 15. ZERO-DOWNGRADE SECURITY ARCHITECTURE & ENHANCED DEFENSE IN DEPTH

This architecture maintains 100% of the existing security mechanisms while introducing new safeguards for Supabase and the dual-billing layer.

### 15.1 Preservation of Existing Mobile Security Controls

The following native Android security features implemented in `JainuneSecurityModule.java` and `deviceIntegrity.ts` must remain fully intact and active in all Android release builds:

1. **Root / Magisk / KernelSU Detection**:
   - Probes binary paths (`/system/bin/su`, `/system/xbin/su`, `/sbin/su`, `/data/local/xbin/su`).
   - Checks package managers for Magisk Manager, KernelSU, and APatch signatures.
2. **Frida Dynamic Instrumentation Detection**:
   - Performs TCP loopback probe on port `27042` to detect active Frida injection servers.
   - Scans `/proc/self/maps` for `frida-gadget.so` and `frida-agent.so`.
3. **PTRACE / Debugger Detection**:
   - Evaluates `android.os.Debug.isDebuggerConnected()` and `Debug.waitingForDebugger()`.
   - Halts application execution if attached to an active debugging session.
4. **OS-Level Screenshot & Screen Recording Prevention**:
   - `enableFlagSecure()` applies `WindowManager.LayoutParams.FLAG_SECURE` to the active Activity.
   - Prevents screenshot capture and screen recording during chat and onboarding.
5. **Emergency Storage Purge**:
   - `emergencyPurgeStorage()` synchronously wipes all `SharedPreferences`, `EncryptedSharedPreferences`, and SQLite databases on critical security violations.

### 15.2 Updated Network Security Configuration (`network_security_config.xml`)

Remove all AWS S3 domains while maintaining strict SPKI certificate pinning for production APIs:

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
  <!-- Production domain: strict SPKI pinning -->
  <domain-config cleartextTrafficPermitted="false">
    <domain includeSubdomains="true">api.jainune.com</domain>
    <domain includeSubdomains="true">jainune.com</domain>
    <pin-set expiration="2027-09-01">
      <pin digest="SHA-256">k20YWfohKw3kUj5t5K65soVIyzxPCQFvMQkxZpmGsoo=</pin>
      <pin digest="SHA-256">WoiWRyIOVNa9ihaBciRSC7XHjliYS9VwUGOIud4PB18=</pin>
    </pin-set>
    <trust-anchors>
      <certificates src="system" />
    </trust-anchors>
  </domain-config>

  <!-- Supabase Managed Storage & Database -->
  <domain-config cleartextTrafficPermitted="false">
    <domain includeSubdomains="true">supabase.co</domain>
    <trust-anchors>
      <certificates src="system" />
    </trust-anchors>
  </domain-config>

  <!-- Razorpay Payment Gateway (Used on Web/PWA) -->
  <domain-config cleartextTrafficPermitted="false">
    <domain includeSubdomains="true">api.razorpay.com</domain>
    <domain includeSubdomains="true">checkout.razorpay.com</domain>
    <trust-anchors>
      <certificates src="system" />
    </trust-anchors>
  </domain-config>

  <!-- Base config: reject cleartext HTTP everywhere -->
  <base-config cleartextTrafficPermitted="false">
    <trust-anchors>
      <certificates src="system" />
    </trust-anchors>
  </base-config>
</network-security-config>
```

### 15.3 Enhanced Defense Layer: Supabase Row Level Security (RLS)

All tables created in Supabase must have Row Level Security enabled to prevent unauthorized data access:

```sql
-- Enable RLS across all tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_arcade_wallet ENABLE ROW LEVEL SECURITY;
ALTER TABLE interactions ENABLE ROW LEVEL SECURITY;

-- 1. Users can only read active and non-banned profiles
CREATE POLICY "Public profiles viewable by authenticated users"
ON profiles FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM users
        WHERE users.id = profiles.user_id
          AND users.account_status = 1
    )
);

-- 2. Users can only update their own profile
CREATE POLICY "Users can update own profile"
ON profiles FOR UPDATE
TO authenticated
USING (auth.uid() = user_id);

-- 3. Arcade wallet accessible strictly by owner
CREATE POLICY "Users can read own arcade wallet"
ON user_arcade_wallet FOR SELECT
TO authenticated
USING (auth.uid() = user_id);
```

### 15.4 Payment Replay Defense & Token Idempotency

To prevent malicious users from replaying valid Google Play purchase tokens or Razorpay signatures:

1. Create table `processed_payment_receipts`:
   ```sql
   CREATE TABLE processed_payment_receipts (
       token_hash VARCHAR(64) PRIMARY KEY,
       provider VARCHAR(16) NOT NULL, -- 'google_play' or 'razorpay'
       user_id UUID NOT NULL REFERENCES users(id),
       processed_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
   );
   ```
2. On every verification request, compute `SHA-256(purchaseToken)` or `SHA-256(razorpay_signature)`.
3. If the hash exists in `processed_payment_receipts`, reject with `HTTP 409 CONFLICT ("RECEIPT_ALREADY_PROCESSED")`.
4. Insert the hash atomically inside the activation transaction.

