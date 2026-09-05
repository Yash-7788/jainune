/**
 * Phase 8 — Input Validation & Sanitization
 *
 * All user inputs validated client-side BEFORE hitting the API.
 * Server validates again — this is defence-in-depth, not a substitute.
 *
 * Covers:
 * 1. Phone number (Indian E.164 format)
 * 2. OTP (6-digit numeric only)
 * 3. Name (Unicode letters, no injection chars)
 * 4. Chat messages (PII regex + length + injection chars)
 * 5. Prompt responses (length, HTML injection)
 * 6. Payment amounts (never from client — validated here too)
 * 7. Age gate (18+ enforcement)
 * 8. Regex patterns matching backend security filters (SECURITY.md §9)
 */

// ── Phone ─────────────────────────────────────────────────────────────────────

/** Accepts: +91XXXXXXXXXX or 10-digit Indian mobile */
const INDIAN_MOBILE_RE = /^(?:\+91|91)?[6-9]\d{9}$/;

export function validatePhone(raw: string): { valid: boolean; e164: string; error?: string } {
  const stripped = raw.replace(/[\s\-().]/g, "");
  if (!INDIAN_MOBILE_RE.test(stripped)) {
    return {
      valid: false,
      e164: "",
      error: "Enter a valid 10-digit Indian mobile number.",
    };
  }
  const digits = stripped.replace(/^(\+91|91)/, "");
  return { valid: true, e164: `+91${digits}` };
}

// ── OTP ──────────────────────────────────────────────────────────────────────

const OTP_RE = /^\d{6}$/;

export function validateOtp(raw: string): { valid: boolean; error?: string } {
  const stripped = raw.trim();
  if (!OTP_RE.test(stripped)) {
    return { valid: false, error: "OTP must be exactly 6 digits." };
  }
  return { valid: true };
}

// ── Name ─────────────────────────────────────────────────────────────────────

/**
 * Allows Unicode letters (Hindi, Gujarati, etc.), hyphens, spaces.
 * Blocks SQL injection chars, HTML injection, command injection.
 */
const NAME_ALLOWED_RE = /^[\p{L}\p{M}' \-]{1,50}$/u;
const INJECTION_RE = /[<>'"`;\\|&${}()\[\]]/;

export function validateName(raw: string): { valid: boolean; error?: string } {
  const trimmed = raw.trim();
  if (trimmed.length < 2) return { valid: false, error: "Name must be at least 2 characters." };
  if (trimmed.length > 50) return { valid: false, error: "Name too long." };
  if (INJECTION_RE.test(trimmed)) return { valid: false, error: "Name contains invalid characters." };
  if (!NAME_ALLOWED_RE.test(trimmed)) return { valid: false, error: "Name contains invalid characters." };
  return { valid: true };
}

// ── Chat Message ──────────────────────────────────────────────────────────────

export const MAX_MESSAGE_LENGTH = 1000;

/**
 * PII patterns — detected and flagged BEFORE sending.
 * Matches backend's content_filter.py patterns.
 * Includes spacing evasion variants (e.g. "9 8 7 6 5 4 3 2 1 0").
 */
export const PII_PATTERNS: { name: string; re: RegExp; isCritical: boolean }[] = [
  {
    name: "phone_number",
    // Indian mobile: 10 digits, optional spaces/dashes between, optional +91
    re: /(?:\+?91[\s\-]?)?[6-9]\d{3}[\s\-]?\d{3}[\s\-]?\d{4}/,
    isCritical: true,
  },
  {
    name: "phone_spaced_evasion",
    // Evasion: "9 8 7 6 5 4 3 2 1 0" or "9-8-7-6-5-4-3-2-1-0"
    re: /[6-9](?:[\s\-]\d){9}/,
    isCritical: true,
  },
  {
    name: "instagram_handle",
    re: /@[a-zA-Z0-9._]{1,30}/,
    isCritical: true,
  },
  {
    name: "whatsapp_link",
    re: /wa\.me\/|whatsapp\.com|bit\.ly\//i,
    isCritical: true,
  },
  {
    name: "url",
    re: /https?:\/\/[^\s]+/i,
    isCritical: true,
  },
  {
    name: "email_address",
    re: /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/,
    isCritical: true,
  },
  {
    name: "snapchat_handle",
    re: /snapchat\.com\/add\/|sc:\s*[a-zA-Z0-9._]+/i,
    isCritical: true,
  },
  {
    name: "telegram_handle",
    re: /t\.me\/|telegram\.me\/|@[a-zA-Z0-9_]{5,}/i,
    isCritical: false,
  },
  {
    name: "address_indicator",
    // Road/building number patterns common in Indian addresses
    re: /\b(?:flat|house|door|no\.?|#)\s*\d+/i,
    isCritical: false,
  },
];

export interface MessageScanResult {
  safe: boolean;
  detections: Array<{ name: string; isCritical: boolean; match: string }>;
}

export function scanMessage(text: string): MessageScanResult {
  const detections: MessageScanResult["detections"] = [];
  for (const pattern of PII_PATTERNS) {
    const match = text.match(pattern.re);
    if (match) {
      detections.push({ name: pattern.name, isCritical: pattern.isCritical, match: match[0] });
    }
  }
  return { safe: detections.length === 0, detections };
}

export function validateMessage(text: string): { valid: boolean; error?: string; scan?: MessageScanResult } {
  const trimmed = text.trim();
  if (trimmed.length === 0) return { valid: false, error: "Message cannot be empty." };
  if (trimmed.length > MAX_MESSAGE_LENGTH) {
    return { valid: false, error: `Message too long (max ${MAX_MESSAGE_LENGTH} chars).` };
  }
  // HTML/script injection
  if (/<script|<iframe|javascript:/i.test(trimmed)) {
    return { valid: false, error: "Message contains invalid content." };
  }
  const scan = scanMessage(trimmed);
  return { valid: true, scan };
}

export type DetectedSensitiveType = "phone" | "social" | "address" | "link" | null;

export function mapScanResultToDetectedType(scan?: MessageScanResult): DetectedSensitiveType {
  if (!scan || scan.safe || scan.detections.length === 0) return null;
  const name = scan.detections[0].name;
  if (name.includes("phone")) return "phone";
  if (name.includes("address")) return "address";
  if (name === "url" || name.includes("whatsapp")) return "link";
  return "social";
}


// ── Prompt Response ───────────────────────────────────────────────────────────

export function validatePromptResponse(text: string): { valid: boolean; error?: string } {
  const trimmed = text.trim();
  if (trimmed.length < 10) return { valid: false, error: "Response too short. Add a little more." };
  if (trimmed.length > 150) return { valid: false, error: "Response too long (max 150 chars)." };
  if (INJECTION_RE.test(trimmed)) return { valid: false, error: "Response contains invalid characters." };
  return { valid: true };
}

// ── Age Gate ─────────────────────────────────────────────────────────────────

export function validateAgeGate(dobIso: string): { valid: boolean; age: number; error?: string } {
  const dob = new Date(dobIso);
  const now = new Date();
  let age = now.getFullYear() - dob.getFullYear();
  if (
    now.getMonth() < dob.getMonth() ||
    (now.getMonth() === dob.getMonth() && now.getDate() < dob.getDate())
  ) {
    age--;
  }
  if (age < 18) {
    return {
      valid: false,
      age,
      error: "You must be at least 18 years old to use Jainune.",
    };
  }
  if (age > 80) {
    return { valid: false, age, error: "Please enter a valid date of birth." };
  }
  return { valid: true, age };
}

// ── Payment Guard ─────────────────────────────────────────────────────────────

/**
 * Validates that a Razorpay payment response has all required fields
 * before sending to verification endpoint.
 * Amount is NEVER validated here — server owns amount verification.
 */
export function validatePaymentResponse(obj: unknown): obj is {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
} {
  if (!obj || typeof obj !== "object") return false;
  const o = obj as Record<string, unknown>;
  return (
    typeof o.razorpay_payment_id === "string" && o.razorpay_payment_id.startsWith("pay_") &&
    typeof o.razorpay_order_id === "string" && o.razorpay_order_id.startsWith("order_") &&
    typeof o.razorpay_signature === "string" && o.razorpay_signature.length > 20
  );
}

// ── Email ─────────────────────────────────────────────────────────────────────

const EMAIL_RE = /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/;

export function validateEmail(raw: string): { valid: boolean; error?: string } {
  const trimmed = raw.trim().toLowerCase();
  if (!EMAIL_RE.test(trimmed)) {
    return { valid: false, error: "Enter a valid email address." };
  }
  if (trimmed.length > 254) {
    return { valid: false, error: "Email address too long." };
  }
  return { valid: true };
}
