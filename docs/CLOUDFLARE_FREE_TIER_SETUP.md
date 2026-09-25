# Cloudflare $0 Free-Tier Suite Configuration Guide

Complete step-by-step setup guide for activating all 6 Cloudflare zero-cost infrastructure tools for the Jainune production stack.

---

## 1. DNS & Reverse Proxy (Render Origin Shield)

### 1.1 DNS Record
* **Path**: Cloudflare Dashboard &rarr; `yourdomain.com` &rarr; **DNS** &rarr; **Records** &rarr; **Add record**
* **Type**: `CNAME`
* **Name**: `api`
* **Target**: `jainune-backend-api.onrender.com`
* **Proxy status**: **Proxied** (Orange cloud ON)
* **TTL**: `Auto`

### 1.2 Custom Domain on Render
* **Path**: Render Dashboard &rarr; `jainune-backend-api` &rarr; **Settings** &rarr; **Custom Domains**
* Add `api.yourdomain.com` and wait for Render's certificate verification to complete.

### 1.3 Transform Rule (Origin Secret Injection)
Prevents attackers from bypassing Cloudflare to hit your Render backend URL directly.
* **Path**: Cloudflare Dashboard &rarr; **Rules** &rarr; **Transform Rules** &rarr; **Modify Request Header** &rarr; **Create rule**
* **Rule name**: `Inject Origin Secret for Render`
* **If incoming requests match**: Custom filter expression
  * Field: `Hostname` &nbsp;|&nbsp; Operator: `equals` &nbsp;|&nbsp; Value: `api.yourdomain.com`
* **Modify request headers**:
  * Action: **Set static**
  * Header name: `CF-Origin-Secret`
  * Value: `<CLOUDFLARE_ORIGIN_SECRET>` *(generate with `openssl rand -hex 32`)*

---

## 2. Media CNAME & Origin Rule (Supabase Storage Proxy)

Bypasses Supabase 2 GB egress bandwidth quota by routing all public avatar and photo fetches through Cloudflare Edge Cache.

### 2.1 Media DNS Record
* **Path**: Cloudflare Dashboard &rarr; **DNS** &rarr; **Records** &rarr; **Add record**
* **Type**: `CNAME`
* **Name**: `media`
* **Target**: `<your-project-ref>.supabase.co`
* **Proxy status**: **Proxied** (Orange cloud ON)
* **TTL**: `Auto`

### 2.2 Origin Rule (Host Header Override)
* **Path**: Cloudflare Dashboard &rarr; **Rules** &rarr; **Origin Rules** &rarr; **Create rule**
* **Rule name**: `Rewrite Host Header to Supabase`
* **If incoming requests match**:
  * Field: `Hostname` &nbsp;|&nbsp; Operator: `equals` &nbsp;|&nbsp; Value: `media.yourdomain.com`
* **Host Header**:
  * Select: **Rewrite to...** &rarr; Value: `<your-project-ref>.supabase.co`

### 2.3 SSL/TLS Mode
* **Path**: Cloudflare Dashboard &rarr; **SSL/TLS** &rarr; **Overview**
* Select: **Full (strict)** *(required for Supabase origin verification)*.

### 2.4 Cache Rule (1-Month Edge Storage TTL)
* **Path**: Cloudflare Dashboard &rarr; **Caching** &rarr; **Cache Rules** &rarr; **Create rule**
* **Rule name**: `Cache Supabase Public Avatars`
* **If incoming requests match**:
  * `(http.host eq "media.yourdomain.com" and starts_with(http.request.uri.path, "/storage/v1/object/public/"))`
* **Cache eligibility**: **Eligible for cache**
* **Edge TTL**: **Override origin** &rarr; `1 month`
* **Browser TTL**: **Override origin** &rarr; `7 days`

---

## 3. Cloudflare Turnstile (Web Anti-Bot & OTP Fraud Shield)

Stops botnets from generating SMS toll fraud or spamming verification endpoints.

### 3.1 Create Turnstile Widget
* **Path**: Cloudflare Dashboard &rarr; **Turnstile** &rarr; **Add widget**
* **Widget name**: `Jainune Web Auth`
* **Domains**: `yourdomain.com`, `api.yourdomain.com`, `localhost`
* **Widget Mode**: **Managed**
* Save and retrieve:
  * **Site Key** &rarr; `EXPO_PUBLIC_TURNSTILE_SITE_KEY` in `mobile/.env`
  * **Secret Key** &rarr; `TURNSTILE_SECRET_KEY` in Render `.env`

---

## 4. Cloudflare Workers AI (Llama 3.2 Vision NSFW Moderation)

Provides 10,000 free daily neurons for NSFW, nudity, and face detection on profile photos.

### 4.1 Obtain Credentials
1. **Account ID**: Found in Cloudflare Dashboard &rarr; right sidebar under **Account details**.
2. **API Token**: Cloudflare Dashboard &rarr; **My Profile** &rarr; **API Tokens** &rarr; **Create Token**
   * Template: **Workers AI Read** or Custom Token with `Account &rarr; Workers AI &rarr; Edit/Run` permissions.

### 4.2 Render Backend Environment Variables
Add to Render `.env`:
```ini
CLOUDFLARE_ACCOUNT_ID=<32_CHAR_ACCOUNT_ID>
CLOUDFLARE_API_TOKEN=<YOUR_CLOUDFLARE_TOKEN>
CF_AI_VISION_MODEL=@cf/meta/llama-3.2-11b-vision-instruct
CF_AI_MODERATION_ENABLED=true
CF_AI_DAILY_NEURON_CAP=9500
CF_AI_MAX_RPM=15
```

---

## 5. WAF & Brotli Compression

One-click dashboard optimizations for performance and intrusion defense.

### 5.1 Brotli Compression
* **Path**: Cloudflare Dashboard &rarr; **Speed** &rarr; **Optimization** &rarr; **Content Optimization**
* Toggle **Brotli** &rarr; **ON** *(compresses API and legal page payloads by 20–25%)*.

### 5.2 Managed WAF Ruleset
* **Path**: Cloudflare Dashboard &rarr; **Security** &rarr; **WAF** &rarr; **Managed rules**
* Under **Cloudflare Free Managed Ruleset** &rarr; Toggle **ON**.

### 5.3 Bot Fight Mode
* **Path**: Cloudflare Dashboard &rarr; **Security** &rarr; **Bots**
* Toggle **Bot Fight Mode** &rarr; **ON**.

---

## 6. Cloudflare Email Routing ($0 Compliance Mailboxes)

Forwards required compliance and support emails directly to your Gmail inbox for App Store and Google Play approvals at $0 cost.

### 6.1 Enable Email Routing
* **Path**: Cloudflare Dashboard &rarr; **Email** &rarr; **Email Routing**
* Click **Enable Email Routing** *(Cloudflare will prompt to auto-add required MX and TXT/SPF records to DNS)*.

### 6.2 Destination Address
* Under **Destination addresses**, add your personal Gmail address.
* Check your Gmail and click the confirmation link.

### 6.3 Routing Rules
Add 3 custom routing rules:
1. `support@yourdomain.com` &rarr; Forward to your verified Gmail *(Google Play Support URL)*.
2. `privacy@yourdomain.com` &rarr; Forward to your verified Gmail *(DPDP Privacy Officer)*.
3. `safety@yourdomain.com` &rarr; Forward to your verified Gmail *(Child Safety & CSAE escalation)*.

---

## 7. Render & Mobile Environment Matrix Check

| Variable | Platform | Value / Purpose |
|---|---|---|
| `CLOUDFLARE_ORIGIN_SECRET` | Render `.env` | Matches `CF-Origin-Secret` in Transform Rule. |
| `MEDIA_CDN_URL` | Render `.env` | `https://media.yourdomain.com` |
| `TURNSTILE_SECRET_KEY` | Render `.env` | Turnstile secret key. |
| `CLOUDFLARE_ACCOUNT_ID` | Render `.env` | Cloudflare account ID for Workers AI. |
| `CLOUDFLARE_API_TOKEN` | Render `.env` | Cloudflare API token for Workers AI. |
| `EXPO_PUBLIC_API_URL` | Mobile `.env` | `https://api.yourdomain.com/v1` |
| `EXPO_PUBLIC_WS_URL` | Mobile `.env` | `wss://api.yourdomain.com/v1/ws/chat` |
| `EXPO_PUBLIC_TURNSTILE_SITE_KEY` | Mobile `.env` | Turnstile public site key. |
