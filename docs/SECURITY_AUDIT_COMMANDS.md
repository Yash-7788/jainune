# Jainune APK & Source Code Security Audit
# Kali Linux / Security Toolchain Command Reference
# Covers SECURITY.md §12 (Pen-Testing Checklist) + mobile layer

---

## 1. BUILD SIGNED RELEASE APK

```bash
# Navigate to android directory
cd mobile/android

# Generate release APK (uses keystore defined in gradle.properties)
./gradlew assembleRelease

# APK output path:
# app/build/outputs/apk/release/app-release.apk

# Verify APK signing certificate fingerprint
keytool -printcert -jarfile app/build/outputs/apk/release/app-release.apk

# Expected fingerprint (must match EXPECTED_RELEASE_CERT_SHA256 in deviceIntegrity.ts):
# E8:7A:B4:9C:2F:1D:6E:8A:3B:5C:7D:9E:0F:1A:2B:3C:4D:5E:6F:7A:8B:9C:0D:1E:2F:3A:4B:5C:6D:7E:8F:90
```

---

## 2. APK STATIC ANALYSIS (Kali)

```bash
# Install tools
sudo apt-get install -y apktool jadx dex2jar

# Decompile APK with apktool (checks ProGuard obfuscation)
apktool d app-release.apk -o jainune_decompiled/

# Inspect smali for hardcoded secrets (should find NONE)
grep -r "api_key\|secret\|password\|razorpay\|BASE_URL" jainune_decompiled/smali/ --include="*.smali"

# Convert DEX to JAR for Java decompilation
d2j-dex2jar.sh app-release.apk -o jainune_output.jar

# Open in JADX GUI for full source review
jadx-gui jainune_output.jar

# Check for plaintext HTTP endpoints (should find NONE — all HTTPS enforced)
grep -r "http://" jainune_decompiled/ | grep -v "https://"

# Check AndroidManifest for dangerous permissions
cat jainune_decompiled/AndroidManifest.xml | grep -E "uses-permission|debuggable|allowBackup"
# Expected: debuggable="false", allowBackup="false" in production
```

---

## 3. NETWORK TRAFFIC INTERCEPTION ATTEMPT (Should Fail Due to Pinning)

```bash
# Set up Burp Suite / mitmproxy proxy on Kali
mitmproxy --listen-host 0.0.0.0 --listen-port 8080

# On Android device: set proxy to Kali IP:8080, install mitmproxy CA cert
# Expected result: ALL requests to api.jainune.com fail with:
#   javax.net.ssl.SSLPeerUnverifiedException: Certificate pinning failure

# Verify SSL pinning is enforced for api.jainune.com
curl -v --proxy http://localhost:8080 https://api.jainune.com/v1/feed 2>&1 | grep -E "SSL|certificate|pin"
```

---

## 4. FRIDA DYNAMIC INSTRUMENTATION ATTEMPT (Should Be Detected)

```bash
# Install Frida on Kali
pip install frida-tools

# Push Frida server to rooted Android device
adb push frida-server-16.x.x-android-arm64 /data/local/tmp/frida-server
adb shell chmod 755 /data/local/tmp/frida-server
adb shell /data/local/tmp/frida-server &

# Attempt to hook Jainune process
frida -U -n com.jainune -l ssl_unpin.js

# Expected result:
# Jainune detects Frida on port 27042 within 500ms,
# calls terminateCompromisedSession(), purges tokens, and exits.
# SecurityBlockScreen shown before any auth content renders.

# Test Frida detection specifically
frida -U -n com.jainune --eval "console.log(ObjC.available)"
# Expected: process terminates before eval runs
```

---

## 5. ROOT DETECTION BYPASS ATTEMPT (Should Fail)

```bash
# Common Magisk hide bypass attempt
adb shell su -c "magiskhide add com.jainune"

# Jainune checks:
# /sbin/.magisk/ — detected
# /data/adb/magisk/ — detected
# /data/adb/ksu/ (KernelSU) — detected
# /data/adb/ap/ (APatch) — detected
# test-keys build tag — detected

# Expected: All checks fail with violation "DEVICE_ROOTED_OR_JAILBROKEN"
# App terminates before any profile data is accessible.
```

---

## 6. APK REPACKAGE / TAMPER ATTEMPT (Should Be Detected)

```bash
# Decompile, modify smali, repackage, resign with debug key
apktool d app-release.apk -o modified/
# ... edit modified/smali/com/jainune/... ...
apktool b modified/ -o modified_jainune.apk

# Sign with debug key (not production keystore)
jarsigner -verbose -keystore ~/.android/debug.keystore modified_jainune.apk androiddebugkey

# Install repackaged APK
adb install modified_jainune.apk

# Expected result:
# verifyApkSignatureIntegrity() detects fingerprint mismatch with EXPECTED_RELEASE_CERT_SHA256
# terminateCompromisedSession() purges all tokens
# SecurityBlockScreen: "This app installation appears to have been modified."
```

---

## 7. BACKEND SECURITY AUDIT (Kali → API)

```bash
# 1. Dependency vulnerability scan (run in backend/)
pip-audit --strict

# 2. SAST — bandit static analysis
bandit -r app/ -ll -f json -o bandit_report.json

# 3. SQL injection probe with sqlmap (against rate-limited test env only)
sqlmap -u "https://api-staging.jainune.com/v1/feed?limit=10" \
  --headers="Authorization: Bearer TEST_TOKEN" \
  --level=3 --risk=2 --dbms=postgresql --batch

# Expected: All parameterized queries prevent injection. No findings.

# 4. BOLA/IDOR test — attempt to access another user's chat
curl -H "Authorization: Bearer TOKEN_USER_A" \
  https://api.jainune.com/v1/chats/CHAT_ID_OF_USER_B/messages
# Expected: 403 Forbidden (RLS + app-level participant check)

# 5. Razorpay webhook replay attack test
# Send same webhook payload twice with same payment_id
curl -X POST https://api.jainune.com/v1/payments/webhook \
  -H "X-Razorpay-Signature: VALID_SIG" \
  -H "Content-Type: application/json" \
  -d '{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_test123","order_id":"order_test456","amount":99900}}}}'

# First call: activates subscription
# Second call (same payment_id): returns {"status":"already_processed"} — idempotency gate works

# 6. OTP brute force test (should hit 429 after 5 attempts)
for i in {1..6}; do
  curl -X POST https://api.jainune.com/v1/auth/verify-otp \
    -H "Content-Type: application/json" \
    -d "{\"phone\":\"+919999999999\",\"otp\":\"00000$i\"}"
  sleep 0.5
done
# Expected: 401 for first 5, then 429 + Redis OTP session deleted

# 7. Rate limit test on /v1/feed (max 20/min per SECURITY.md §10)
for i in {1..25}; do
  curl -H "Authorization: Bearer TOKEN" https://api.jainune.com/v1/feed &
done
wait
# Expected: First 20 return 200, remaining return 429

# 8. Secret detection in git history
trufflehog git file://. --since-commit HEAD~10 --json | jq .

# 9. Docker image vulnerability scan
trivy image jainune-backend:latest --severity HIGH,CRITICAL --format table

# 10. Semgrep SAST for SQL injection patterns
semgrep --config "p/sql-injection" backend/app/ --json | jq '.results | length'
# Expected: 0
```

---

## 8. FRONTEND SOURCE CODE AUDIT

```bash
# Check for hardcoded secrets in JS bundle
grep -r "secret\|api_key\|razorpay_key_id" mobile/src/ --include="*.ts" --include="*.tsx"
# Expected: NONE (Razorpay key received from server in order response, not hardcoded)

# Check for raw AsyncStorage usage (tokens must be in SecureStore only)
grep -r "AsyncStorage" mobile/src/ --include="*.ts" --include="*.tsx"
# Expected: NONE

# Verify all token storage uses SecureStore
grep -r "SecureStore" mobile/src/ --include="*.ts" --include="*.tsx"
# Expected: Only in client.ts (saveTokens, clearTokens, getAccessToken, getRefreshToken)

# Check no console.log leaking sensitive data in production
grep -r "console.log.*token\|console.log.*password\|console.log.*otp" mobile/src/
# Expected: NONE

# Verify input validation is applied before all API calls
grep -rn "validatePhone\|validateOtp\|validateMessage\|scanMessage" mobile/src/screens/
# Expected: Present in auth screens (validatePhone, validateOtp) and ChatScreen (scanMessage)

# Check PII regex coverage matches backend
grep -n "PII_PATTERNS\|phone_number\|instagram_handle\|phone_spaced_evasion" \
  mobile/src/security/inputValidation.ts
```

---

## 9. PROGUARD / CODE OBFUSCATION VERIFICATION

```bash
# Check that ProGuard/R8 is enabled for release builds
grep -A5 "buildTypes" mobile/android/app/build.gradle | grep "minifyEnabled"
# Expected: minifyEnabled true for release

# Verify mapping file is generated (for crash reporting)
ls mobile/android/app/build/outputs/mapping/release/mapping.txt
# Upload to Sentry/Crashlytics for deobfuscated crash reports

# Check class name obfuscation worked
cat jainune_decompiled/smali/com/jainune/ | head -20
# Sensitive class names should be obfuscated (a.b.c, etc.)
```

---

## 10. GEOLOCATION PRIVACY VERIFICATION

```bash
# Verify raw GPS is never returned from API
curl -H "Authorization: Bearer TOKEN" https://api.jainune.com/v1/feed | \
  python3 -c "import json,sys; data=json.load(sys.stdin); \
  [print('RAW GPS LEAK:', c.get('latitude'), c.get('longitude')) \
   for c in data.get('candidates',[])]"
# Expected: No latitude/longitude fields in any response

# Verify distance_display is quantized (no decimals under 2km)
curl -H "Authorization: Bearer TOKEN" https://api.jainune.com/v1/feed | \
  python3 -c "import json,sys; data=json.load(sys.stdin); \
  [print(c.get('distance_display')) for c in data.get('candidates',[])]"
# Expected values: "Under 2 km away", "5 km away", "12 km away" — never "1.3 km" or "3.47 km"
```

---

## SUMMARY: EXPECTED SECURITY POSTURE

| Attack Vector                  | Defense                            | Expected Result         |
|-------------------------------|-------------------------------------|------------------------|
| Burp Suite / Charles MITM     | SPKI certificate pinning            | SSLPeerUnverifiedException |
| Frida instrumentation         | TCP 27042 probe + native module     | App terminates          |
| APK decompile + resign        | Cert fingerprint mismatch check     | SecurityBlockScreen     |
| Root / Magisk / KernelSU      | Binary path + test-keys check       | SecurityBlockScreen     |
| OTP brute force               | Redis 5-attempt limit + HMAC        | 429 after 5 attempts    |
| Webhook replay                | Redis idempotency lock (24h TTL)    | already_processed ACK   |
| Price tampering               | Server-side amount from plan_id     | No effect               |
| BOLA/IDOR                     | RLS + participant verification      | 403 Forbidden           |
| Raw GPS extraction            | Geohash-6 snapping + no lat/lng API | No coordinates returned |
| Chat PII exfiltration         | Client regex + backend moderator    | Message blocked/flagged |
| Screenshot of chat            | FLAG_SECURE (MainActivity.java)     | Black screen in capture |
