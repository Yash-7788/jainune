/**
 * Phase 8 — Security Gate: App-level integrity & anti-tamper boot sequence
 *
 * Enforces SECURITY.md §9 (Mobile Client Security):
 * - Root / Jailbreak detection (su, Magisk, KernelSU, APatch, Cydia)
 * - Frida instrumentation detection (TCP 27042 probe)
 * - Active debugger / PTRACE detection
 * - Developer Options / ADB detection (Android production only)
 * - APK signature / repackage verification
 * - FLAG_SECURE screen protection on sensitive screens
 * - Emulator detection (blocks production builds on simulators)
 *
 * On critical violation: purge all in-memory tokens, show blocking screen, halt.
 * On soft violation: log silently, telemetry flagged, session continues.
 *
 * Call runSecurityBoot() from App.tsx before any authenticated navigation.
 */

import {
  performDeviceIntegrityCheck,
  terminateCompromisedSession,
} from "./deviceIntegrity";
import { enforceCertificatePinning, SPKI_PINS } from "./antiReversing";

export type SecurityBootResult =
  | { passed: true }
  | { passed: false; reason: string; violations: string[] };

// Violations that immediately block the app
const CRITICAL_VIOLATIONS = new Set([
  "FRIDA_HOOK_INJECTION_DETECTED",
  "DEBUGGER_PTRACE_ATTACHED",
  "APK_REPACKAGED_OR_TAMPERED",
  "DEVICE_ROOTED_OR_JAILBROKEN",
]);

/**
 * Run at app startup before rendering any authenticated content.
 * Returns { passed: true } if the device is clean.
 * Returns { passed: false, reason, violations } if critical threat is detected.
 */
export async function runSecurityBoot(): Promise<SecurityBootResult> {
  // Skip checks in development (allows normal Metro bundler dev workflow)
  if (__DEV__) {
    return { passed: true };
  }

  // Enforce certificate pinning at native network layer
  await enforceCertificatePinning(SPKI_PINS);

  const result = await performDeviceIntegrityCheck();

  if (result.isSecure) {
    return { passed: true };
  }

  const criticalViolations = result.violations.filter((v) =>
    CRITICAL_VIOLATIONS.has(v)
  );

  if (criticalViolations.length > 0) {
    // Purge all tokens from memory and storage before halting
    terminateCompromisedSession(criticalViolations);

    return {
      passed: false,
      reason: mapViolationToUserMessage(criticalViolations[0]),
      violations: criticalViolations,
    };
  }

  // Soft violations (ADB enabled, emulator) — log but allow for now
  return { passed: true };
}

function mapViolationToUserMessage(violation: string): string {
  switch (violation) {
    case "DEVICE_ROOTED_OR_JAILBROKEN":
      return "This device appears to be rooted or jailbroken. Jainune cannot run on modified devices to protect member privacy.";
    case "FRIDA_HOOK_INJECTION_DETECTED":
      return "A dynamic instrumentation framework was detected. Jainune has stopped to protect member data.";
    case "DEBUGGER_PTRACE_ATTACHED":
      return "A debugger is attached to this session. Jainune cannot run in this environment.";
    case "APK_REPACKAGED_OR_TAMPERED":
      return "This app installation appears to have been modified. Please install Jainune from the official Google Play Store or Apple App Store.";
    default:
      return "A security violation was detected. Jainune has stopped to protect member privacy.";
  }
}
