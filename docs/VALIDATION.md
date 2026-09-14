# Launch-hardening validation

Date: 14 September 2026. Baseline main: `9ed9fc5d1c6f190efb4fec32f067da9f4bfd2d3b`.

Review: [draft PR #2](https://github.com/Yash-7788/jainune/pull/2). GitHub reported `action_required` for the fork's [mobile compilation workflow](https://github.com/Yash-7788/jainune/actions/runs/34822080638) and [CI workflow](https://github.com/Yash-7788/jainune/actions/runs/34822080691). A repository maintainer must inspect and approve the fork workflow runs. No remote native-build success is claimed.

| Verification | Result |
| --- | --- |
| Backend suite (`pytest tests/unit tests/integration -q`) | **357 passed**, 1 warning; **73.24%** coverage against the required 70% |
| Added mobile regression suite (`npm test`) | **7 passed**, 0 failed |
| Mobile TypeScript (`npm run type-check`) | Pass |
| Mobile lint (`npm run lint`) | 0 errors, 158 warnings |
| Production JS export (`expo export --platform all`) | Android and iOS Hermes bundles exported successfully |
| Updated iOS config generation | `expo prebuild --platform ios --no-install` succeeded in a temporary copy; custom security pod and notification entitlement generated |
| Static endpoint script | 64 client call patterns, 109 backend routes; no reported path mismatch |
| Patch whitespace | `git diff --check` passed |
| Dependency installation | Baseline and PR #1 `npm ci --legacy-peer-deps` succeeded; backend requirements installed in an isolated Python 3.12 environment |
| Dependency security | **Unresolved**: npm 41 affected entries (1 critical, 11 high); Python 43 advisory instances across six packages |
| PR #1 | Standard TypeScript command fails; ten further diagnostics after opting past the TypeScript 6 deprecation error |

Backend tests use mocks/fakeredis and do not establish real database/provider integration. Four initial push tests failed because httpx 0.27 could not parse this workspace's SOCKS proxy environment; the suite passed when proxy variables were omitted for mocked tests. No networking behavior was changed in the application to pass those tests.

New regressions cover: unknown backend environments, metric cardinality and profile-ID privacy, release endpoint configuration, REST/WebSocket environment consistency, iOS Podfile preservation, no silent Play-to-Razorpay fallback, no iOS-to-Razorpay fallback, Android notification permission order and the incompatible APNs/FCM fallback.

No Android SDK, Xcode, Apple signing identity or store credentials are configured in this workspace. Updated Android native source has been reconciled with the SDK 51 Expo template, but has not been compiled or run here. iOS native project generation is not a CocoaPods build or signed archive. No signed AAB/IPA, store submission, live deployment or real-device acceptance is claimed.

## Reproduction

From `mobile/`:

```sh
npm ci --legacy-peer-deps
npm test
npm run type-check
npm run lint
JAINUNE_BUILD_ENV=production \
EXPO_PUBLIC_API_URL=https://api.jainune.com/v1 \
EXPO_PUBLIC_WS_URL=wss://api.jainune.com/v1/ws/chat \
npx expo export --platform all
```

With Java 17 and the appropriate Android SDK installed, compilation-only validation is:

```sh
cd mobile/android
./gradlew bundleRelease -PJAINUNE_ALLOW_UNSIGNED_RELEASE=true
```

That output is deliberately unsigned. For store signing, configure all four `JAINUNE_RELEASE_STORE_FILE`, `JAINUNE_RELEASE_STORE_PASSWORD`, `JAINUNE_RELEASE_KEY_ALIAS`, and `JAINUNE_RELEASE_KEY_PASSWORD` Gradle properties in protected local/CI configuration and omit the unsigned flag. Signing alone does not clear the open launch blockers.

From `backend/` in an isolated environment:

```sh
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/unit tests/integration -q
pip-audit -r requirements.txt
```

The dependency audit is expected to report outstanding findings on this baseline. Resolve supported-version migrations, then rerun scans; do not convert scan failures into a production-ready claim.
