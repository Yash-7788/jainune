# Logical Dependency Selection & Stepwise Upgrade Guide

A permanent engineering standard and architectural guide for package version selection, dependency lifecycle management, and zero-regression upgrades across all projects and ecosystems.

---

## 1. Universal Dependency Selection Principle

### Default to Latest Stable
- When scaffolding or starting any new project or adding new libraries (in Node.js, Python, Mobile, Go, Rust, DevOps, Docker, etc.), **always select the latest stable release**.
- **Rationale:** 
  1. Prevents immediate technical debt and obsolescence.
  2. Ensures latest security patches and zero-day mitigations are active.
  3. Complies with current and future platform / app store enforcement policies (e.g., Google Play API level requirements, Apple iOS SDK minimums).
  4. Minimizes downstream migration pain by keeping ecosystem distance as small as possible.

### The "Latest Isn't Optimal" Exception Protocol
If the latest version is **not** the best choice for a project (e.g., experimental/canary releases, major breaking ecosystem incompatibilities, deprecated native bridges, or unmaintained upstream peers):
- **Never silently downgrade or choose an older version without user alignment.**
- **Mandatory User Confirmation Gate:** You must proactively inform the user and request confirmation with a clear 3-part breakdown:
  1. **WHAT:** The exact version under consideration vs. the proposed alternative.
  2. **WHY:** Technical justification (e.g., "Library X does not support TurboModules in SDK 55 yet", or "v3 introduces an incompatible breaking database schema").
  3. **HOW:** How this specific version choice benefits the project, what tradeoffs are accepted, and the planned roadmap to advance when the ecosystem matures.

---

## 2. The Stepwise Upgrade Protocol ("One Hop at a Time")

When upgrading existing codebases across multiple major versions, **never perform multi-major leaps in a single step** (e.g., jumping directly from v1 to v4, or Expo SDK 51 directly to SDK 54). 

### The Protocol:
1. **Isolate on a Migration Branch:** Never perform multi-stage upgrades on `main`. Keep `main` deployable.
2. **Execute Single Major Hops (N → N+1):** Upgrade one major version at a time.
3. **Strict Verification Gate per Hop:**
   - Run dependency alignment (`expo install --fix` or equivalent package manager fix).
   - Run linter & strict static type checking (`tsc --noEmit`, `mypy`, `cargo check`).
   - Run bundler / compiler validation (e.g., `expo export`, `next build`, `pytest`).
   - Verify native plugins, configuration hooks, and security invariants survive prebuild/build.
4. **Commit & Push at Each Gate:** Create atomic, revertible git commits for each validated hop before touching the next major version.

---

## 3. Case Study & Incident Postmortem: The Jainune Mobile Incident

### Context & Initial State
- The Jainune mobile application was built on **Expo SDK 51** (React Native 0.74, React 18.2).
- Expo SDK 51 was pinned natively to Android 14 (compile/target SDK 34).

### The Trigger & Consequence of Shortcuts
- **External Driver:** Google Play requires all submissions and updates to target Android 15+ (API 35/36).
- **The Shortcut Failure:** Attempting to force compliance by manually editing `mobile/android/gradle.properties`:
  ```properties
  android.compileSdkVersion=35
  android.targetSdkVersion=35
  ```
- **The Fatal Crash:** In Android SDK 35 stubs, Google updated nullability annotations, marking `PackageInfo.requestedPermissions` as `@Nullable`. In Expo SDK 51's `expo-modules-core`, the Kotlin code had:
  ```kotlin
  packageInfo.requestedPermissions.contains(permission) // No null-safety check!
  ```
  The Kotlin compiler crashed immediately in CI with:
  `Only safe (?.) or non-null asserted (!!.) calls are allowed on a nullable receiver of type Array<(out) String!>?`
  Result: GitHub Actions Android release builds failed consistently.

### The Correct Systematic Solution: 3-Hop Incremental Migration
Instead of patching compiled vendor code or guessing, the team executed an incremental migration on branch `migration/expo-sdk-54`:

1. **Hop 1 (SDK 51 → SDK 52 | React Native 0.76):**
   - Removed hardcoded `"sdkVersion": "51.0.0"` in `app.json` (which was forcing npm to install SDK 51 packages even when package.json requested 52).
   - Removed redundant `@types/react-native` (native types now bundled in React Native 0.76+).
   - Added missing `expo-asset` required by SDK 52 Metro bundler.
   - **Gate 1 Passed:** 0 TypeScript errors; 1,429 modules bundled into Hermes `.hbc`.

2. **Hop 2 (SDK 52 → SDK 53 | React Native 0.79, React 19.0):**
   - React Native 0.79 advanced to React 19; aligned `@types/react` to `~19.0.10`.
   - Resolved breaking API in `expo-notifications`: added `shouldShowBanner: true` and `shouldShowList: true` to `NotificationBehavior`.
   - **Gate 2 Passed:** 0 TypeScript errors; 1,472 modules bundled into Hermes `.hbc`.

3. **Hop 3 (SDK 53 → SDK 54 | React Native 0.81, React 19.1, Native API 35/36):**
   - Aligned `@types/react` to `~19.1.10` and TypeScript to `~5.9.2`.
   - Added `babel-preset-expo` devDependency required by SDK 54.
   - Executed `npx expo prebuild --platform android --no-install`. Verified that:
     - `withAndroidSecurity.js` preserved `FLAG_SECURE` in `MainActivity.kt`.
     - `JainuneSecurityPackage()` preserved in `MainApplication.kt`.
     - Network security config and SSL pinning preserved.
     - Cloud backup credential exclusions added to manifest.
     - `expo-modules-core` upstream in SDK 54 now includes `requestedPermissions!!`, natively compiling against API 35/36 stubs without failure.
   - **Gate 3 Passed:** 0 TypeScript errors; 1,631 modules bundled into Hermes `.hbc` in 11.7s; backend test suite passed 351/351 tests.

### Outcome
- Restored **100% green CI** on `main`.
- Secured **2+ years of Google Play runway** (compliant through late 2027) on `migration/expo-sdk-54`.
- Maintained zero runtime regressions and preserved 100% of native security controls.
