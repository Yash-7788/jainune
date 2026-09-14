# Jainune launch readiness

Review date: 14 September 2026. Baseline: `Yash-7788/jainune` main at `9ed9fc5d1c6f190efb4fec32f067da9f4bfd2d3b`. Also inspected PR #1 at `9c77478e9141e62e921542681c19b6a30f01934b`.

**Release decision: not ready for public Android or iOS launch.** This branch contains launch-hardening changes, not a signed or approved production release. Historical audit documents are not release certificates; their claims of zero vulnerabilities and 100% readiness are contradicted by the billing implementation, dependency scans, and native configuration.

## Product and system understanding

Jainune is an adult Jain relationship and matchmaking product. Its strongest distinct features are cultural and dietary compatibility, respectful communication, voice introductions, and local community density. The essential product loop is signup → adult profile → discover → contextual like → mutual match → conversation → report/block or a consensual next step.

The repository contains 296 tracked files at baseline and 39 mobile screen files. This review mapped the repository, compared specifications and audit documents, inspected launch-critical code paths and infrastructure, ran the existing tests and JS bundles, and reviewed the open upgrade PR. It is not a line-by-line security certification, a live penetration test, or proof of cloud configuration.

| Area | Implementation and responsibility |
| --- | --- |
| Mobile | Expo SDK 51 / React Native 0.74.5, React Navigation, Zustand, SecureStore; four tabs: Discover, Likes, Chats, Profile |
| Authentication | FastAPI phone/email OTP, Google and Apple tokens, RS256 access tokens and refresh rotation |
| Onboarding | Multi-step profile flow, adult age validation, Jain preferences, location, media, prompts and consent |
| Discovery | PostgreSQL/PostGIS geographic filtering, reciprocal preferences, pgvector behavior signals; daily pairing workers |
| Interaction and messaging | Mutual matching, quotas, message idempotency, ticket-authenticated WebSockets, moderation and blocking |
| Storage | S3 quarantine, moderation/sanitization, media promotion and deletion workers |
| Background work | Celery workers and beat, Redis queues/caches, notifications, telemetry, expiration and matching |
| Monetization | Razorpay subscriptions and arcade orders; a custom authenticated store-event adapter exists, but native store purchases and verification are incomplete |
| Operations | Docker Compose, Nginx, Cloudflare configuration, GitHub Actions, 25 forward SQL migrations plus down scripts |

The mobile architecture can serve both platforms. A second native app codebase is unnecessary. The checked-in Android project must nevertheless be maintained alongside Expo config; editing `app.json` does not automatically synchronize it.

## Confirmed findings and disposition

| Priority | Finding and evidence | This branch / remaining requirement |
| --- | --- | --- |
| P0 | `billingService.ts` labels Android as Play Billing but executes Razorpay; iOS reads an uninstalled `global.RNIap`; no client receipt-verification flow is connected | Android now fails before creating an order unless Razorpay is explicitly selected. Store billing remains unimplemented. This guard does not make checkout launch-ready. |
| P0 | `/subscriptions/store-notification` expects custom JSON and `X-Store-Webhook-Token`, rather than directly verifying Apple signed notifications or Google RTDN | Implement a verified provider adapter, purchase/account binding, authoritative entitlements, restore, acknowledgement/finish, refunds and renewal reconciliation. Never send this webhook secret to a client. |
| P0 | Android Gradle settings omit `useExpoModules()`, and application/activity omit Expo lifecycle wrappers | Added module autolinking, Expo bundling and lifecycle integration while preserving native security registration. Native compile and installed-device startup still need verification. |
| P0 | `targetSdkVersion 35`; PR #1 upgrades JS dependencies without upgrading the checked-in native project | Migrate Expo/RN and generated native projects together, preserve security modules with plugins, target API 36, and test current native binary compatibility. Do not merely change the target number. |
| P0 | Android release signing silently falls back to the debug key; iOS CI builds with signing disabled | Removed debug fallback. Unsigned Android compilation requires an explicit diagnostic flag and is labelled accordingly. Configure actual distribution credentials and produce store artifacts. |
| P0 | npm audit: 41 affected dependency entries (1 critical, 11 high, 28 moderate, 1 low). Python audit: 43 advisory instances across six packages | Upgrade and re-audit a supported dependency stack. Scanner findings include transitive/build dependencies and are not proof that every advisory is reachable. The forced `tar ^6.2.1` override requires removal as part of a compatible Expo upgrade. |
| P1 | An environment typo avoids production-only validation and can select nonproduction branches | Unknown environment values now fail validation; documented dev/test/stage/prod aliases remain supported. |
| P1 | Metrics label every raw URL and arbitrary HTTP method, creating unbounded process-memory growth and recording identifiers | Use matched route templates, one unmatched label and a bounded method set; regression tests cover arbitrary URLs and profile IDs. |
| P1 | iOS Podfile injection can split `use_native_modules!(config_command)` | Added target-scoped, idempotent Podfile modification. Current SDK 51 iOS prebuild succeeds. |
| P1 | Android notification channel created after permissions; iOS can register a raw APNs token with an FCM-only transport | Channel now precedes permission; Expo project ID is passed; iOS no longer takes the incompatible raw-token fallback. Real push credentials and delivery remain unverified. |
| P1 | REST overrides can point to staging while chat/location use production defaults | Centralized endpoints; WebSocket defaults derive from REST. Production config rejects missing/insecure/mixed endpoints and known mock flags. |
| P1 | Unexpected boot-security exception allows entry; font-load errors leave splash visible | Unexpected security failure blocks entry; font errors no longer prevent boot completion. Test recovery and native behavior on devices. |
| P1 | Deployment checks only process liveness, not database/Redis connectivity | Deployment and rollback verification now use readiness with request timeouts; production deployments are serialized and reference the production environment. Configure that environment's protections separately. |
| P1 | Tab bar uses a fixed bottom inset; white text on pastel CTA and orange text on white have poor contrast | Tab spacing follows safe-area insets. Primary CTA uses dark text; text-only and selected-tab accents use darker saffron. |

Additional release reviews: verify actual TLS pins and backup-key rotation (the repository hard-codes pins); prove origin lockdown and database privilege/RLS behavior; confirm media retention and retry durability; assess full account erasure separately from financial records; verify access to media cached before blocking or deletion. These remain unverified, not confirmed exploits.

## PR #1: SDK 57 upgrade assessment

The PR was checked out separately; its dependency installation completed. Default type-check fails with TS5101 (`baseUrl` deprecation). Continuing the diagnostic with `--ignoreDeprecations 6.0` reveals ten further diagnostics, including duplicate `GoogleSignin`, missing `Audio` namespace, `NodeJS.Timeout`, and `global` declarations. The duplicate sign-in declaration is substantive, not merely a compiler warning.

Its API wrappers return demo success on **any** caught failure in `__DEV__`, including wrong OTP and authorization failures. Release builds do not automatically take these branches, but development can conceal real integration defects. Move demo behavior behind an explicit, isolated demo client; real staging authentication must surface failures. No demo users or fabricated profiles should enter production discovery.

Keep the upgrade work, repair it, and generate native projects against the selected SDK with reproducible security plugins. Do not merge the PR as a ready-to-ship build.

## Specification decisions to settle

| Topic | Repository conflict | Proposed launch decision |
| --- | --- | --- |
| Identity | Matrimonial, dating, friends, and many experimental mechanics coexist | Lead with intentional adult Jain relationships; state supported intentions clearly |
| Visual system | Warm light design tokens versus forced dark native appearance | Warm light interface, saffron and pink accents, dark readable text; dark mode later as a complete system |
| Geography | DEVPLAN says Bangalore; other flows support Mumbai MMR, Pune and Bengaluru | Begin with the city where the team can recruit and moderate a dense compatible cohort; waitlist other cities |
| Likes | DEVPLAN describes blurred free likes; SUBSCRIPTION_SPEC promises transparent inbound likes; code has premium masking | Decide one entitlement matrix and synchronize server payloads, UI and marketing before charging |
| Paid offering | Four Jainune+ durations, legacy gold tiers, arcade microtransactions | Start with the smallest complete paid offering after store billing works; hide incomplete paid features only as an explicit product change |
| Roadmap | Large feature list includes maps, circles, voice, bounties and random matching | Ship the core discovery-to-conversation loop first; phase advanced mechanics behind tested feature controls |

These are proposals, not silent changes to pricing, geography or entitlements. The implemented Jainune+ catalogue is ₹499/30 days, ₹999/90 days, ₹1,699/180 days and ₹2,799/365 days; confirm whether store products are renewable subscriptions or fixed-duration passes. Store localized prices and billing periods must drive checkout presentation.

## Android and iOS layout plan

See [ANDROID_IOS_LAYOUT.md](ANDROID_IOS_LAYOUT.md) and [layout overview](mobile-layout-overview.svg). The illustration is a proposed layout, not a screenshot of a running app.

## Build and acceptance evidence

| Check | Evidence / limitation |
| --- | --- |
| Baseline backend | 351 tests passed, 73.30% coverage after excluding workspace proxy variables from mocked tests |
| Updated backend | See validation record below; includes new environment and metrics regressions |
| Mobile | Baseline and updated TypeScript pass; seven added behavioral regression tests pass |
| Bundles | Both Android and iOS production JS/Hermes exports tested; these are not AAB/IPA distribution files |
| iOS generation | Updated Expo prebuild with `--platform ios --no-install` succeeds; no CocoaPods/Xcode/signing test in this Linux workspace |
| Endpoint checker | Reports 64 client call patterns against 109 routes; this is a static path check, not an API contract or integration guarantee |
| Lint | Passes with existing warnings; a successful exit does not mean zero warnings |
| Existing GitHub main CI | CI and Mobile Build runs at baseline were successful; audits were advisory, Android used debug fallback, and iOS was unsigned |
| Not exercised | Real PostgreSQL/Redis migrations, S3 moderation, OTP providers, native purchases, installed phones, cloud deployment, production load, App Store/Play review |

Tests labelled “integration” in the repository predominantly use the shared mocked app/database/Redis fixtures. Their success does not prove real SQL migrations or provider integration. Four initial push-test failures came from the workspace HTTP proxy configuration, and passed after the proxy variables were omitted for the mocked suite; application networking was not weakened.

## Ordered release work

1. **Supported mobile baseline.** Repair the SDK upgrade, reconcile native Android and generated iOS, remove incompatible overrides and deprecated audio/file-system APIs, pass type-check, native compilation and package audits. Test API 36 edge-to-edge and binary page-size requirements with the actual native modules.
2. **Complete identity and billing.** Configure Google OAuth for Android signing and iOS URL schemes; enable Apple Sign In, revoke Apple credentials on deletion as needed. Implement platform-native purchase/restore and server verification. Exercise interrupted, duplicate, pending, refunded, renewed and cross-account receipts.
3. **Production backend and safety.** Provision isolated staging/production databases and Redis; run all migrations on a fresh DB and an upgrade copy. Configure S3/IAM, moderation, OTP delivery, push, origin protection and secrets. Test authorization with at least two accounts plus blocked/deleted users. Establish a staffed moderation queue and escalation procedure.
4. **Release artifacts.** Android: sign an AAB with the upload key and enroll Play App Signing; anti-tamper fingerprint must match the Play **app-signing** certificate for store installs. iOS: archive with the distribution identity/provisioning profile and export an App Store IPA. Record commit, lockfile, environment and artifact checksum. Never distribute CI's unsigned diagnostic bundle.
5. **Device beta.** Run the matrix in the layout plan through Play internal/closed testing and TestFlight. Review crash-free sessions, onboarding completion, eligible feed density, conversation starts, abuse reports and deletion completion. No fabricated users to mask a thin feed.
6. **Store submission and launch.** Prepare accurate screenshots, app access for reviewers, privacy/data disclosures, support and deletion URLs, age restrictions, and product descriptions. Verify operational ownership and perform an explicit go/no-go before public submission or deployment.

## Store and safety requirements checked

As of this review, new Android app submissions must target API 36, subject to any applicable approved extension. [Google Play target API requirements](https://support.google.com/googleplay/android-developer/answer/11926878?hl=en).

The app needs content filtering, reporting, blocking, published support information and in-app deletion. Store billing and dating-app differentiation also need review. [Apple App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/).

Social/dating apps must meet Google's Child Safety Standards, including a designated contact in Play Console. [Google child safety requirements](https://support.google.com/googleplay/android-developer/answer/14747720?hl=en). Dating/matchmaking apps must use Play's minor-access restriction. [Google dating age restrictions](https://support.google.com/googleplay/android-developer/answer/16838200?hl=en).

The current legal pages claim perceptual-hash screening, automatic authority reporting, a 24/7 under-one-hour response, and a 48-hour deletion timeline. No evidence in this review establishes all those capabilities; deletion code uses different retention behavior. Correct published claims to the implemented and staffed process before release. Have the responsible operator and counsel settle applicable privacy, retention and reporting obligations; do not treat earlier MD assertions as verified legal advice.

## Business launch controls

Measure compatible active profiles per user's actual preference set, not total signups. Recruit an opted-in local cohort, watch empty-feed incidence and time to a reciprocal conversation, and expand geography only when supply and moderation capacity support it. Keep report/block/account deletion available regardless of subscription.

Track signup → verified adult profile → first eligible profile → contextual like → reciprocal match → two-way conversation. Track abuse response and data erasure separately from growth. Set launch thresholds from the beta; prior claims such as 96% gross margin or guaranteed match rates are hypotheses. Net contribution must include store/payment charges, taxes, refunds, OTP, media, infrastructure, acquisition and moderation costs.

## Access and owner handoff

The connected account can read upstream and write the existing `Dakshbumb/jainune` fork. Review changes through a separate draft PR. Public deployment, merges and store submission have not occurred.

Needed to complete the release: team Expo project (if using Expo push/EAS), Apple Developer and App Store Connect access, Play Console access, distribution signing identities, product identifiers/verification credentials, production cloud access, actual DNS/TLS configuration, and the launch-city/entitlement decisions above. Configure secret values in the relevant account or secret manager; do not paste private signing keys into chat or commit them.

## Validation record

The final test counts and limitations are recorded in the draft PR and `VALIDATION.md`.
