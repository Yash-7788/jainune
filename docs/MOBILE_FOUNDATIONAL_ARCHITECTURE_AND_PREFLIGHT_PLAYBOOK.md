# Mobile Foundational Architecture & Pre-Flight Verification Playbook

## 1. Retrospective & Architectural Critique

### Core Failure Analysis
During the initial development cycles of this project, focus was placed on high-level UI component structure, mock API contracts, and business logic state machines. However, **foundational native bootstrap and packaging prerequisites were neglected**:
- Basic OS-level application resources (`styles.xml`, `strings.xml`, `mipmap` icons) were never created in the Android source tree.
- The JavaScript bundler blueprint (`metro.config.js`) was absent.
- Breaking transitive package overrides were introduced to satisfy vulnerability scanners without verifying native build toolchain contracts.
- Custom iOS native pods were injected into the main application namespace, causing compiler header collisions.

Because these first-order requirements were not validated at project bootstrap, they surfaced as a cascading chain of fatal failures at the production release packaging phase. Instead of resolving all foundational prerequisites systematically in a single pass, fixes were applied reactively across multiple CI cycles.

### Foundational Law
> **"First Priority: Load and Package Before Testing Logic."**  
> An application that cannot compile a clean native binary, resolve its launcher icons, or initialize its JavaScript engine has zero functional value regardless of how many feature tests pass. Native bootability must always be verified before functional testing.

---

## 2. Active Package Overrides Audit

### Current Status
There is **only one override** across the entire repository:

```json
// mobile/package.json
"overrides": {
  "tar": "^6.2.1"
}
```

- **Why it exists**: `@expo/cli` (Expo SDK 51) depends on `tar@6` and invokes `tar.extract(...)` during `npx expo prebuild`. `tar@6.2.1` includes all security patches for the v6 tree while preserving the API contract.
- **Verification**: Confirmed zero other `overrides`, `resolutions`, or `pnpm` override blocks exist anywhere in `mobile/package.json` or root project manifests.

---

## 3. Case Studies: The 5 Fatal Build-Time Errors

### Case Study 1: React Native Version Mismatch in Android Autolinking
- **Fatal Error**:
  ```text
  Could not find method autolinkLibrariesWithApp() for arguments [...] on project ':app'
  ```
- **Root Cause**: React Native 0.75+ introduced `autolinkLibrariesWithApp(dependencies)` in `app/build.gradle`. Our project targets React Native 0.74.5 / Expo SDK 51. Attempting to use 0.75+ syntax on 0.74 crashed Gradle during configuration.
- **The One-Shot Prevention Rule**:
  - Always verify React Native version before editing Gradle files:
    - For **RN 0.74.x**: Use legacy autolinking hook:
      ```groovy
      apply from: file("../../node_modules/@react-native-community/cli-platform-android/native_modules.gradle"); applyNativeModulesAppBuildGradle(project)
      ```
    - For **RN 0.75.x+**: Use `autolinkLibrariesWithApp()`.

---

### Case Study 2: Missing Metro Bundler Configuration
- **Fatal Error**:
  ```text
  Task :app:createBundleReleaseJsAndAssets
  warn From React Native 0.73, your project's Metro config should extend '@react-native/metro-config' or it will fail to build.
  ```
- **Root Cause**: Expo bare-workflow projects require `metro.config.js` extending `expo/metro-config` to correctly resolve assets, platform extensions, and Hermes bytecode bundling.
- **The One-Shot Prevention Rule**:
  - Every React Native / Expo project must have [mobile/metro.config.js](file:///c:/Users/yashk/Downloads/jainune/mobile/metro.config.js) created at Day 0:
    ```javascript
    const { getDefaultConfig } = require('expo/metro-config');
    const config = getDefaultConfig(__dirname);
    module.exports = config;
    ```

---

### Case Study 3: Missing Android Native Identity Resources (AAPT Linking)
- **Fatal Error**:
  ```text
  Execution failed for task ':app:processReleaseResources'.
  AAPT: error: resource mipmap/ic_launcher not found.
  AAPT: error: resource mipmap/ic_launcher_round not found.
  AAPT: error: resource style/AppTheme not found.
  ```
- **Root Cause**: `AndroidManifest.xml` referenced `@style/AppTheme`, `@mipmap/ic_launcher`, `@mipmap/ic_launcher_round`, and `@string/app_name`. However, `res/` only contained `xml/network_security_config.xml`. All base XML values and image drawables were missing.
- **The One-Shot Prevention Rule**:
  - Run a pre-flight resource audit before attempting native compilation. Every `@type/name` referenced in `AndroidManifest.xml` must physically exist:
    - `res/values/styles.xml` -> `<style name="AppTheme" ...>`
    - `res/values/strings.xml` -> `<string name="app_name">Jainune</string>`
    - `res/values/colors.xml` -> base background & splash colors
    - `res/mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/` -> `ic_launcher.png`, `ic_launcher_round.png`

---

### Case Study 4: Breaking Transitive Package Override (`tar@7`)
- **Fatal Error**:
  ```text
  - Creating native directory (./ios)
  Cannot read properties of undefined (reading 'extract')
  ✖ Failed to create the native directory
  ```
- **Root Cause**: Blindly adding `"tar": "^7.5.22"` to `overrides` in `package.json` to satisfy an `npm audit` critical alert. `tar@7` completely rewrote its export architecture (swapping `tar.extract` for `tar.x` / named ESM exports). `@expo/cli` invoked `tar.extract()`, which evaluated to `undefined` and crashed during `npx expo prebuild`.
- **The One-Shot Prevention Rule**:
  - **NEVER** force-override a transitive dependency across major version boundaries (`v6 -> v7`) without verifying whether parent tooling relies on deprecated/removed APIs.
  - Pin to the latest patched release of the supported major line (`^6.2.1`).

---

### Case Study 5: Native Pod Namespace & Header Collision
- **Fatal Error**:
  ```text
  JainuneSecurityModule.build/.../main.o
  AppDelegate.h:3:9: fatal error: 'Expo/Expo.h' file not found
  #import <Expo/Expo.h>
  ```
- **Root Cause**: The custom Config Plugin (`withIosSecurity.js`) copied `JainuneSecurityModule.podspec`, `.h`, and `.m` into `ios/Jainune/`. Because `ios/Jainune/` also contained `main.m` and `AppDelegate.h`, the podspec's wildcard matcher `s.source_files = "*.{h,m}"` caused CocoaPods to compile the application entry point inside the pod target. Because the pod only declared `React-Core` as a dependency (not `Expo`), compilation exploded.
- **The One-Shot Prevention Rule**:
  - Native pods must reside in their **own dedicated subdirectory**:
    - Directory: `ios/JainuneSecurityModule/` (never `ios/Jainune/` or root `ios/`).
    - Explicit file pattern: `s.source_files = "JainuneSecurityModule.{h,m}"` (never wildcard `*.{h,m}`).

---

## 4. Single-Pass Mobile Pre-Flight Protocol

Before testing UI functionality or pushing mobile code to CI, run this deterministic 5-phase pre-flight check:

### Phase 1: Dependency & Override Integrity
```bash
cd mobile
# 1. Verify no conflicting or breaking major overrides exist
git grep "overrides" package.json
# 2. Verify lockfile is in sync with package.json
npm install --package-lock-only --legacy-peer-deps
```

### Phase 2: Static Resource & Manifest Audit
Verify that every resource identifier in Android and iOS manifests exists on disk:
- **Android**:
  - `mobile/android/app/src/main/res/values/styles.xml` defines `AppTheme`.
  - `mobile/android/app/src/main/res/values/strings.xml` defines `app_name`.
  - `mobile/android/app/src/main/res/mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/` contain both `ic_launcher.png` and `ic_launcher_round.png`.
- **iOS**:
  - `mobile/app.json` defines valid paths for `icon`, `adaptiveIcon`, and `splash`.
  - Custom plugins isolate native files to dedicated subdirectories (`ios/<PluginName>/`).

### Phase 3: Bundler & TypeScript Compilation
```bash
cd mobile
# 1. Verify TypeScript compiles with zero errors
npm run type-check
# 2. Verify Expo configuration resolves cleanly
npx expo config --type public
```

### Phase 4: Native Android Dry-Run (Local or Sandbox)
```bash
cd mobile/android
# Test resource linking and assemble debug/release tasks
./gradlew processReleaseResources
```

### Phase 5: CI Guardrails
- Build-time developer CLI tool audits (`npm audit`) must run with `continue-on-error: true` or `--omit=dev` so transitivity in build tooling does not block runtime release bundles.
- Workflows must scope `paths: ['mobile/**']` to avoid unnecessary expensive macOS runner usage on backend-only commits.
