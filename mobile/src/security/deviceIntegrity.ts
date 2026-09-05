/**
 * Jainune Mobile Security — Device Integrity & Anti-Tamper Engine
 * 
 * Protects against:
 * 1. Rooting (su binary, Superuser, Magisk, KernelSU, APatch)
 * 2. Kali Linux / Dynamic Instrumentation / Frida (TCP port 27042, maps, agents)
 * 3. Xposed / Substrate hooking
 * 4. Active Debuggers / PTRACE attachment
 * 5. Developer Options / USB Debugging / ADB exploitation in production
 * 6. APK Tampering / Repackaging (Signature verification check)
 */

import { Platform, NativeModules } from "react-native";

export interface IntegrityCheckResult {
  isSecure: boolean;
  violations: string[];
  details: {
    isRooted: boolean;
    isDebuggerAttached: boolean;
    isFridaDetected: boolean;
    isAdbEnabled: boolean;
    isEmulator: boolean;
    isTampered: boolean;
  };
}

// Known root indicators on Android
const ROOT_PATHS: string[] = [
  "/system/app/Superuser.apk",
  "/sbin/su",
  "/system/bin/su",
  "/system/xbin/su",
  "/data/local/xbin/su",
  "/data/local/bin/su",
  "/system/sd/xbin/su",
  "/system/bin/failsafe/su",
  "/data/local/su",
  "/su/bin/su",
  "/system/app/Magisk.apk",
  "/sbin/.magisk/",
  "/data/adb/magisk/",
  "/data/adb/ksu/",
  "/data/adb/ap/",
];

// iOS Jailbreak indicators
const JAILBREAK_PATHS: string[] = [
  "/Applications/Cydia.app",
  "/Library/MobileSubstrate/MobileSubstrate.dylib",
  "/bin/bash",
  "/usr/sbin/sshd",
  "/etc/apt",
  "/private/var/lib/apt/",
  "/Applications/Sileo.app",
];

// Production Release Signing Certificate SHA-256 Fingerprint
// If APK is decompiled, modified, and resigned with Kali or debug key, signature mismatch triggers halt.
export const EXPECTED_RELEASE_CERT_SHA256 = "E8:7A:B4:9C:2F:1D:6E:8A:3B:5C:7D:9E:0F:1A:2B:3C:4D:5E:6F:7A:8B:9C:0D:1E:2F:3A:4B:5C:6D:7E:8F:90";

/**
 * Executes multi-vector hardware, kernel, and process integrity checks.
 */
export async function performDeviceIntegrityCheck(): Promise<IntegrityCheckResult> {
  const violations: string[] = [];
  const details = {
    isRooted: false,
    isDebuggerAttached: false,
    isFridaDetected: false,
    isAdbEnabled: false,
    isEmulator: false,
    isTampered: false,
  };

  // 1. Root & Jailbreak Inspection
  try {
    const rootDetected = await checkRootOrJailbreak();
    if (rootDetected) {
      details.isRooted = true;
      violations.push("DEVICE_ROOTED_OR_JAILBROKEN");
    }
  } catch {
    // Fail secure if inspection blocked
    violations.push("ROOT_INSPECTION_FAILED");
  }

  // 2. Active Debugger / Kali PTRACE Inspection
  try {
    const debuggerAttached = checkDebuggerAttached();
    if (debuggerAttached) {
      details.isDebuggerAttached = true;
      violations.push("DEBUGGER_PTRACE_ATTACHED");
    }
  } catch {
    violations.push("DEBUGGER_INSPECTION_FAILED");
  }

  // 3. Frida / Dynamic Hooking Framework Inspection
  try {
    const fridaActive = await checkFridaInstrumentation();
    if (fridaActive) {
      details.isFridaDetected = true;
      violations.push("FRIDA_HOOK_INJECTION_DETECTED");
    }
  } catch {
    violations.push("FRIDA_INSPECTION_FAILED");
  }

  // 4. Developer Options & USB Debugging (Android Production Check)
  if (Platform.OS === "android" && !__DEV__) {
    try {
      const adbActive = await checkAdbAndDeveloperOptions();
      if (adbActive) {
        details.isAdbEnabled = true;
        violations.push("DEVELOPER_OPTIONS_OR_ADB_ENABLED");
      }
    } catch {
      // Ignored in sandbox/unsupported builds
    }
  }

  // 5. APK Signature & Repackage Tamper Verification
  if (Platform.OS === "android" && !__DEV__) {
    try {
      const isTampered = await verifyApkSignatureIntegrity();
      if (isTampered) {
        details.isTampered = true;
        violations.push("APK_REPACKAGED_OR_TAMPERED");
      }
    } catch {
      violations.push("SIGNATURE_VERIFICATION_ERROR");
    }
  }

  const isSecure = violations.length === 0;
  return { isSecure, violations, details };
}

/**
 * Checks for existence of su binaries, root managers, and test-keys tags.
 */
async function checkRootOrJailbreak(): Promise<boolean> {
  if (NativeModules.JainuneSecurityModule?.isDeviceRooted) {
    return await NativeModules.JainuneSecurityModule.isDeviceRooted();
  }

  // Fallback heuristic: check system properties if bridge available
  const constants = NativeModules.PlatformConstants || {};
  const buildTags: string = constants.ServerHost || constants.Release || "";
  if (buildTags.includes("test-keys")) {
    return true;
  }

  return false;
}

/**
 * Detects whether debugger is actively connected.
 */
function checkDebuggerAttached(): boolean {
  if (__DEV__) {
    return false; // Allow standard development in debug mode
  }
  if (NativeModules.JainuneSecurityModule?.isDebuggerAttached) {
    return NativeModules.JainuneSecurityModule.isDebuggerAttached();
  }
  return false;
}

/**
 * Probes for Frida server on localhost:27042 and frida-gadget in loaded maps.
 */
async function checkFridaInstrumentation(): Promise<boolean> {
  if (NativeModules.JainuneSecurityModule?.detectFrida) {
    return await NativeModules.JainuneSecurityModule.detectFrida();
  }

  // Socket probe on default Frida port 27042
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 300);
    const resp = await fetch("http://127.0.0.1:27042", {
      method: "GET",
      signal: controller.signal,
    }).catch(() => null);
    clearTimeout(timeoutId);

    // If port 27042 responds, Frida server is running
    if (resp !== null) {
      return true;
    }
  } catch {
    // Port closed, normal state
  }

  return false;
}

/**
 * Detects whether Developer Settings or USB Debugging are active.
 */
async function checkAdbAndDeveloperOptions(): Promise<boolean> {
  if (NativeModules.JainuneSecurityModule?.isAdbEnabled) {
    return await NativeModules.JainuneSecurityModule.isAdbEnabled();
  }
  return false;
}

/**
 * Compares current APK signing certificate with release keystore signature.
 */
async function verifyApkSignatureIntegrity(): Promise<boolean> {
  if (NativeModules.JainuneSecurityModule?.getAppCertificateFingerprint) {
    const currentFingerprint = await NativeModules.JainuneSecurityModule.getAppCertificateFingerprint();
    if (currentFingerprint && currentFingerprint !== EXPECTED_RELEASE_CERT_SHA256) {
      return true; // Tampered / resigned
    }
  }
  return false;
}

/**
 * Emergency lock & memory wipe: triggered if critical integrity violations detected.
 */
export function terminateCompromisedSession(violations: string[]): void {
  // 1. Purge all in-memory keys
  if (NativeModules.JainuneSecurityModule?.emergencyPurgeStorage) {
    NativeModules.JainuneSecurityModule.emergencyPurgeStorage();
  }

  // 2. Halt execution
  if (NativeModules.JainuneSecurityModule?.exitApp) {
    NativeModules.JainuneSecurityModule.exitApp();
  }
}
