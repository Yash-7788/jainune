# Jainune Android and iOS layout specification

Proposed launch layout, 14 September 2026. Existing screen names and four-tab navigation are preserved. This is the implementation plan; only the safe-area, shared CTA contrast and theme corrections described in the launch report are implemented in this branch.

## Shared design system

Warm canvas `#FFFCFA`, white cards, primary text `#1C1C1E`, secondary text `#6C6C70`, saffron `#FF9C4A` and pink `#FFAAC4` accents. Use dark text on pastel fills and `#9A4700` for saffron text on light surfaces. Reserve red for destructive/error actions and use labels in addition to color.

Outfit for headings, Inter for reading. Use the existing 32/24/17/15/13 type scale with system font scaling; avoid fixed-height text containers. Screen gutters 20 logical units, section spacing 24, card padding 16, input and button minimum height 52. Icon controls need meaningful accessible names. Photos use consistent 3:4 crops; never overlay critical controls on faces. Load images progressively and reserve their dimensions to avoid jumps.

## Platform adaptation

| Element | iOS | Android |
| --- | --- | --- |
| Top region | Respect notch/Dynamic Island and status bar insets | Respect status bar and display cutouts; validate API 36 edge-to-edge |
| Navigation | Native stack back gesture, meaningful back labels | Hardware/predictive back closes sheet, then pops stack; preserve entered data |
| Bottom tabs | 56-unit content region plus actual home-indicator inset | 56-unit content region plus actual gesture/three-button-nav inset |
| Tap areas | At least 44 × 44 pt | At least 48 × 48 dp |
| Forms | Keyboard-aware scroll with visible next action; OTP autofill | Keyboard resize/insets; numeric OTP keyboard and supported autofill |
| Pickers | Native date/photo/permission conventions | System date/photo picker; request only necessary permissions |
| Feedback | VoiceOver labels, Dynamic Type, reduce motion, restrained haptics | TalkBack labels, font/display scaling, reduce animations, restrained haptics |
| Purchases | StoreKit sheet and actual restore flow | Play Billing sheet; alternative billing only under the applicable implemented program |
| Sheets | Reachable close/back, large text can scroll | Back dismisses; content stays above system navigation |

## Screen layout and behavior

| Screen | Top → bottom layout | Required states |
| --- | --- | --- |
| Welcome | Small wordmark; one clear relationship value proposition; brand illustration; sign-in actions; 18+ and policy links | Offline, unavailable provider, accessibility text size |
| Sign-in/OTP | Back; title; labelled phone/email field; inline validation; continue; resend timer after OTP request | Invalid OTP, expired code, rate limit, cancelled sign-in, provider outage; never silently simulate success |
| Onboarding | Back + progress; one question; concise reason; inputs; sticky continue above keyboard | Saved progress, upload processing/rejection, permission denied, retry, unsupported city waitlist |
| Discover | Title + preferences control; one scrollable profile; first name/age/city; photo; values row; prompts; contextual like action; pass; tabs | Loading skeleton, no eligible profiles, offline/retry, quota reached, blocked profile removed |
| Like sheet | Referenced photo/prompt; optional or required opener as product specifies; character counter; send; close | Keyboard, sending, quota, failure without losing draft |
| Likes | Title/count; readable incoming-like cards with opener; review/connect or pass; tabs | Empty, loading, actionable error; final free/premium visibility follows the agreed entitlement matrix |
| Match | Two profile thumbnails; short acknowledgement; genuine prompt-based opener; message now / later | Reduce motion; return to discovery without forced urgency |
| Chats list | New matches; conversations with last activity and unread state; tabs | Empty, failed refresh, unread updates, blocked/unmatched entry removed |
| Chat thread | Back; name; menu with report/block/unmatch; message history; send state; composer above keyboard | Sending/sent/failed, retry without duplicate message, offline, reconnect, expired media, blocked/unmatched notice |
| Own profile | Preview card; completion/edit; cultural details; settings; tabs | Edit/save errors, photo processing, pause confirmation |
| Settings/safety | Grouped discovery, notifications, account/privacy and support sections | Paused profile, block list, export/deletion confirmation, logout, accessible support contact |
| Report/block | Simple reason options; optional detail; explain effect; submit; confirmation | Urgent safety route, offline retry, successful block immediate in UI and enforced server-side |
| Membership | Concrete benefits; store localized total price and period; renewal disclosure; purchase; restore/manage; policies | Store unavailable, cancelled, pending, verified entitlement, refund, expired; never show success merely because a checkout sheet completed |

The existing long onboarding flow is preserved until backend requirements are reconciled. A later redesign should progressively collect optional career/voice details, save each completed step and clearly distinguish required safety information from optional profile enrichment.

## Platform device acceptance matrix

| Test | Acceptance |
| --- | --- |
| Narrow phone / large text | At 320–360 logical width and large accessibility text, no clipped labels, inaccessible next action or horizontal overflow |
| Tall iPhone and Android cutout | All controls outside status/home/system-nav regions; smooth scrolling under safe-area chrome |
| Android back and iOS swipe back | Dismiss sheets predictably; do not lose unsent drafts or onboarding progress unexpectedly |
| Keyboard open | Composer and form CTA remain visible; tapping send does not require dismissing keyboard first |
| Assistive technology | Meaningful focus order and labels; loading/error changes announced; selections not indicated only by color |
| Slow network and restart | Repeatable loading/error/empty states; persist drafts where promised; session refresh and upload retry recover safely |
| Two real test accounts | Like → mutual match → chat → block/unmatch → attempts from old session; server enforces the resulting state |
| Native providers | OTP, Google/Apple sign-in, camera/photo picker, microphone, push, purchase/restore and cancellation exercised on release-signed builds |
| Privacy | Background previews and capture behavior verified for sensitive screens; no claim that screenshot prevention is unbreakable |
| Deletion | Profile disappears, sessions revoked, media and retained records follow the disclosed process, and old links cannot expose private content |

Use actual device screenshots for store submission after this matrix passes. The accompanying vector layout is for design review only.
