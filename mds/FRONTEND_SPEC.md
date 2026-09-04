# Jainune — Complete Frontend Specification & Architecture

> **A synthesis of Jainune's core identity, Hinge's proven UX mechanics, seamless fusion rules, and craft-first non-AI-slop design guidelines.**

---

## Table of Contents
1. [Quarter 1: Jainune Original DevPlan (Frontend Scope)](#quarter-1-jainune-original-devplan-frontend-scope)
2. [Quarter 2: Hinge UI/UX Reverse-Engineered Architecture](#quarter-2-hinge-uiux-reverse-engineered-architecture)
3. [Quarter 3: The Blend (Hinge Mechanics × Jainune Identity)](#quarter-3-the-blend-hinge-mechanics--jainune-identity)
4. [Quarter 4: Human-Craft UI/UX & Anti-Slop Guidelines](#quarter-4-human-craft-uiux--anti-slop-guidelines)

---

## Quarter 1: Jainune Original DevPlan (Frontend Scope)

### 1.1 Palette & Design Tokens
```javascript
export const tokens = {
  colors: {
    saffron:      "#FF9C4A", // Primary CTA, active states, accents
    saffronMid:   "#FFB366", // Hover states, secondary actions
    saffronLight: "#FFF4EA", // Card backgrounds, input tints
    pink:         "#FFAAC4", // Likes, hearts, match moments
    pinkMid:      "#FF8FAB", // Pressed states, active like icons
    pinkLight:    "#FFF0F5", // Like screen backgrounds, match UI
    dark:         "#1C1C1E", // Main body text, headings
    mid:          "#6C6C70", // Subtitles, hints, labels
    light:        "#F7F3F0", // Section backgrounds
    border:       "#EDE8E3", // Cards, separators, input borders
    white:        "#FFFFFF", // Surfaces
    bg:           "#FFFCFA", // App-wide warm canvas
    green:        "#2E9E6B", // Success badges, verified
    greenLight:   "#EBF7F2",
    blue:         "#3B7DD8", // Information, external links
    blueLight:    "#EBF2FF",
    red:          "#E84040", // Destructive, report, block
    redLight:     "#FFF0F0",
  },
  gradients: {
    primary:   "linear-gradient(135deg, #FF9C4A 0%, #FFAAC4 100%)",
    button:    "linear-gradient(135deg, #FF9C4A, #FF8FAB)",
    overlay:   "linear-gradient(180deg, rgba(0,0,0,0) 60%, rgba(28,28,30,0.85) 100%)",
  },
  spacing: {
    xs:   4,  // Icon gaps, tight margins
    sm:   8,  // Inner-component spacing
    md:   12, // Card inner padding
    base: 16, // Standard screen horizontal gutter
    lg:   20, // Section gaps
    xl:   24, // Major block separation
    xxl:  32, // Screen-level breathing room
  },
  radii: {
    xs:   4,
    sm:   6,
    md:   10,
    lg:   16, // Cards, prompt containers
    full: 9999, // Pill buttons, badges, avatars
  }
};
```

### 1.2 Typography Hierarchy
- **H1 Display** (`32px`, weight 800, line-height 38px): Welcome screens, match celebration header.
- **H2 Screen Title** (`24px`, weight 700, line-height 30px): Screen headers, section banners.
- **H3 Card Title** (`17px`, weight 600, line-height 22px): Profile name, prompt labels.
- **Body Regular** (`15px`, weight 400, line-height 21px): Prompt responses, chat bubbles.
- **Body Small** (`13px`, weight 400, line-height 18px): Captions, timestamps, secondary hints.
- **Caption / Tag** (`11px`, weight 700, line-height 14px, letter-spacing +0.4px): Category tags, upper badges.
- **CTA Button** (`16px`, weight 700, line-height 20px): Primary action buttons.

### 1.3 Core Component Roster
1. **PrimaryButton**: Height `52px`, radius `full` (`26px`), saffron→pink gradient fill, white text 700.
2. **GhostButton**: Height `52px`, radius `full`, border `1.5px solid #FF9C4A`, transparent bg, saffron text 700.
3. **HeartButton**: Circular `56px`, floating bottom-right over photo/card, white base with subtle shadow, pink gradient fill + pulse on active tap.
4. **PassButton**: Circular `48px`, floating bottom-left, light border `#EDE8E3`, subtle grey `✕` icon.
5. **ProfileCard**: Vertical container, 3:4 aspect ratio photo cards, bottom dark gradient overlay for text readability.
6. **PromptCard**: Background `#FFF4EA`, border `1px solid #EDE8E3`, radius `16px`, padding `16px`, prompt label in dark 700 + response in dark 400.
7. **TextInput**: Single bottom-border style (`1.5px solid #EDE8E3`), font `16px`, focus indicator `#FF9C4A`.
8. **OTPInput**: 6 individual boxes, auto-advance, `#FF9C4A` border on filled/focus.
9. **PhotoSlot**: 3:4 ratio, dashed border when empty, photo fill + top-right delete overlay when filled.
10. **ProgressBar**: Top of screen, height `3px`, track `#FFF0F5`, fill `#FF9C4A`, animated width transition.
11. **MatchBurst**: Fullscreen overlay, saffron particle explosion + pink glow ring with dual avatar float.
12. **ChatBubble**: Sent: `#FFF4EA` with `#1C1C1E` text. Received: `#FFFFFF` with `#EDE8E3` border. Radius `16px`.

### 1.4 Onboarding Sequence (22 Screens)
| Step | Screen | Input Mechanism | UX Rule |
| :--- | :--- | :--- | :--- |
| 1 | Splash | Auto-advance (2s) | Jainune mark fade on saffron-pink gradient. |
| 2–4 | Welcome Slides | Horizontal swipe + dots | Value props: "An app that gets it", "Shared world", "Your community". |
| 5 | Phone Number | Numeric keyboard + country picker | Default `+91`, bottom-pinned sticky CTA. |
| 6 | OTP Verify | 6-box auto-advance | 30s resend timer, clipboard auto-paste. |
| 7 | First Name | Bottom-border single input | Capitalize first letter, disable button if empty. |
| 8 | Date of Birth | Drum-roll wheel picker | Enforce 18+ age gate; show age only on profile, never DOB. |
| 9 | Gender | 3 radio cards + "More options" | Man / Woman / Nonbinary / Custom. No visual hierarchy. |
| 10 | Show Me | 3 segmented pills | Men / Women / Everyone. |
| 11 | Looking For | Multi-select chips | Life partner, Long-term, Figuring out, Friends. Minimum 1 required. |
| 12 | City | Searchable FlatList + GPS button | Bangalore highlighted at top of list. |
| 13 | Photos Grid | 3×2 drag-to-reorder grid | Min 3, max 6. Silently runs local ML Kit face check. |
| 14 | Prompts Select | Categorized SectionList | Select exactly 3 prompts from 40+ bank. |
| 15 | Prompt Response | Multi-line text input | 150-character limit with active countdown indicator. |
| 16–17| Job / School | Search + autocomplete | Free text allowed; autocomplete from common roles. |
| 18 | Height | Vertical slider / wheel | Dual display: cm and ft/in shown simultaneously. |
| 19 | Kids Intent | Single-select card list | Want someday / Open to it / Don't want / Have kids. |
| 20 | Drinking Habit | Single-select card list | Never / Occasionally / Socially. |
| 21 | Notifications | Custom pre-permission sheet | Explains "Never miss a match" before triggering iOS/Android dialog. |
| 22 | Location | Custom pre-permission sheet | Explains discovery proximity before system permission prompt. |

### 1.5 Navigation Architecture
Bottom Tab Bar (Fixed 4 tabs):
1. **Feed**: Discovery stream.
2. **Likes**: Who liked you (blurred grid for free, unlocked for Premium).
3. **Chats**: Match strip at top, conversation list below.
4. **Profile**: Preview own card, edit profile, settings, Paryushan toggle.

---

## Quarter 2: Hinge UI/UX Reverse-Engineered Architecture

### 2.1 The Visual Language of Hinge (From Mobbin & Live Teardown)
- **Neutral Canvas**: Built on Cod Gray (`#1A1A1A`) rather than harsh pure black (`#000000`). Subtitles in Dove Gray (`#666666`). Pure White (`#FFFFFF`) card surfaces.
- **Editorial Typography Pairing**:
  - Headlines: High-contrast Editorial Serif (Cheltenham / Canela aesthetic). Creates a literary, mature, thoughtful atmosphere ("Designed to be deleted", "Tips for Connection", "Hinge Reviews").
  - Controls & Prompts: Neutral grotesque sans-serif (Proxima Nova / Neue Haas style) for clear legibility on mobile viewports.
- **Brand Accent**: Deep Plum / Aubergine (`#4C243B` / `#36162E`), evoking quiet luxury, intentionality, and intimacy rather than fast dopamine.

### 2.2 Profile Anatomy & The Scroll Rhythm
Hinge replaced the binary swipe deck with a **continuous vertical narrative**:
1. **Header**: Name, age, verified badge, and a top-right 3-dot report/overflow menu.
2. **Slot 1 (Lead Photo)**: 3:4 aspect ratio, full-width bleed with rounded card borders. Floating circular Heart button in bottom-right corner.
3. **Slot 2 (Prompt 1)**: Large serif prompt label (`"I geek out on..."`) followed by a conversational response. Floating Heart button bottom-right.
4. **Slot 3 (Secondary Photo)**: Additional angle/action shot.
5. **Slot 4 (Basics Strip)**: Horizontal row of compact pills (Height, City, Job, Religion, Drinking). Tappable to reveal detail.
6. **Slot 5 (Prompt 2)**: Personality/humor anchor prompt.
7. **Slots 6–8 (Remaining Photos + Prompt 3)**: Completing the 6-photo, 3-prompt requirement.
8. **Bottom Floating Controls**: Left `✕` Pass button (minimalist, low visual weight) and Right Heart Like button.

### 2.3 The Like-Comment Sheet Interaction
- Tapping any heart does **not** instantly fire an unthinking like.
- It summons a **Bottom Sheet Drawer**:
  - Displays a thumbnail of the specific photo or prompt being liked.
  - Text input: `"Add a comment..."` (Optional for photos, **required for prompts**).
  - Send Button: High-contrast pill (`"Send Like"`).
- **Psychological impact**: 3x higher conversation initiation rate compared to photo-only double taps.

### 2.4 Hinge Standouts & Review Ecosystem
- **Standouts Tab**: Daily curated carousel of top prompts and photos based on user's latent preference profile.
- **"We Met" / Hinge Reviews**:
  - Post-date feedback loop ("Things you Did", "Rate the Date Experience").
  - Monoline ink sketch illustrations reduce stress and make accountability feel supportive.
  - Feeds reciprocal Gale-Shapley matching data.

### 2.5 Paywall Architecture (Hinge+ / HingeX)
- Dark mode presentation (`#111111`).
- Top segmented switcher between membership tiers.
- High-contrast card grid highlighting the "Sweet Spot" (3 months, "Save 67%", broken down into weekly pricing).
- Solid white pill CTA with black bold text for maximum contrast.

---

## Quarter 3: The Blend (Hinge Mechanics × Jainune Identity)

### 3.1 What Jainune Adopts Directly from Hinge (Proven Mechanics)
1. **Vertical Narrative Feed**: Zero horizontal card flipping. Users scroll an authentic profile top-to-bottom.
2. **Granular Asset Liking**: Users like a *specific photo* or *specific prompt*, not an abstract persona.
3. **Bottom Sheet Comment Drawer**: Every like provides a canvas for a conversational opening line.
4. **Strict Profile Completeness (6 Photos + 3 Prompts)**: Enforces effort before discovery access is granted.
5. **Subtle Pass Button**: Instant dismissal without dramatic reject animations or sound effects.

### 3.2 Where Jainune Diverges (Originality & Cultural Identity)
| Feature | Hinge | Jainune Original |
| :--- | :--- | :--- |
| **Color Atmosphere** | Deep plum, dark headers, muted slate | Radiant Indian warmth: Saffron (`#FF9C4A`), Baby Pink (`#FFAAC4`), warm cream canvas (`#FFFCFA`) |
| **Typography Vibe** | Western literary serif + grotesque sans | Warm rounded sans display (`Outfit` / `Plus Jakarta Sans`) paired with crisp body sans (`Inter`) |
| **Cultural Modes** | None | **Paryushan Mode**: 8/10-day profile banner, match preservation, auto chat freeze, respect for spiritual downtime |
| **Prompt Bank** | Generic Western lifestyle prompts | Community-resonant prompts: Food boundaries, Navkarasi spots, family dynamics, joint vs nuclear values |
| **Match Celebration** | Understated text slide-in | **MatchBurst**: Saffron particle fireworks, soft pink glow ring, dual profile float, festive Indian warmth |
| **Navigation** | 5 tabs (includes Standouts) | 4 tabs (simplified, Standouts integrated into Top of Feed as "Curated Daily") |

### 3.3 The Jainune Prompt Bank (Original Content)
Prompts engineered specifically for the Jainune demographic:
- *Category 1: Lifestyle & Food*
  - "My relationship with onion and garlic on a Friday night is..."
  - "The best Jain meal I've ever had was at..."
  - "My non-negotiable dietary boundary..."
- *Category 2: Values & Family*
  - "How my family would describe me in 3 words..."
  - "In 10 years, I see our Sunday mornings looking like..."
  - "The festival I take most seriously is..."
- *Category 3: Quirks & Personality*
  - "I'm a 10, but during Derasar visits I..."
  - "Teach me something about your family business..."
  - "The easiest way to win over my grandmother is..."

---

## Quarter 4: Human-Craft UI/UX & Anti-Slop Guidelines

### 4.1 Anti-AI Slop Rules (Strict Design Standards)
1. **Zero Unjustified Glassmorphism**: Never use frosted glass (`backdrop-filter: blur()`) on core readable content. Glass is strictly reserved for floating top navbars during scroll.
2. **Zero Neon Gradients on Text**: Never apply multi-color gradients across body text or titles. Gradients belong exclusively on primary CTA buttons and the match burst moment.
3. **No Decorative Clutter**: Never insert floating abstract shapes, meaningless sparkles, or decorative blob vectors. Every pixel must serve profile clarity or direct interaction.
4. **No Card-in-Card Nesting**: A prompt card must not sit inside another card. Single-level surface hierarchy: Canvas (`#FFFCFA`) → Surface (`#FFFFFF`) → Border (`#EDE8E3`).
5. **No Infinite Walls of Text**: Prompts are capped at 150 characters. Bios do not exist as essay blocks; information is chunked into discrete, bite-sized cards.

### 4.2 Spacing, Breathing Room & De-Cluttering
- **Vertical Rhythm**: Maintain `24px` spacing between each photo and prompt block in the feed. This forces pause and visual digestion.
- **Screen Margins**: Global horizontal padding is locked to `16px`. Full-bleed photos touch edges, with an inner container margin of `16px` for text and controls.
- **The "One Focal Point" Rule**: At any point during a feed scroll, the viewport must contain at most **one active prompt** or **one primary photo**. Never display two prompts simultaneously on screen.
- **Touch Target Discipline**:
  - Minimum touch bounding box: `48×48px` (even if the icon is `24px`).
  - CTA Button Height: `52px` minimum for single-hand thumb reach.
  - Bottom Tab Bar Height: `64px` + device safe-area inset.

### 4.3 Gesture & Haptic Engineering
- **Scroll Physics**: Custom spring deceleration on React Native `ScrollView` / `FlashList`. No abrupt stops.
- **Like Sheet Animation**:
  - Springs up with `damping: 24`, `stiffness: 220`, `mass: 0.8` (feels physical, not floaty).
  - Automatically raises with the soft keyboard using `KeyboardAvoidingView` with zero layout stutter.
- **Haptic Tactile Feedback**:
  - Heart Tap: `Haptics.impactAsync(ImpactFeedbackStyle.Light)`.
  - Pass Button Tap: `Haptics.impactAsync(ImpactFeedbackStyle.Medium)`.
  - Match Moment: `Haptics.notificationAsync(NotificationFeedbackType.Success)`.
  - Chip Toggle: `Haptics.selectionAsync()`.

### 4.4 Trust, Comfort & Dating Psychology
- **Lowering Rejection Anxiety**:
  - Likes received are framed as "Someone liked your prompt" rather than "Someone swiped right on your photo". Focus on shared words and thoughts over pure physical judgment.
- **Paryushan Mode Sensitivity**:
  - Toggling this mode disables discovery push notifications and places an elegant cream-and-saffron badge on the profile: *"Taking time for Paryushan. Chats paused until Samvatsari."*
- **Photo Verification Authenticity**:
  - Verified profiles carry a small, non-obtrusive green checkmark badge (`#2E9E6B`) next to the name, never an ostentatious banner.

---

## Quarter 5: Next-Gen Redefined UX Architecture (Post-Swipe Era)

### 5.1 The Anti-Fatigue Paradigm Shift
Standard dating apps (Tinder, Bumble, Hinge) suffer from dating app burnout caused by three systemic design flaws:
1. **Catalog Commodification**: Endless swipe/scroll decks turn humans into infinite inventory.
2. **Asynchronous Stagnation**: Matches collect passively with zero momentum, producing 85% ghosting rates.
3. **Static Resumes**: Predictable photo-prompt grids encourage rehearsed personas rather than raw chemistry.

Jainune redefines this through five foundational next-gen mechanics:

```
[ Spatial Orbit Feed ] ---> [ Ambient Voice Canvas ] ---> [ 72h Momentum Protocol ] ---> [ In-Person City Drop ]
```

---

### 5.2 Kinetic Core Features

#### Feature A: The Spatial Orbit Feed (Replacing Vertical Scrolling)
- **Concept**: Instead of linear scrolling through identical card formats, profiles appear as dynamic nodes in a gravity-based spatial field ("The Orbit").
- **Visual Presentation**:
  - The user's avatar sits at the center of a subtle circular radar ring canvas (`#FFF4EA`).
  - Candidate profiles orbit at varying radial distances based on mutual compatibility score calculated by the reciprocal matching engine.
  - Nodes closer to the center share higher values alignment (dietary discipline, life trajectory, mutual social spheres).
- **Interaction Mechanics**:
  - Dragging across the spatial field rotates the orbit with fluid inertia (`decay` animation).
  - Tapping an orbital node smoothly expands it into the **Vibe Canvas** via a shared-element fluid scale transition (400ms cubic bezier `(0.16, 1, 0.3, 1)`).
  - Flicking outward dismisses a node with smooth Doppler particle dissipation.

#### Feature B: Ambient Voice Canvas (Audio-First Micro-Moments)
- **Concept**: Visuals establish recognition, but vocal cadence, inflection, and laughter establish biological attraction.
- **Specification**:
  - Each profile features a compulsory 7-second "Vibe Snapshot" recorded directly in-app.
  - **Zero Polished Audio**: Background noise cancellation is intentionally reduced to capture authentic environment acoustics (e.g. coffee brewing, rain, ambient street murmur).
  - **Dynamic Waveform Visualizer**: Soundwaves render as 32 vertical bars with reactive height scaling (`12px` to `48px`), colored with Saffron-to-Pink gradient interpolation.
  - Scrubbing the waveform produces tactile linear haptic ticks per frame (`Haptics.selectionAsync()`).

#### Feature C: Progressive Depth Reveal (Anti-Superficiality Shield)
- **Concept**: Prevents immediate 2-second snap judgments based purely on visual angles.
- **Mechanics**:
  - Lead Photo 1 is visible in full clarity.
  - Photos 2 through 6 are dynamically blurred with progressive Gaussian blur (`sigma: 24` down to `0`).
  - Blur dissolves automatically when the viewing user listens to the Voice Snapshot for at least 4 seconds or engages with a community value prompt.
  - This shifts the cognitive reward loop from visual scanning to personal exploration.

#### Feature D: The 72-Hour Momentum Protocol (Zero-Ghosting Mechanism)
- **Problem**: Matches sit dormant for weeks, decaying into conversational dead-ends.
- **Solution**:
  - Upon a mutual match, a circular **Momentum Ring** appears above the chat thread with a 72-hour hard countdown.
  - The ring shifts color dynamically: Saffron (`#FF9C4A`) from 72h to 24h, transitioning to Soft Amber (`#E8700A`) below 24h, and Deep Rose (`#E84040`) in the final 6 hours.
  - **Momentum Triggers**: Exchanging at least 3 voice notes or setting an in-person date proposal locks the match permanently.
  - If neither party takes action within 72 hours, the match quietly dissolves into the background without awkward notifications, clearing emotional clutter.

#### Feature E: The Sunday City Drop (Curated Bangalore Pairing)
- **Concept**: Converting digital matches into real-world shared tables.
- **Protocol**:
  - Every Thursday at 20:00 IST, users opt into the "Weekend Drop".
  - The engine matches exactly one compatible pair within a 6km radius who share dietary parameters (e.g., pure Jain dining restrictions, non-alcoholic preference).
  - Unveils a curated location voucher at vetted cafes and breakfast spaces (e.g., Indiranagar, Jayanagar, Koramangala) with a pre-set conversation prompt.

---

### 5.3 Custom Hairline SVG Iconography System (Zero Emojis)
All iconography is built strictly from 1.5px hairline vector geometry. No external font icon libraries or raster emojis.

#### 1. Orbit Feed Icon (`icon-orbit.svg`)
```xml
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#1C1C1E" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3" />
  <ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(-30 12 12)" />
  <circle cx="19" cy="8" r="1.2" fill="#FF9C4A" stroke="none" />
</svg>
```

#### 2. Soundwave / Voice Pulse Icon (`icon-voice.svg`)
```xml
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#FF9C4A" stroke-width="1.5" stroke-linecap="round">
  <line x1="4" y1="10" x2="4" y2="14" />
  <line x1="8" y1="6" x2="8" y2="18" />
  <line x1="12" y1="3" x2="12" y2="21" />
  <line x1="16" y1="7" x2="16" y2="17" />
  <line x1="20" y1="11" x2="20" y2="13" />
</svg>
```

#### 3. Momentum Clock Icon (`icon-momentum.svg`)
```xml
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#1C1C1E" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="9" />
  <polyline points="12 6 12 12 16 14" />
  <path d="M19.5 4.5 L21 3" stroke="#FF8FAB" />
</svg>
```

#### 4. Paryushan Serenity Leaf Icon (`icon-serenity.svg`)
```xml
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#FF9C4A" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 2C6.5 2 2 6.5 2 12C2 17.5 6.5 22 12 22C17.5 22 22 17.5 22 12" />
  <path d="M12 2C12 12 22 12 22 12" />
  <path d="M2 12C2 12 12 12 12 22" />
</svg>
```

#### 5. Clean Action Cross Icon (`icon-pass.svg`)
```xml
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#6C6C70" stroke-width="1.5" stroke-linecap="round">
  <line x1="18" y1="6" x2="6" y2="18" />
  <line x1="6" y1="6" x2="18" y2="18" />
</svg>
```

#### 6. Kinetic Heart / Spark Icon (`icon-spark.svg`)
```xml
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#FF8FAB" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
</svg>
```

---

### 5.4 Motion Choreography & Transition Physics
All screen motions utilize React Native Reanimated with physical spring configurations instead of artificial easing curves.

| Interaction | Animation Primitive | Spring Parameters | Visual Behavior |
| :--- | :--- | :--- | :--- |
| **Orbit Node Tap** | Shared Element Transition | `stiffness: 240, damping: 26, mass: 1` | Node scales from circle into full canvas without layout flicker |
| **Voice Bar Pulse** | Continuous loop with noise offset | `damping: 12, stiffness: 90` | Waveform heights oscillate proportionally to audio decibels |
| **Momentum Ring** | SVG StrokeDashoffset animation | `duration: 600ms, linear` | Smooth radial progress consumption |
| **Progressive Unblur** | Skia Image Shader Blur | `sigma: withTiming(0, { duration: 450 })` | Gaussian blur clears like steam wiping off glass |
| **Match Moment Burst**| Radial particle explosion | 48 vector particles, randomized velocity vectors | Particles decelerate with gravity decay, settling into a glowing halo |

---

### 5.5 Modern Clean UI Layout & Zero-Clutter Spatial Rules

1. **Strict 8-Point Grid System**:
   - Every margin, padding, height, and width is an integer multiple of 4 or 8 (`4px`, `8px`, `16px`, `24px`, `32px`, `48px`, `64px`).
   - Zero odd-number offsets (`7px`, `13px`, `21px` are strictly banned).

2. **Contrast Hierarchy Without Heavy Lines**:
   - Never rely on dark borders to separate content blocks.
   - Use subtle surface tone shifts: `#FFFCFA` (Canvas) to `#FFFFFF` (Surface Card) with a featherweight 1px border `#EDE8E3`.
   - Primary data points use `#1C1C1E` (weight 700); supporting context uses `#6C6C70` (weight 400); decorative metadata uses `#9C9CA0` (weight 500, uppercase, letter-spacing +1.2px).

3. **No Redundant Visual Elements**:
   - No badges saying "New" or "Hot". The algorithm speaks through orbital placement.
   - No explicit percentage matching numbers (e.g. "94% Match" creates false gamification). Orbital distance communicates affinity organically.
   - No distracting floating sticker overlays or animated gift icons. Interactions are deliberate, personal, and grounded.

---

## Quarter 6: Redefining Discovery, Messaging, & Date Feedback (Next-Gen Playful Mechanics)

### 6.1 Reinventing How You Find People (Beyond Endless Profiles)

#### 1. The Blind 3-Question Dilemma Duel (Daily 20:00 IST Synchronous Game)
- **Problem**: Photos bias people before they know if they laugh at the same jokes or share worldviews.
- **Mechanic**:
  - Every evening at 20:00 IST, users get a notification: "The 3-Question Duel is Live".
  - Two matched users are paired completely blind (blurred silhouette, no names, no photos).
  - 3 fast-paced cultural dilemma cards appear sequentially (15 seconds per card):
    - Dilemma 1: "Street food chaos at midnight OR quiet rooftop dinner?"
    - Dilemma 2: "Bangalore traffic coping mechanism: podcasts in bumper-to-bumper OR metro commute with headphones?"
    - Dilemma 3: "Sunday ritual: Navkarasi brunch with extended family OR sleeping in till noon?"
  - **The Spark Reveal**: If both users choose 2 or more identical answers, their photos and profiles simultaneously unlock on screen with a warm particle celebration. If choices diverge, both are gently returned to the home screen with zero awkwardness.

#### 2. The Bangalore Vibe Map (Hangout Proximity Without Tracking)
- **Problem**: Finding out you live in Whitefield while your match is in Jayanagar kills 60% of Bangalore dates before they happen.
- **Mechanic**:
  - Profiles feature an interactive, privacy-fuzzed "Weekend Orbit" badge selecting up to 3 favored cultural zones:
    - Central Hub: Church Street, Lavelle Road, Cubbon Park.
    - East Corridor: Indiranagar 12th Main, HAL, Koramangala 4th Block.
    - South Culture: Jayanagar 4th Block, JP Nagar, VV Puram.
  - Users discover matches who naturally frequent the same coffee houses, parks, and dining spots without ever sharing GPS coordinates or live location data.

#### 3. Friend Endorsement & Co-Pilot Wingman Mode
- **Problem**: Self-written bios are biased, awkward, and often inaccurate.
- **Mechanic**:
  - **Friend Voice Seal**: A user's close friend can record a 15-second audio testimony ("Why you should date my friend"). It sits prominently on the profile as a verified social badge.
  - **Wingman Queue Review**: Users can send a private 24-hour web link to a best friend. The friend can review the discovery pool from their perspective, tagging profiles with non-judgmental stamps: "Shares your humor", "Great family values", "Elite music taste".
  - The primary user sees these friend endorsements overlaid on their feed cards.

#### 4. Sunday Navkarasi Brunch Circles (Low-Pressure Small Group Dates)
- **Problem**: High-pressure 1-on-1 first dates create intense performance anxiety.
- **Mechanic**:
  - Users can toggle "Open to Brunch Circles".
  - On Friday afternoons, the algorithm pairs two compatible male friends with two compatible female friends for a curated 4-person table at vetted pure vegetarian/Jain breakfast spots across Bangalore.
  - Group dynamic eliminates 1-on-1 awkwardness, turning dating into an enjoyable social outing.

---

### 6.2 Reinventing Messaging (Ending Boring Small Talk & Ghosting)

#### 1. The 60-Second Ephemeral Voice Spark
- **Problem**: Texting "Hey, what's up" leads to immediate conversational decay.
- **Mechanic**:
  - When two users match, instead of opening an empty text field, they receive an optional "60-Second Spark" challenge.
  - If both accept, a lightweight 60-second audio connection opens with a fun prompt card displayed on both screens (e.g., "Describe your most chaotic family wedding moment in 30 seconds").
  - A subtle 60-second countdown runs at the top.
  - At the end of 60 seconds, both get a prompt: "Keep talking?". If both press Yes, full permanent text, audio, and media chat opens. If either declines, the chat closes politely.

#### 2. Simultaneous Reveal / The Question Bounty
- **Problem**: One person asks thoughtful questions, the other responds with one-word answers.
- **Mechanic**:
  - Either user in chat can drop a "Bounty Card" chosen from a curated list of high-chemistry questions.
  - Both users must type and submit their response.
  - **Double-Blind Lock**: Responses remain blurred until *both* participants have submitted their answer.
  - Once both answers are submitted, they unlock simultaneously. This enforces equal vulnerability and conversational investment.

#### 3. Collaborative Date Canvas (Swiggy Date Builder)
- **Problem**: The agonizing back-and-forth of "Where do you want to go?" / "I don't know, you pick".
- **Mechanic**:
  - An interactive shared card embedded directly into the chat thread.
  - User A taps: Zone (Indiranagar / Jayanagar / Koramangala).
  - User B taps: Vibe (Art cafe / Casual street walk / Quiet dinner).
  - Both toggle: Dietary rules (Pure Jain / Vegetarian / Vegan).
  - The app automatically generates 3 vetted venue cards matching both criteria with a single tap to propose date time.

---

### 6.3 Reinventing Post-Date Evaluation (Ending Toxic Star Ratings)

#### 1. The Green Flag Capsule (Peer-Verified Reputation Badges)
- **Problem**: 1-to-5 star ratings or Yelp-style reviews are humiliating, punitive, and turn humans into commercial products.
- **Solution**:
  - 24 hours after a scheduled date, both users receive a private "Date Reflection" sheet.
  - Users cannot leave negative text reviews or star ratings.
  - Instead, users award positive **Green Flag Badges** from a curated list:
    - "Punctual & Respectful of Time"
    - "Looks Exactly Like Profile Photos"
    - "Exceptional Conversationalist"
    - "Respects Dietary & Personal Boundaries"
    - "Effortless & Fun Energy"
    - "Gentlemanly / Gracious Manner"
  - **Aggregate Privacy Protection**: Badges are strictly anonymous and only display on a user's public profile once 3 or more independent dates have awarded the identical badge. This builds authentic community trust.

#### 2. The Graceful Exit Protocol (Mutual Decency Escrow)
- **Problem**: People ghost because sending a rejection text feels confrontational, while the recipient is left in limbo.
- **Mechanic**:
  - Inside the chat thread or reflection sheet, a user can tap "Graceful Close".
  - The user selects one of three warm, dignified pre-set closures:
    - Option 1: "Loved meeting you, but felt more of a friendly connection. Wishing you the absolute best on your journey."
    - Option 2: "Really enjoyed our conversation, but don't think our life trajectories align. Thank you for your time."
    - Option 3: "Grateful for the date, but didn't feel romantic chemistry. Hope you find your person soon."
  - The message delivers with a calm, respectful visual treatment.
  - Both users are immediately unlinked from discovery without penalty, leaving zero lingering resentment or ghosting anxiety.

#### 3. Split-The-Bill Karma
- **Mechanic**:
  - A discreet checkmark on post-date reflection: "Did you split or handle the bill equitably?".
  - Contributes to a subtle behind-the-scenes "Accountability Score", prioritizing users who treat their dates with mutual respect.

---

## Quarter 7: High-Chemistry Match Moments & Anti-Ragebait Dignity Architecture

### 7.1 Deconstructing & Reinventing "The Match Moment"

#### What Existing Dating Apps Do (And Why It Fails)
- **The Industry Standard (Tinder, Bumble, Hinge)**:
  - User swipes or likes.
  - A modal pops up: "It's a Match!" showing two circular profile photos side-by-side.
  - Two buttons appear: "Send Message" and "Keep Swiping".
- **The Psychological Failure**:
  - Over 75% of users tap "Keep Swiping" because sending a message from a blank slate triggers performance anxiety.
  - Those who do tap "Send Message" are dropped into an empty, sterile text input.
  - The result is either silence, generic "Hey" messages, or matches that rot permanently in the inbox.

---

#### The Jainune Match Moment: A 4-Phase Experiential Ritual
In Jainune, matching is not a static pop-up banner. It is an active, gamified 4-phase micro-experience designed to launch high-momentum conversation within 30 seconds of connection.

```
[ Phase 1: Resonance Convergence ] (0s - 2s)
            |
            v
[ Phase 2: Mutual Chemistry Ticker ] (2s - 4s)
            |
            v
[ Phase 3: The First Move Wager ] (4s - 12s)
            |
            v
[ Phase 4: Thread Launch with Pinned Root ]
```

---

#### Phase 1: Resonance Convergence (0.0s – 2.0s)
1. **Trigger Event**:
   - Client receives a WebSocket event: `EVENT_MATCH_MUTUAL` containing `{ match_id, user_a, user_b, asset_liked_a, asset_liked_b }`.
2. **Visual Animation**:
   - Screen background softens into a warm dark vignette (`#1C1C1E` at 92% opacity).
   - Rather than generic circular avatars, the **specific assets that caused the match** converge:
     - From screen-left: The photo or prompt card of User B that User A liked.
     - From screen-right: The photo or prompt card of User A that User B liked.
   - Both cards slide inward on an elastic spring curve (`stiffness: 260, damping: 22`) and meet at a 6-degree overlapping tilt in the center viewport.
   - An interactive hairline vector spark bridges the two cards.

---

#### Phase 2: Mutual Chemistry Ticker (2.0s – 4.0s)
Directly beneath the converging cards, an animated container unrolls displaying the **Resonance Breakdown**:
- Three specific shared alignment data points extracted by the matching engine:
  - **Dietary Harmony**: *"Both strictly pure vegetarian / no root vegetables"*
  - **Neighborhood Orbit**: *"Both spend weekend mornings around Indiranagar 12th Main"*
  - **Life Alignment**: *"Both seeking life partnership with joint family openness"*
- **Cognitive Purpose**: Instantly reminds both users of the deep, non-superficial reasons they aligned before a single word is typed.

---

#### Phase 3: The First Move Wager (4.0s – 15.0s)
Instead of an empty text field, the screen presents an interactive, playful dilemma card: **The First Move Wager**.

Users select between three conversational launchpads:

##### Option A: The Culinary Wager (Playful Bangalore Stakes)
- An interactive toggle card with a single rule:
  - *"The first person to send a message chooses the date activity. The respondent chooses the cafe or dessert spot."*
- Solves the paralysis of who talks first by turning initiative into a strategic advantage.

##### Option B: 5-Second Voice Ping-Pong (Instant Audio Chemistry)
- An in-modal recording capsule appears:
  - A random lighthearted prompt displays: *"State your favorite Sunday breakfast spot in Bangalore in under 3 seconds."*
  - Either user can tap and hold the microphone button to leave a spontaneous 3-to-5-second soundbite.
  - As soon as the first user records, the second user receives a push notification: *"Your match recorded a 4-second audio ping! Tap to hear and reply."*
  - Removes text overthinking entirely.

##### Option C: The Chemistry Time Capsule
- Both users are presented with a blind 1-sentence prompt before text chat unlocks:
  - Prompt: *"Our first hypothetical disagreement will definitely be about..."*
  - User types their answer. The response is encrypted and displayed as a floating wax-sealed capsule at the top of the chat thread.
  - The capsule automatically unseals and reveals both answers once the conversation reaches 40 exchanged messages or an in-person date proposal is accepted.

---

#### Phase 4: Thread Launch with Pinned Root
When either user taps into the chat thread:
1. **The Root Anchor**: The exact prompt or photo that initiated the match remains pinned as Card Zero at the top of the conversation list.
2. **Context-Aware Input**: The placeholder text in the message bar is never "Type a message...". It displays:
   - *"Reply to Caroline's prompt about Sunday mornings..."*
3. **The 72-Hour Momentum Ring**: Positioned discretely in the top-right header, showing the remaining hours to establish conversational cadence.

---

### 7.2 The Anti-Ragebait Dignity Engine (Exhaustive System Architecture)

#### Why Dating Apps Cause Emotional Burnout & Rage Deletions
1. **The Concentration Monopoly (Gini Coefficient > 0.8)**:
   - Standard apps route 85% of incoming likes to the top 10% most conventional profiles.
   - 90% of sincere, quality users receive zero feedback, concluding they are undesirable and deleting the app in frustration.
2. **Ghost Hoarding**:
   - Casual users collect 40 to 80 active matches simultaneously, responding to none.
   - Senders experience serial silence, creating burnout.
3. **Algorithmic Withholding**:
   - Platforms deliberately store incoming likes behind paywalls, sending manipulative notifications ("Someone likes you!") to trigger anxiety and monetize insecurity.

---

#### System Component 1: The Visibility Floor (Guaranteed Impressions Quota)
- **Algorithmic Rule**: Every verified profile that has logged in within 72 hours is assigned a rolling **Impression Balance**.
- **The Guarantee**:
  - The feed distribution pipeline guarantees each user a minimum of **35 high-intent discovery impressions every 48 hours** to compatible users within their age and location preferences.
- **Fair Rotation Index**:
  - Instead of ranking profiles purely by visual swipe-ratios (ELO), Jainune calculates a **Health Score ($H$)**:
    $$H = 0.4 \times (\text{Prompt Depth}) + 0.3 \times (\text{Response Rate}) + 0.3 \times (\text{Green Flag Reputation})$$
  - Users who engage thoughtfully, reply to messages, and hold verified reputation badges are boosted to the top of the local orbit regardless of follower counts or vanity metrics.

---

#### System Component 2: The Gentle Queue (Soft Cap of 3 Active Chats)
- **Problem**: Nobody can genuinely maintain 15 meaningful romantic conversations simultaneously. It inevitably produces one-word replies and ghosting.
- **Technical Specification**:
  - A user can hold a maximum of **3 active open conversation slots** in their Chats tab.
  - If a user reaches 3 active chats, their discovery profile is placed in a **"Snoozed & Focused"** state in the global feed.
- **How a Slot Frees Up**:
  1. **Date Scheduled**: Tapping "Propose Date" moves the match to the "Upcoming Dates" vault, unlocking an open chat slot.
  2. **The Graceful Exit Protocol**: Either user sends a dignified, pre-set closure card, archiving the chat cleanly.
  3. **72-Hour Momentum Expiration**: Inactive threads dissolve automatically.
- **Psychological Result**: Matches are treated as rare, focused opportunities rather than disposable disposable notifications.

---

#### System Component 3: Proactive Profile Health Coach (Constructive Coaching)
- **Problem**: When a user gets zero matches on Tinder, the app gives complete silence. The user assumes the worst about themselves.
- **Implementation**:
  - If a user's profile receives fewer than 2 likes over 100 discovery impressions, the automated **Profile Health Diagnostic** runs silently on device:
    - Analyzes photo lighting, face framing, prompt character counts, and voice snapshot noise floors.
  - A private, warm, supportive coaching card appears inside their own Profile tab:
    - Header: *"Let's optimize your profile's genuine warmth."*
    - Tip 1: *"Your second photo is a bit shadowed. Adding a natural daylight photo increases match connections by 42% in Bangalore."*
    - Tip 2: *"Your prompt about food is great, but very brief! Expanding with your favorite local spot gives matches an easy conversation hook."*
  - Transforms rejection into constructive, empowering personal presentation.

---

#### System Component 4: The Monthly Second Glance
- **Problem**: People swipe while tired, distracted, or in bad moods, rejecting great compatible partners in half a second.
- **Specification**:
  - On the 1st of every calendar month at 10:00 IST, the app presents a special section: **"Second Glance"**.
  - Displays exactly 3 profiles that the user passed on during the preceding 30 days who share the highest reciprocal life goals and dietary preferences.
  - Frame: *"Sometimes great people catch us on busy days. Here are 3 people whose life values match yours."*
  - Users can review these profiles with zero pressure and zero penalty.

---

#### System Component 5: Zero Paywalled Withholding (Transparent Likes)
- **Anti-Exploitation Policy**:
  - Jainune will **never** artificially hold back likes to force a subscription.
  - Free tier users see the exact number of people who liked them with blurred previews.
  - One like is completely unlocked for free every 24 hours without paying, ensuring every active participant has a clear, accessible path to genuine connection.




