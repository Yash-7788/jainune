/**
 * Jainune Security — barrel export
 * Import all security utilities from this single entry point.
 */

export { runSecurityBoot } from "./securityBoot";
export type { SecurityBootResult } from "./securityBoot";

export {
  performDeviceIntegrityCheck,
  terminateCompromisedSession,
  EXPECTED_RELEASE_CERT_SHA256,
} from "./deviceIntegrity";
export type { IntegrityCheckResult } from "./deviceIntegrity";

export {
  enableScreenCaptureProtection,
  disableScreenCaptureProtection,
  zeroizeBuffer,
  SPKI_PINS,
} from "./antiReversing";

export {
  validatePhone,
  validateOtp,
  validateName,
  validateMessage,
  validatePromptResponse,
  validateAgeGate,
  validateEmail,
  validatePaymentResponse,
  scanMessage,
  PII_PATTERNS,
} from "./inputValidation";
export type { MessageScanResult } from "./inputValidation";
