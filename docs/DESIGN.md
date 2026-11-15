# V Notice — Design System & UI/UX Architecture

**Document Version:** 2.1.0  
**Status:** Living Design Specification  
**Product:** V Notice (Smart Campus Digital Notice Board & Kiosk)  
**Last Updated:** October 11, 2026  

---

## 1. Brand Identity & Geometric Vector Mark

The official V Notice mark features a bold geometric **"V" centered in a wide bow-tie shaped screen frame** (an outlined shape widening toward the left and right edges and narrowing behind the V) with **three concentric broadcast arcs** above the V's top (small, medium, large), built on exact vector geometry within a 415×292 canvas (`viewBox="0 0 415 292"`, aspect ratio 1.4212):

* **Mark Geometry & Parts:**
  - *Group `mark`:* Geometric V with 63.4° arm slope (`dx/dy = 0.5`), flat 54px arm tops at `y = 118`, inner notch vertex at `(207, 226)`, flat 42px bottom tip at `y = 291`; bow-tie screen frame with 24px vertical borders at `x = 0..24` and `x = 390..414`, sloping top borders from `(0, 71)` to `(130, 118)` and `(414, 71)` to `(284, 118)`, and sloping bottom borders from `(0, 268)` to `(137, 233)` and `(414, 268)` to `(277, 233)`.
  - *Group `arcs`:* Three concentric broadcast arcs centered at `(207, 166)` with round caps and consistent stroke widths:
    - *Outer Arc 3:* Radius `R = 155.5`, stroke 20px, span -39° to +39°
    - *Middle Arc 2:* Radius `R = 116.0`, stroke 19px, span -34° to +34°
    - *Inner Arc 1:* Radius `R = 76.5`, stroke 18px, span -27° to +27°
* **Brand Color Palette:**
  - *Vanilla:* `#EEEBDA` (Primary mark fill on dark surfaces: kiosk, dark admin, dark public notice)
  - *Ink:* `#131210` (Primary mark fill on light surfaces: light admin, light public page)
  - *Gold:* `#B08D57` (Concentric broadcast arcs on dark surfaces; 6.06:1 contrast ratio > 4.5:1 WCAG AA)
  - *Darker Gold:* `#8A6B3A` (Broadcast arcs on light surfaces; 4.39:1 contrast ratio > 3:1 WCAG AA on vanilla `#F5F1E8`)
  - *Urgent Red:* `#EF4444` (Arcs takeover in urgent broadcast state)
* **Surface Rules & Theme Variables:**
  - *Dark Surfaces (Kiosk, Dark Admin):* Mark `#EEEBDA`, Arcs `#B08D57`.
  - *Light Surfaces (Light Admin, Light Public Page):* Mark `#131210`, Arcs `#8A6B3A`.
  - Driven by CSS custom properties:
    - `--logo-mark`: `#EEEBDA` (dark) / `#131210` (light)
    - `--logo-arcs`: `#B08D57` (dark) / `#8A6B3A` (light)
    - Backward-compatible aliases: `--logo-sheet: var(--logo-mark)`, `--logo-accent: var(--logo-arcs)`
* **Typography & Lockups:**
  - *Wordmark "V Notice":* Outfit 700 (Bold) for clean geometric optical balance. Letter-spacing `-0.01em`. Cap height ~0.34 of mark height. Vertically centered on mark center line across lockups.
  - *Descriptor "DIGITAL NOTICE PLATFORM":* Inter 500 (Medium), uppercase, letter-spacing `0.20em`. Left edge aligned flush with the left edge of "V" in wordmark, right edge aligned with the right edge of "Notice". Color `#6E685F` on light surfaces (4.89:1 contrast ratio > 4.5:1 WCAG AA), vanilla at 70% (`rgba(238, 235, 218, 0.70)`) on dark surfaces (7.95:1 contrast ratio > 4.5:1 WCAG AA).
  - *Visibility Rule:* Appears ONLY in lockup files, Open Graph image, and stacked login card. Never in kiosk header, admin header, public page header, favicons, or app icons; hidden in any lockup rendered under 160px wide.
  - *Outlines:* Final lockup SVGs convert text to `<path>` outlines, accompanied by editable-text comment fallbacks specifying font families, sizes, and tracking.
* **Compact Cut for Tiny Sizes:**
  - Wide bow-tie frame lines are omitted for ultra-small sizes to guarantee crisp rendering without sub-pixel blur.
  - Retains the bold central "V" and concentric broadcast arcs within a rounded-square tile style (`rx="64"` in 320×320 box).
  - 16px & 24px cut uses two thickened arcs (stroke 32px & 28px) ensuring the arcs never turn to mush at tiny resolutions.
  - Used for `favicon-16.svg`, `favicon-32.svg`, `favicon.ico` (16, 32, 48), `apple-touch-icon.png` (180), `icon-192.png`, `icon-512.png`, and maskable icons (full-bleed `#131210` background with compact mark inside central 80% safe zone).
* **Special States & Animation:**
  - *Urgent Broadcast Takeover:* The three broadcast arcs turn `#EF4444` (replaces legacy crimson fold/dot).
  - *Kiosk-Only Pulse:* A subtle 2.4s brightness pulse (`brightness(1)` to `brightness(1.28)`) on the broadcast arcs (staggered by 0.2s per arc) on the kiosk header only, automatically disabled under `@media (prefers-reduced-motion: reduce)`.
  - *Admin Portal & Public Notice:* Zero animation.
* **Asset Catalog:**
  - `static/brand/logo-obsidian.svg` (Default dark surface mark: vanilla mark, gold arcs)
  - `static/brand/logo-light-tile.svg` (Light surface mark: ink mark, dark gold arcs)
  - `static/brand/logo-mono-dot.svg` (Standard brand mark asset)
  - `static/brand/logo-urgent.svg` (Urgent state with #EF4444 broadcast arcs)
  - `static/brand/favicon-16.svg` & `static/brand/favicon-32.svg` (Compact cut favicons: 2 thicker arcs for 16px, 3 arcs for 32px)
  - `static/favicon.svg` (Dark/light mode preference-aware root favicon)
  - `static/brand/logo-lockup-dark.svg` & `static/brand/logo-lockup-light.svg` (Horizontal lockups with outlined typography and "DIGITAL NOTICE BOARD" descriptor)
  - `static/brand/logo-lockup-stacked-dark.svg` & `static/brand/logo-lockup-stacked-light.svg` (Stacked lockups with outlined typography and descriptor)
  - `static/favicon.ico` (Multi-resolution 16, 32, 48 from simplified compact cut)
  - `static/apple-touch-icon.png` (180×180 iOS home screen bookmark with compact mark)
  - `static/icons/icon-192.png`, `static/icons/icon-512.png` (PWA compact icons)
  - `static/icons/icon-192-maskable.png`, `static/icons/icon-512-maskable.png` (Full-bleed `#131210` with compact mark in central 80% safe zone)
  - `static/brand/og-image.png` (1200×630 Open Graph preview: dark warm `#131210` background, centered lockup with descriptor)
  - `static/brand/contact-sheet.png` (Verification contact sheet across 16, 24, 32, 48, 64, 180px on Light, Dark, and #131210 surfaces for Full Mark and Compact Cut in Normal & Urgent states)

---

## 2. Display Hierarchy (display.html Kiosk)

1. **The Hero Stage (`.stage-panel`):**
   - Elevated with a subtle radial gradient glow (`radial-gradient(120% 120% at 20% 10%, rgba(30, 58, 138, 0.22) 0%, #141F36 70%)`), 1px inner interactive border (`--border-interactive: rgba(59, 130, 246, 0.35)`), and deep stage drop shadow (`--shadow-stage: 0 16px 48px -8px rgba(0, 0, 0, 0.65)`).
   - Dynamic ambient perimeter glow transitions across 350ms based on active notice priority (`.glow-urgent` crimson `#E5484D`, `.glow-info` blue `#2F6BFF`).
2. **Text-Only Slides Never Empty:**
   - Headlines fill the stage using viewport scaling: `clamp(3rem, 6vw, 7rem)` with a 6px accent bar (`--blue: #2F6BFF`).
   - Body copy scaled to `clamp(1.5rem, 2.4vw, 2.5rem)` in `--text-secondary-bright` (`#CBD5E1`).
   - Deterministic backdrop gradient cycle computed from notice ID:
     - `theme-deep-blue`: `radial-gradient(circle at 10% 20%, #172554 0%, #0F172A 100%)`
     - `theme-indigo`: `radial-gradient(circle at 10% 20%, #1E1B4B 0%, #0F172A 100%)`
     - `theme-teal`: `radial-gradient(circle at 10% 20%, #042F2E 0%, #0F172A 100%)`
     - `theme-slate`: `radial-gradient(circle at 10% 20%, #1E293B 0%, #0A0F1D 100%)`
3. **Unambiguous Counters & Progressive Rail:**
   - Stage corner indicator: `Now showing 1 of 5`.
   - Rail header pill: `Up next` with badge pill `4`. Rail sequence begins from the immediate next notice and wraps cyclically (`#2`, `#3`, `#4`, etc.).
   - `+ N more in rotation` upgraded to 20px minimum size in `--muted` with an icon prefix.
4. **Rotation Progress Dots:**
   - Inactive dots: 8px circular dots with 40% white opacity (`rgba(255, 255, 255, 0.4)`).
   - Active dot: 34px pill with a linear duration progress fill (`.dot-progress-fill`) matching the active slide display duration (`duration * 1000ms`). Falls back to solid white under `prefers-reduced-motion`.
5. **Decoupled QR Card:**
   - Receded secondary card (`#0E1626`) at bottom of rail with a dedicated, scan-reliable `#FFFFFF` canvas. "Camera / Scanner" lightning pill removed for visual cleanliness.
6. **Smooth Edge-Masked Ticker:**
   - CSS mask-image linear gradients on left (0–48px) and right (calc(100%-48px)–100%) prevent text from clipping abruptly at viewport edges. Ticker motion pauses automatically under `prefers-reduced-motion`.
7. **Aligned Header & Live Sync Indicator:**
   - Weather widget, clock, and date align to a single baseline.
   - Thin 6px indicator dot next to the clock displays amber (`#F59E0B`) during healthy active sync and muted slate (`#64748B`) when offline/reconnecting.

---

## 3. Admin Visuals & Semantic Design (admin.html)

1. **Header Toolbar:**
   - 44px minimum touch targets across all toolbar elements.
   - Distinct labeled `Audit Logs` button with shield icon + tooltip, grouped alongside the circular `Refresh` button.
2. **Explicit Status & Priority Semantics:**
   - Color is **never** the sole communication channel; every badge pairs a color with explicit text:
     - **Status:** `Live` (Emerald `#10B981` dot + `#34D399` label), `Scheduled` (Amber `#F59E0B` dot + `#FBBF24` label), `Expired` (Slate `#64748B` dot + `#94A3B8` label).
     - **Priority:** Separate badge pill: `Urgent` (Crimson `#F87171` pill), `Info` (Blue `#60A5FA` pill), `Normal` (Slate `#94A3B8` pill).
3. **Notice Card Anatomy:**
   - **Thumbnail (left):**
     - Video cards: First frame poster rendered client-side via `<video>` + `<canvas>` with an overlaid play badge (`▶`).
     - Image cards: Clean rounded aspect-fill thumbnail.
     - Text cards: Curated gradient tile displaying the bold initial letter in **Outfit**.
   - **Body (middle):** Title, single-line truncated snippet, separate status/priority badges row, and schedule row with relative end duration (`ends in 3 days` / `ended 2d ago`). Year is displayed only when differing from current calendar year.
   - **Actions (right):** 44px hit targets with 12px separation between Edit and Delete. Delete is styled as destructive with red hover state (`#F87171`).
4. **Illustrated Per-Tab Empty States:**
   - Custom SVG illustration and helper text for each filter tab (`All`, `Live`, `Scheduled`, `Expired`), with primary "Create Notice" CTA on `All`.
5. **Typo Hardening:**
   - Replaced all instances of `"Alumini"` with `"Alumni"` across database records, mock fixtures, and seed data.

---

## 4. Typography Scale & Weight Labels

* **Outfit (Primary Brand & Display Headlines):**
  - `400 Regular`
  - `600 SemiBold`
  - `700 Bold`
  - `800 ExtraBold`
* **Inter (Interface & Body Text):**
  - `400 Regular`
  - `500 Medium`
  - `600 SemiBold`
  - `700 Bold`

---

## 5. WCAG 2.1 Contrast Ratios Audit (Real Measured Values)

Contrast ratios measured via relative luminance formula ($L_1 + 0.05) / (L_2 + 0.05)$:

| Element Pair | Foreground | Background | Measured Ratio | WCAG 2.1 Status |
| :--- | :--- | :--- | :---: | :---: |
| **Primary Headline** on Stage Surface | `#FFFFFF` | `#141F36` | **16.42:1** | **AAA** (Exceeds 7.0:1) |
| **Primary Headline** on Canvas Base | `#FFFFFF` | `#0F172A` | **17.85:1** | **AAA** (Exceeds 7.0:1) |
| **Headline** on Theme Deep Blue | `#FFFFFF` | `#0F172A` | **17.85:1** | **AAA** (Exceeds 7.0:1) |
| **Headline** on Theme Indigo | `#FFFFFF` | `#1E1B4B` | **15.99:1** | **AAA** (Exceeds 7.0:1) |
| **Headline** on Theme Teal | `#FFFFFF` | `#042F2E` | **14.47:1** | **AAA** (Exceeds 7.0:1) |
| **Headline** on Theme Slate | `#FFFFFF` | `#1E293B` | **14.63:1** | **AAA** (Exceeds 7.0:1) |
| **Secondary Text** on Stage Surface | `#CBD5E1` | `#141F36` | **11.06:1** | **AAA** (Exceeds 7.0:1) |
| **Secondary Text** on Canvas Base | `#CBD5E1` | `#0F172A` | **12.02:1** | **AAA** (Exceeds 7.0:1) |
| **Muted Text** on Canvas Base | `#94A3B8` | `#0F172A` | **6.96:1** | **AA** (Exceeds 4.5:1) |
| **Muted Secondary** on Canvas Base | `#A3B1C6` | `#0F172A` | **8.21:1** | **AAA** (Exceeds 7.0:1) |
| **Live Status Text** on Badge Surface | `#34D399` | `#162238` (blended) | **6.52:1** | **AA** (Exceeds 4.5:1) |
| **Urgent Status Text** on Badge Surface | `#F87171` | `#162238` (blended) | **4.89:1** | **AA** (Exceeds 4.5:1) |
| **Info Status Text** on Badge Surface | `#60A5FA` | `#162238` (blended) | **5.39:1** | **AA** (Exceeds 4.5:1) |
| **Normal Status Text** on Badge Surface | `#CBD5E1` | `#162238` (blended) | **8.79:1** | **AAA** (Exceeds 7.0:1) |

All body and primary text pairs easily surpass the **7:1 AAA** threshold, and all status badges exceed the **4.5:1 AA** standard without relying solely on color.
