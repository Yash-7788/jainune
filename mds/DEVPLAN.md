# Jainune — Development Plan

> **Hinge Flow · Saffron + Pink**  
> React Native · FastAPI · Supabase · 10-Week Build · Bangalore Launch

---

## 1. Design System

### Colour Palette

| Name | Hex | Usage |
| :--- | :--- | :--- |
| **Saffron — Primary CTA** | `#FF9C4A` | Buttons, active states, primary accents |
| **Saffron Mid — Hover** | `#FFB366` | Hover states, secondary actions |
| **Saffron Light — BG Tint** | `#FFF4EA` | Card backgrounds, input tints |
| **Baby Pink — Accent** | `#FFAAC4` | Likes, hearts, match moments, gradient end |
| **Pink Mid — Active Pink** | `#FF8FAB` | Pressed states, active like icons |
| **Pink Light — BG Tint** | `#FFF0F5` | Like screen backgrounds, match UI |
| **Dark — Primary Text** | `#1C1C1E` | All main body text, headings |
| **Mid — Secondary Text** | `#6C6C70` | Subtitles, hints, labels |
| **Background** | `#FFFCFA` | App-wide background |
| **Border / Divider** | `#EDE8E3` | Cards, separators, inputs |

#### Gradients
- **CTA Buttons + Match Screen**: `linear-gradient(135deg, #FF9C4A 0%, #FFAAC4 100%)`
- **Gradient Button**: `linear-gradient(135deg, #FF9C4A, #FF8FAB)`

---

### Typography Scale

| Role | Size | Weight | Used For |
| :--- | :--- | :--- | :--- |
| **H1 Display** | `32px` | 800 | Welcome screens, match moment |
| **H2 Screen Title** | `24px` | 700 | Screen headers, section names |
| **H3 Card Title** | `17px` | 600 | Profile name, card prompts |
| **Body Regular** | `15px` | 400 | Prompt responses, chat messages |
| **Body Small** | `13px` | 400 | Captions, labels, timestamps |
| **Caption / Tag** | `11px` | 700 | Tags, badges, upper labels |
| **CTA Button** | `16px` | 700 | All primary actions |

---

### Spacing System

| Value | Name | Usage |
| :--- | :--- | :--- |
| `4px` | xs | Icon gaps, tight spacing |
| `8px` | sm | Within components |
| `12px` | md | Card inner padding |
| `16px` | base | Standard screen padding |
| `20px` | lg | Section gaps |
| `24px` | xl | Between major sections |
| `32px` | 2xl | Screen-level breathing room |

---

### Core Component Library

- `PrimaryButton`: Gradient bg (saffron→pink), 52px height, 12px radius, white text 700
- `GhostButton`: Border saffron, transparent bg, saffron text — secondary actions
- `HeartButton`: Circle 56px, pink gradient fill on tap, pulse animation on like
- `PassButton`: Circle 48px, light border, grey X icon, no fill
- `ProfileCard`: Full screen height, photo fill, overlay gradient bottom-to-top for text
- `PromptCard`: Saffron-light bg, rounded 16px, prompt label + response text
- `TextInput`: Bottom-border only style (Hinge), 16px text, saffron focus indicator
- `OTPInput`: 6 individual digit boxes, auto-advance, saffron border on filled
- `PhotoSlot`: 3:4 ratio, dashed border empty, filled = photo + X delete overlay
- `ProgressBar`: Top of onboarding screens, saffron fill, pink track, animated
- `MatchBurst`: Full screen animation — saffron particles burst, pink glow ring
- `ChatBubble`: Sent: saffron-light. Received: white/border. 16px radius.

---

### Hinge vs Jainune — Visual Differences

| Dimension | Hinge | Jainune |
| :--- | :--- | :--- |
| **Primary Theme** | Deep maroon/aubergine primary | Light saffron + baby pink |
| **Vibe** | Dark, rich, sophisticated | Warm, airy, modern Indian |
| **Typography** | Serif display type | Rounded sans-serif |
| **Header Bars** | Dark header bars | White + warm bg throughout |
| **Accents** | Rose = premium | Pink hearts, saffron CTAs |

---

## 2. App Flow

### Onboarding Flow (Hinge Order, Jainune Fields)

> **Progress bar:** Runs across top of every onboarding screen. Saffron fill, pink track. Steps 5–22 count toward it. Steps 1–4 (welcome) don't count. Back button always visible — never trap the user.

| # | Screen | Dev Notes |
| :--- | :--- | :--- |
| 1 | Splash | Jainune wordmark fade in on saffron-pink gradient. 2s. Auto-advance. |
| 2 | Welcome Slide 1 | 'Finally. An app that gets it.' — Dark BG, saffron type. |
| 3 | Welcome Slide 2 | 'Real people. Shared world.' — Real photo, no stock. |
| 4 | Welcome Slide 3 | 'Your community. Your terms.' — CTA: Get Started. |
| 5 | Phone Number | Country code (+91 default). Big numeric input. Continue CTA at bottom. |
| 6 | OTP Verify | 6-box OTP input. Auto-advance per digit. Resend after 30s. |
| 7 | First Name | Single text field. 'What do we call you?' Hinge-style bottom border input. |
| 8 | Date of Birth | Wheel/drum-roll picker. Show age on profile — never the DOB. |
| 9 | Gender | Man / Woman / Nonbinary / More options. No hierarchy between options. |
| 10 | Show Me | Men / Women / Everyone. Sets discovery preference. |
| 11 | Looking For | Life partner / Long-term / Figuring out / Short-term / Friends. Multi-select. |
| 12 | City | Bangalore default. Searchable. Auto-detect option. |
| 13 | Photos | 3 × 2 photo grid. Tap slot to pick. Drag to reorder. 3 min, 6 max. Face detection runs silently. |
| 14 | Prompts | Scrollable list of 40+ prompts. Tap to select. Write response (150 char). Must pick exactly 3. |
| 15 | Job Title | Text input, optional. Autocomplete from common roles. |
| 16 | Company | Text input, optional. |
| 17 | School / University | Text input with autocomplete. Degree field below. |
| 18 | Height | Optional. Slider or picker. cm / ft both shown. |
| 19 | Kids | Want someday / Open to it / Don't want / Have kids. |
| 20 | Drinking | Never / Occasionally / Socially. |
| 21 | Notifications Prompt | Native iOS/Android permission dialog. Show value prop first. |
| 22 | Location Prompt | Native dialog. Required for feed. Show why before asking. |

---

### Core App Screens (Hinge UX, Jainune Skin)

- **🏠 Feed (Home)**: Vertical profile stack. See one profile at a time. Scroll through their photos + prompts within the profile.
- **📸 Photo Section**: Full-bleed photo. Tap heart → like with optional comment sheet slides up. Dots show photo count.
- **💬 Prompt Section**: Saffron-light card with prompt label + response. Tap heart → MUST leave a comment (forces real opener).
- **📋 Basics Strip**: Age · Height · City · Job — compact inline row between photos. Tappable for full detail.
- **✕ Pass Action**: X button bottom-left. Instant. No animation drama. Profile is gone.
- **❤️ Like Comment Sheet**: Bottom sheet slides up. Shows the photo or prompt they liked. Text input + Send. Pink send button.
- **💌 Likes Received**: Grid of profiles who liked you. Free: blurred with count overlay. Premium: full visibility + filter bar.
- **🎉 Match Screen**: Full screen. Saffron burst animation. Both photos float up. 'It's a Jainune!' in gradient text. Suggested opener from their prompt.
- **💬 Chat List**: New matches row at top (horizontal scroll). Active chats below in list. Last message preview. 'Active today' indicator.
- **📩 Chat Thread**: Saffron bubbles sent, white bubbles received. Voice note: hold mic button. Weekly Question banner at top.
- **👤 Profile (Own)**: Preview of how you appear to others. Edit button top right. Settings icon. Pause profile toggle.
- **✏️ Edit Profile**: Same step-by-step flow as onboarding, but individual sections editable. Photo reorder.
- **⚙️ Settings**: Discovery prefs / Notifications / Paryushan Mode / Pause / Block list / Premium / Account / Logout.
- **🙏 Paryushan Mode**: Toggle screen. When on: profile shows soft banner. Matches preserved. Chats frozen. Auto-off after Samvatsari.
- **⭐ Jainune+ Paywall**: Feature comparison grid. 3 plan options (monthly/quarterly/annual). Razorpay CTA. 7-day trial for verified users.
- **🚨 Report / Block**: Category select. Optional description. Instant block. Confirmation screen.

---

### Navigation Structure

#### Bottom Tab Bar (4 tabs, Hinge-identical)
1. **🏠 Home**
2. **❤️ Likes**
3. **💬 Chats**
4. **👤 Profile**

*No 5th tab. Settings lives inside Profile tab. Premium lives inside Profile tab. Keeps the nav dead simple.*

---

## 3. Sprints (10-Week Development Roadmap)

> **Parallel tracks:** Instagram hype runs during Weeks 1–4 while core product is being built. App needs to be in TestFlight by Week 9 so the team can dog-food it before launch. Week 10 = App Store submission, not new features.

### Week 1: Foundation
- **Goal**: Everything set up. Team can push code. Design tokens live.
- **Tasks**:
  - [ ] Monorepo setup — React Native (Expo) + FastAPI
  - [ ] Supabase project init — schema v1, auth, storage buckets
  - [ ] Design system: colour tokens, typography, base components in React Native
  - [ ] React Navigation skeleton — all screen stubs registered
  - [ ] GitHub Actions CI/CD — lint + test on PR, auto-deploy backend
  - [ ] ENV management — dev / staging / prod configs
  - [ ] Figma file set up with component library (hand-off ready)
- **Owners**: All 5 team members — foundation sprint, everyone contributes

### Week 2: Auth + Phone OTP
- **Goal**: User can create an account and log back in.
- **Tasks**:
  - [ ] Phone number input screen (country code, validation)
  - [ ] MSG91 OTP integration — send + verify
  - [ ] OTP input screen (6-box, auto-advance, resend timer)
  - [ ] Supabase session management + token refresh
  - [ ] Deep link handling for magic link fallback
  - [ ] Auth guard — redirect to login if no session
  - [ ] Basic error states (wrong OTP, network fail)
- **Owners**: Backend: 1 dev (FastAPI auth routes) · Frontend: 1 dev (screens)

### Week 3: Onboarding Part 1 (Screens 7–13)
- **Goal**: User can complete first half of profile setup.
- **Tasks**:
  - [ ] Progress bar component (animated, step-aware)
  - [ ] Name, DOB picker, Gender, Show Me screens
  - [ ] Looking For multi-select screen
  - [ ] City selector (searchable, Bangalore default)
  - [ ] Photo upload grid (3×2, tap to pick from camera roll)
  - [ ] ML Kit face detection on photo upload
  - [ ] Drag-to-reorder photos (react-native-draggable-flatlist)
  - [ ] Photo storage to Supabase Storage + CDN URL
- **Owners**: 2 frontend devs on screens · 1 backend dev on photo upload API

### Week 4: Onboarding Part 2 (Screens 14–22)
- **Goal**: Full profile setup complete. User profile exists in DB.
- **Tasks**:
  - [ ] Prompt bank screen (40+ prompts, select 3)
  - [ ] Prompt response text input (150 char, character counter)
  - [ ] Job, Company, University inputs (with autocomplete)
  - [ ] Height picker, Kids, Drinking screens
  - [ ] Notification permission request flow (iOS + Android)
  - [ ] Location permission + geocoding
  - [ ] Profile completeness score (internal, not shown to user)
  - [ ] Onboarding completion → write full profile to Supabase
- **Owners**: 2 frontend devs · 1 backend dev on profile schema

### Week 5: Discovery Feed
- **Goal**: Core product loop works. User can see profiles, like, and pass.
- **Tasks**:
  - [ ] Profile card — full vertical scroll (photos + prompts + basics)
  - [ ] Photo viewer inside card (horizontal swipe, dot indicators)
  - [ ] Prompt card component (saffron-light bg, prompt label + response)
  - [ ] Heart button on photo → like with optional comment bottom sheet
  - [ ] Heart button on prompt → like with REQUIRED comment input
  - [ ] Pass button (X) — remove from feed
  - [ ] Feed pagination — cursor-based, load next batch
  - [ ] Feed algorithm v1: location → age preference → activity score
  - [ ] Empty feed state (no more profiles in area)
- **Owners**: 2 frontend devs (card + interactions) · 1 backend dev (feed API + algorithm)

### Week 6: Likes + Matching System
- **Goal**: Mutual likes create matches. Match screen fires. Likes grid works.
- **Tasks**:
  - [ ] Likes received screen — grid layout
  - [ ] Blur overlay on free tier (CSS blur on photo)
  - [ ] Match detection logic (when both users have liked each other)
  - [ ] Match celebration screen — particle burst animation (react-native-lottie)
  - [ ] Suggested conversation starter from their prompt on match screen
  - [ ] Push notification for new match (FCM)
  - [ ] Push notification for new like received
  - [ ] Unmatch flow (from chat screen)
- **Owners**: 1 frontend dev (likes screen + match screen) · 1 backend dev (match logic + notifications)

### Week 7: Chat System
- **Goal**: Matched users can have real-time conversations.
- **Tasks**:
  - [ ] Chat list screen (new matches row + active chats list)
  - [ ] Chat thread — real-time messages via Supabase Realtime
  - [ ] Chat bubble components (sent saffron-light, received white)
  - [ ] Voice note — hold to record, release to send (expo-av)
  - [ ] Voice note player in chat thread
  - [ ] Weekly icebreaker question banner (updates every Monday)
  - [ ] 7-day nudge notification (if matched chat has no message)
  - [ ] 'Active today' indicator in chat list
  - [ ] Read receipts (store, but only show for Premium)
- **Owners**: 2 frontend devs (chat UI) · 1 backend dev (Supabase Realtime + voice storage)

### Week 8: Premium + Payments
- **Goal**: Jainune+ subscription live. Razorpay integrated. Premium gates work.
- **Tasks**:
  - [ ] Jainune+ paywall screen (feature comparison, 3 plan cards)
  - [ ] Razorpay SDK integration (React Native)
  - [ ] Subscription create-order → verify-payment API
  - [ ] Premium status stored in DB + checked on every gated feature
  - [ ] Blur removal on likes screen for Premium users
  - [ ] Unlimited likes gate (check on each like action)
  - [ ] Profile boost — à la carte Razorpay payment
  - [ ] Boost active indicator (top of feed, 30min timer)
  - [ ] 7-day free trial trigger for photo-verified users
- **Owners**: 1 frontend dev (paywall + boost UI) · 1 backend dev (Razorpay + subscription logic)

### Week 9: Settings, Polish + Paryushan Mode
- **Goal**: All settings work. Paryushan Mode live. App feels finished.
- **Tasks**:
  - [ ] Settings screen (all sections)
  - [ ] Paryushan Mode toggle screen + profile banner
  - [ ] Pause profile toggle (removes from discovery)
  - [ ] Block / Report flow (with categories)
  - [ ] Edit profile — all sections editable post-onboarding
  - [ ] Photo verification flow (face match check)
  - [ ] Discovery preferences editing (age range, distance)
  - [ ] Notification preferences screen
  - [ ] Performance audit — image caching, lazy loading, scroll perf
  - [ ] Empty states for all screens (no matches, no chats, no likes)
  - [ ] Accessibility pass — font scaling, contrast ratios
- **Owners**: All team — polish sprint. Split by feature area.

### Week 10: Beta, QA + App Store
- **Goal**: App submitted to App Store. Ship it.
- **Tasks**:
  - [ ] Internal beta via TestFlight (iOS) + Firebase App Distribution (Android)
  - [ ] Bug bash — all team uses app for 3 days straight
  - [ ] Critical bug fixes only (no new features)
  - [ ] App Store listing: screenshots, description, keywords
  - [ ] App icon finalised (saffron-pink gradient, Jainune mark)
  - [ ] Privacy policy + Terms of service pages (required for App Store)
  - [ ] App Store Connect submission
  - [ ] Play Store submission (Android)
  - [ ] Monitoring setup — Sentry for crash reporting, PostHog for events
  - [ ] Backend load test before launch day
- **Owners**: 1 dev: App Store submission · 1 dev: bug fixes · 1 dev: monitoring · Others: QA

---

## 4. Screens Build Reference

### Complexity Legend
- 🟢 **Easy** (1–2 days)
- 🟡 **Medium** (3–4 days)
- 🔴 **Hard** (5+ days)

### All Screens (29 Screens)

| Screen | Week | Difficulty | Dev Notes |
| :--- | :--- | :--- | :--- |
| Splash | W1 | 🟢 Easy | Lottie animation or simple fade. Saffron-pink gradient BG. |
| Welcome (3 slides) | W1 | 🟢 Easy | Static slides + swipe. Dots indicator. Skip option. |
| Phone Input | W2 | 🟢 Easy | react-native-phone-input. Country code auto +91. Validation. |
| OTP Verify | W2 | 🟡 Medium | 6 individual TextInputs, focus auto-advance, Resend countdown. |
| First Name | W3 | 🟢 Easy | Single input, bottom-border style. Continue disables if empty. |
| Date of Birth | W3 | 🟡 Medium | Drum-roll/wheel picker. Min age 18 enforced. |
| Gender | W3 | 🟢 Easy | 3 option cards + 'More options' expander. |
| Show Me | W3 | 🟢 Easy | 3 option pills. Saves to preference. |
| Looking For | W3 | 🟢 Easy | Multi-select chips. Min 1 required. |
| City | W3 | 🟡 Medium | Searchable FlatList. Geo-detect button. Bangalore highlighted. |
| Photos Grid | W3 | 🔴 Hard | 3×2 grid. ImagePicker. Drag reorder. ML Kit face check. Upload to Supabase. |
| Prompt Select | W4 | 🟡 Medium | Categorized SectionList. Tap to open response input. Must pick 3. |
| Prompt Response | W4 | 🟢 Easy | TextInput 150 char. Counter. Keyboard aware. |
| Job / School | W4 | 🟢 Easy | Text inputs with basic autocomplete. |
| Details (Height etc.) | W4 | 🟢 Easy | Option cards for each question. Skip allowed on most. |
| Permission Screens | W4 | 🟢 Easy | Custom pre-ask screen → native dialog. Deny gracefully. |
| Feed (Home) | W5 | 🔴 Hard | Core of the app. ScrollView per profile. Infinite scroll. Performance critical. |
| Like Comment Sheet | W5 | 🟡 Medium | Bottom sheet. Shows what they liked. TextInput + Send. |
| Likes Received | W6 | 🟡 Medium | FlatList grid. Blur with FastImage + blur overlay. Filter bar for Premium. |
| Match Screen | W6 | 🟡 Medium | Lottie burst animation. Both photos. Gradient text. Suggested opener. |
| Chat List | W7 | 🟡 Medium | New matches horizontal scroll. Chats FlatList. Last message + timestamp. |
| Chat Thread | W7 | 🔴 Hard | Supabase Realtime. Voice record/play. Inverted FlatList. Keyboard avoid. |
| Profile (Own) | W9 | 🟡 Medium | Mirror of how others see you. Edit + Settings entry points. |
| Edit Profile | W9 | 🟡 Medium | Same components as onboarding, pre-filled. Photo reorder. |
| Settings | W9 | 🟡 Medium | Grouped sections. Toggle for Paryushan Mode + Pause. Nav to sub-screens. |
| Paryushan Mode | W9 | 🟢 Easy | Single toggle. Confirm dialog. Profile banner change. |
| Jainune+ Paywall | W8 | 🟡 Medium | Feature grid. 3 plan cards. Razorpay sheet. |
| Report / Block | W9 | 🟢 Easy | Category select. Optional note. Instant block on confirm. |
| Profile Boost | W8 | 🟢 Easy | Confirm + Razorpay. Active timer shown in feed header. |

*Total screens: 29 · Critical path: Feed → Like → Match → Chat*

---

## 5. Database Schema — Supabase (PostgreSQL)

> **Supabase RLS Policy (Row Level Security):** Every table has RLS enabled. Users can only read/write their own rows. The feed API runs as a service role (bypasses RLS) to query other users' profiles. Messages are readable by both users in a match (policy checks match membership).

### `users`
*Core user identity and profile settings.*

| Column | Type | Notes |
| :--- | :--- | :--- |
| `id` | `uuid` | PK, default gen_random_uuid() |
| `phone` | `text` | UNIQUE, NOT NULL — primary identifier |
| `name` | `text` | First name only |
| `dob` | `date` | Date of birth — never exposed via API |
| `gender` | `text` | man / woman / nonbinary / other |
| `show_me` | `text` | men / women / everyone |
| `city` | `text` | Current city |
| `job_title` | `text` | Optional |
| `company` | `text` | Optional |
| `school` | `text` | Optional |
| `height_cm` | `int` | Optional, in centimetres |
| `kids` | `text` | want / open / dont_want / have |
| `drinking` | `text` | never / occasionally / socially |
| `relationship_type` | `text[]` | Array of intents |
| `is_verified` | `bool` | Photo verified |
| `is_premium` | `bool` | Computed from subscriptions table |
| `premium_expires_at` | `timestamptz` | Null if free |
| `paryushan_mode` | `bool` | Default false |
| `is_paused` | `bool` | Default false — hides from feed |
| `last_active` | `timestamptz` | Updated on every app open |
| `created_at` | `timestamptz` | Default now() |

---

### `photos`
*User photos. Max 6 per user. order determines display sequence.*

| Column | Type | Notes |
| :--- | :--- | :--- |
| `id` | `uuid` | PK |
| `user_id` | `uuid` | FK → users.id, CASCADE delete |
| `url` | `text` | Supabase Storage public URL |
| `order` | `int` | 0–5, determines card order |
| `is_primary` | `bool` | First photo shown in feed |
| `created_at` | `timestamptz` | |

---

### `prompts`
*Prompt bank. Seeded at launch, grows over time.*

| Column | Type | Notes |
| :--- | :--- | :--- |
| `id` | `uuid` | PK |
| `text` | `text` | The prompt question text |
| `category` | `text` | jain / general / fun / deep |
| `is_active` | `bool` | False = retired from bank |

---

### `user_prompts`
*Which prompts a user has chosen and their responses.*

| Column | Type | Notes |
| :--- | :--- | :--- |
| `id` | `uuid` | PK |
| `user_id` | `uuid` | FK → users.id |
| `prompt_id` | `uuid` | FK → prompts.id |
| `response` | `text` | Max 150 chars |
| `order` | `int` | 0–2, determines display order on profile |

---

### `interactions`
*All swipe actions — likes and passes. Indexed heavily for feed algorithm.*

| Column | Type | Notes |
| :--- | :--- | :--- |
| `id` | `uuid` | PK |
| `swiper_id` | `uuid` | FK → users.id (who acted) |
| `swiped_id` | `uuid` | FK → users.id (who was acted on) |
| `type` | `text` | like / pass / superlike |
| `target_type` | `text` | photo / prompt (what they liked) |
| `target_id` | `uuid` | FK to photo or user_prompt id |
| `comment` | `text` | Null for passes. Required for prompt likes. |
| `created_at` | `timestamptz` | |

---

### `matches`
*Created when two users have mutually liked each other.*

| Column | Type | Notes |
| :--- | :--- | :--- |
| `id` | `uuid` | PK |
| `user1_id` | `uuid` | FK → users.id (lower uuid alphabetically) |
| `user2_id` | `uuid` | FK → users.id |
| `created_at` | `timestamptz` | |
| `is_active` | `bool` | False if either user unmatches |

---

### `messages`
*Chat messages within a match. Realtime via Supabase.*

| Column | Type | Notes |
| :--- | :--- | :--- |
| `id` | `uuid` | PK |
| `match_id` | `uuid` | FK → matches.id |
| `sender_id` | `uuid` | FK → users.id |
| `type` | `text` | text / voice / photo |
| `content` | `text` | Text content, or null for media |
| `media_url` | `text` | Voice/photo URL, or null for text |
| `is_read` | `bool` | Default false |
| `created_at` | `timestamptz` | |

---

### `subscriptions`
*Premium subscription records. One active row per user max.*

| Column | Type | Notes |
| :--- | :--- | :--- |
| `id` | `uuid` | PK |
| `user_id` | `uuid` | FK → users.id |
| `plan` | `text` | monthly / quarterly / annual |
| `started_at` | `timestamptz` | |
| `expires_at` | `timestamptz` | |
| `razorpay_order_id` | `text` | For verification |
| `razorpay_payment_id` | `text` | Captured on success |
| `status` | `text` | active / expired / cancelled |

---

### `boosts`
*Active profile boosts. One active at a time per user.*

| Column | Type | Notes |
| :--- | :--- | :--- |
| `id` | `uuid` | PK |
| `user_id` | `uuid` | FK → users.id |
| `started_at` | `timestamptz` | |
| `expires_at` | `timestamptz` | started_at + 30 minutes |
| `razorpay_payment_id` | `text` | |

---

### `reports`
*User reports for safety. Reviewed by admin.*

| Column | Type | Notes |
| :--- | :--- | :--- |
| `id` | `uuid` | PK |
| `reporter_id` | `uuid` | FK → users.id |
| `reported_id` | `uuid` | FK → users.id |
| `reason` | `text` | fake / harassment / solicitation / other |
| `description` | `text` | Optional detail |
| `created_at` | `timestamptz` | |
| `status` | `text` | pending / reviewed / actioned |

---

## 6. FastAPI Endpoints Reference

> **Base URL & Auth:**  
> All endpoints: `https://api.jainune.app/v1`  
> Auth: Bearer token in `Authorization` header (Supabase JWT).  
> Rate limits: 100 req/min per user. Feed endpoint: 30 req/min.

### Auth
| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/auth/send-otp` | Send OTP to phone number via MSG91 |
| `POST` | `/auth/verify-otp` | Verify OTP, create user if new, return session |
| `POST` | `/auth/refresh` | Refresh access token |
| `POST` | `/auth/logout` | Invalidate session |

### Profile
| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/profile/me` | Get own full profile |
| `PUT` | `/profile/me` | Update profile fields |
| `GET` | `/profile/:id` | Get another user's public profile |
| `PUT` | `/profile/me/photos/reorder` | Reorder photo array |
| `DELETE` | `/profile/me/photos/:id` | Delete a photo |
| `POST` | `/profile/me/verify-photo` | Submit photo for face verification |
| `PUT` | `/profile/me/pause` | Toggle pause profile |
| `PUT` | `/profile/me/paryushan` | Toggle Paryushan Mode |

### Photos (Upload)
| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/photos/upload` | Get Supabase Storage signed upload URL (client uploads direct) |
| `POST` | `/photos/confirm` | Confirm upload, save URL to photos table |

### Feed (Discovery)
| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/feed` | Paginated feed. Cursor-based. Filters by prefs + location + activity. |
| `POST` | `/feed/interactions` | Like or pass a profile. Body: `{swiped_id, type, target_type, target_id, comment}` |
| `DELETE` | `/feed/interactions/last` | Rewind — delete last interaction (Premium only) |

### Likes + Matches
| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/likes/received` | Who liked you. Blurred data for free tier, full for Premium. |
| `GET` | `/matches` | All active matches. Sorted by last message time. |
| `DELETE` | `/matches/:id` | Unmatch — sets is_active=false, hides from both chat lists |

### Chat
| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/chats/:match_id/messages` | Paginated message history for a match |
| `POST` | `/chats/:match_id/messages` | Send text message |
| `POST` | `/chats/:match_id/voice` | Upload voice note → get URL → send as voice message |
| `PUT` | `/chats/:match_id/read` | Mark all messages in match as read |
| `GET` | `/chats/weekly-question` | Get this week's icebreaker question |

### Premium + Payments
| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/premium/create-order` | Create Razorpay order for chosen plan |
| `POST` | `/premium/verify-payment` | Verify payment signature, activate subscription |
| `GET` | `/premium/status` | Get current subscription status + expiry |
| `POST` | `/boost/create-order` | Create Razorpay order for profile boost (à la carte) |
| `POST` | `/boost/verify-payment` | Verify boost payment, activate 30-min boost |
| `GET` | `/boost/active` | Check if user has active boost |

### Safety
| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/reports` | Submit a report. Body: `{reported_id, reason, description?}` |
| `POST` | `/blocks` | Block a user. Hides them from feed + chat permanently. |
| `GET` | `/blocks` | List of blocked user IDs |

---

## 7. Checklist

### Week 1 — Foundation
- [ ] Supabase project created (prod + staging)
- [ ] React Native Expo project init
- [ ] FastAPI project structure
- [ ] GitHub repo + branch protection
- [ ] Design tokens in code (colours, spacing)
- [ ] Navigation skeleton with all screen stubs
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] ENV secrets configured

### Pre-Launch (Week 9–10)
- [ ] TestFlight beta distributed to team
- [ ] All screens implemented
- [ ] All API endpoints working
- [ ] Razorpay payment tested end-to-end
- [ ] FCM push notifications tested on device
- [ ] Photo upload + face detection tested
- [ ] Paryushan Mode tested
- [ ] Block/report flow tested
- [ ] Sentry crash reporting set up
- [ ] PostHog event tracking set up

### App Store Submission (Week 10)
- [ ] App icon (1024×1024, saffron-pink, no alpha)
- [ ] Splash screen asset (all sizes)
- [ ] App Store screenshots (6.7in, 6.5in, 5.5in)
- [ ] App Store description written
- [ ] Keywords researched and filled
- [ ] Privacy policy URL live (required)
- [ ] Terms of service URL live (required)
- [ ] Age rating: 17+ (dating app)
- [ ] App Store Connect submission
- [ ] TestFlight external review passed

### Launch Day
- [ ] App Store approved + available
- [ ] Instagram content blitz scheduled
- [ ] All influencer posts ready to go
- [ ] Backend load tested (100 concurrent users minimum)
- [ ] Monitoring dashboards open
- [ ] Team on standby for rapid bug fixes
- [ ] Waitlist email campaign sent
- [ ] WhatsApp group seeding done
- [ ] Founder IG Live scheduled (8pm)
- [ ] Respond to every App Store review within 24h

### Post-Launch Week 1
- [ ] Review crash reports daily (Sentry)
- [ ] Review funnel drop-off (PostHog: signup → like → match → chat)
- [ ] Fix top 3 bugs from user feedback
- [ ] Respond to every DM on @jainune
- [ ] Check feed density in Bangalore (need 500+ active profiles)
- [ ] Review match rate — target >40%
- [ ] Review premium conversion — target 8%+
- [ ] Ship hotfix if critical issue found
