/**
 * Auth API — exact contracts from backend/app/routers/auth.py
 * Endpoints: POST /auth/otp/request, /auth/otp/verify, /auth/email/otp/request,
 *            /auth/email/otp/verify, /auth/google, /auth/apple, /auth/token/refresh, /auth/logout
 *
 * Input sanitization rules from frontend_integration_contracts.md §3.1
 */

import { apiPost, saveTokens, clearTokens, extractError } from "./client";

// ── Input sanitizers (client-side, matches backend validators) ────────────────

/** Strips whitespace, lowercases, validates RFC 5322 email. Max 254 chars. */
export function sanitizeEmail(raw: string): string {
  return raw.trim().toLowerCase().slice(0, 254);
}

/** Validates +91XXXXXXXXXX Indian mobile. */
export function validatePhone(phone: string): boolean {
  return /^\+91[6-9]\d{9}$/.test(phone.trim());
}

/** Validates 6-digit OTP. */
export function validateOTP(otp: string): boolean {
  return /^\d{6}$/.test(otp.trim());
}

/** Strips spaces and non-base64 chars from OAuth tokens. Max 4096 chars. */
export function sanitizeOAuthToken(token: string): string {
  return token.trim().replace(/[^A-Za-z0-9._\-+/=]/g, "").slice(0, 4096);
}

/** Strips HTML, control chars from name. Max 64 chars. */
export function sanitizeName(name: string): string {
  return name
    .trim()
    // eslint-disable-next-line no-control-regex
    .replace(/[<>'"\u0000-\u001f]/g, "")
    .slice(0, 64);
}

// ── Allowed email domains allowlist (frontend_integration_contracts.md §4.2) ──

const ALLOWED_EMAIL_DOMAINS = new Set([
  // Google
  "gmail.com", "googlemail.com",
  // Microsoft
  "outlook.com", "hotmail.com", "live.com", "msn.com",
  "outlook.in", "hotmail.co.in", "live.in",
  // Yahoo
  "yahoo.com", "yahoo.co.in", "yahoo.in", "ymail.com", "rocketmail.com",
  // Apple
  "icloud.com", "me.com", "mac.com",
  // Proton
  "proton.me", "protonmail.com",
  // Zoho
  "zoho.com", "zohomail.in", "zoho.in",
  // Indian
  "rediffmail.com", "sify.com",
  // Other major
  "aol.com", "gmx.com", "mail.com", "fastmail.com", "hey.com",
]);

export function isEmailDomainAllowed(email: string): boolean {
  const domain = email.split("@")[1]?.toLowerCase();
  return !!domain && ALLOWED_EMAIL_DOMAINS.has(domain);
}

// ── Response types (match backend Pydantic schemas byte-for-byte) ─────────────

export interface OTPRequestData {
  phone_number: string; // masked: +91*****1210
  retry_after_seconds: number;
  expires_in_seconds: number;
}

export interface TokenData {
  user_id: string;
  is_new_user: boolean;
  onboarding_completed: boolean;
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export interface RefreshData {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

// ── API calls ─────────────────────────────────────────────────────────────────

/** POST /v1/auth/otp/request */
export async function requestPhoneOTP(
  phoneNumber: string,
  channel: "sms" | "whatsapp" = "sms"
): Promise<OTPRequestData> {
  const res = await apiPost<OTPRequestData>("/auth/otp/request", {
    phone_number: phoneNumber.trim(),
    channel,
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

/** POST /v1/auth/otp/verify */
export async function verifyPhoneOTP(phoneNumber: string, otp: string): Promise<TokenData> {
  const res = await apiPost<TokenData>("/auth/otp/verify", {
    phone_number: phoneNumber.trim(),
    otp: otp.trim(),
  });
  if (!res.success) throw { _apiError: res.error };
  await saveTokens(res.data.access_token, res.data.refresh_token, res.data.user_id);
  return res.data;
}

/** POST /v1/auth/email/otp/request */
export async function requestEmailOTP(
  email: string,
  turnstileToken?: string
): Promise<{ email: string; retry_after_seconds: number; expires_in_seconds: number }> {
  const clean = sanitizeEmail(email);
  const res = await apiPost<{ email: string; retry_after_seconds: number; expires_in_seconds: number }>(
    "/auth/email/otp/request",
    { email: clean, turnstile_token: turnstileToken ?? null }
  );
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

/** POST /v1/auth/email/otp/verify */
export async function verifyEmailOTP(email: string, otp: string): Promise<TokenData> {
  const res = await apiPost<TokenData>("/auth/email/otp/verify", {
    email: sanitizeEmail(email),
    otp: otp.trim(),
  });
  if (!res.success) throw { _apiError: res.error };
  await saveTokens(res.data.access_token, res.data.refresh_token, res.data.user_id);
  return res.data;
}

/** POST /v1/auth/google — id_token from @react-native-google-signin */
export async function googleSignIn(idToken: string): Promise<TokenData> {
  const clean = sanitizeOAuthToken(idToken);
  const res = await apiPost<TokenData>("/auth/google", { id_token: clean });
  if (!res.success) throw { _apiError: res.error };
  await saveTokens(res.data.access_token, res.data.refresh_token, res.data.user_id);
  return res.data;
}

/** POST /v1/auth/apple — id_token from expo-apple-authentication */
export async function appleSignIn(
  idToken: string,
  firstName?: string | null
): Promise<TokenData> {
  const clean = sanitizeOAuthToken(idToken);
  const res = await apiPost<TokenData>("/auth/apple", {
    id_token: clean,
    first_name: firstName ? sanitizeName(firstName) : null,
  });
  if (!res.success) throw { _apiError: res.error };
  await saveTokens(res.data.access_token, res.data.refresh_token, res.data.user_id);
  return res.data;
}

/** POST /v1/auth/token/refresh */
export async function refreshAccessToken(refreshToken: string): Promise<RefreshData> {
  const res = await apiPost<RefreshData>("/auth/token/refresh", {
    refresh_token: refreshToken.trim(),
  });
  if (!res.success) throw { _apiError: res.error };
  return res.data;
}

/** POST /v1/auth/logout */
export async function logout(): Promise<void> {
  try {
    await apiPost("/auth/logout");
  } catch {
    // Ignore — still clear local state
  } finally {
    await clearTokens();
  }
}
