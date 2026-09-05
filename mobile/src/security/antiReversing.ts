/**
 * Jainune Anti-Reversing, Code Obfuscation & Screen Protection Specification
 * 
 * 1. Screen Capture / Screen Recording Protection:
 *    Prevents attackers or spyware from screenshotting or recording private Jain profile data.
 * 
 * 2. SSL/TLS Public Key Pinning (HPKP / SPKI):
 *    Prevents MITM proxies (Kali Burp Suite, Charles Proxy, mitmproxy).
 * 
 * 3. In-Memory Key Zeroization:
 *    Ensures tokens and keys are overwritten in memory with zeros before garbage collection.
 */

import { NativeModules, Platform } from "react-native";

export const SPKI_PINS = [
  // Primary pin for api.jainune.com (SHA-256 Subject Public Key Info)
  "sha256/k20YWfohKw3kUj5t5K65soVIyzxPCQFvMQkxZpmGsoo=",
  // Backup disaster-recovery certificate pin
  "sha256/WoiWRyIOVNa9ihaBciRSC7XHjliYS9VwUGOIud4PB18=",
];

/**
 * Activates OS-level screenshot and screen recording blocking (FLAG_SECURE).
 */
export function enableScreenCaptureProtection(): void {
  if (Platform.OS === "android") {
    if (NativeModules.JainuneSecurityModule?.enableFlagSecure) {
      NativeModules.JainuneSecurityModule.enableFlagSecure();
    }
  }
}

/**
 * Deactivates FLAG_SECURE if explicitly navigating to public non-sensitive screens.
 */
export function disableScreenCaptureProtection(): void {
  if (Platform.OS === "android") {
    if (NativeModules.JainuneSecurityModule?.disableFlagSecure) {
      NativeModules.JainuneSecurityModule.disableFlagSecure();
    }
  }
}

/**
 * Cryptographically zeroizes sensitive token buffers in memory.
 */
export function zeroizeBuffer(buffer: Uint8Array | number[]): void {
  if (Array.isArray(buffer)) {
    for (let i = 0; i < buffer.length; i++) {
      buffer[i] = 0;
    }
  } else if (buffer instanceof Uint8Array) {
    buffer.fill(0);
  }
}
