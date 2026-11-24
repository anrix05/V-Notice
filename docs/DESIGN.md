# V Notice — Design System & UI/UX Architecture

**Document Version:** 2.1.0  
**Status:** Living Design Specification  
**Product:** V Notice (Smart Campus Digital Notice Board & Kiosk)  
**Last Updated:** October 11, 2026  

---

## 1. Brand Identity & Geometric Vector Mark

The official V Notice mark features a bold geometric **"V" made of one rounded stroke with two gold signal arcs at the upper right** (`viewBox="44 20 134 132"`):

* **Mark Geometry & Paths:**
  - *V path:* `<path d="M64 70 L96 132 L128 70" fill="none" stroke="var(--logo-v)" stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>`
  - *Inner Arc:* `<path d="M133.7 48.8 A22 22 0 0 1 149.2 64.3" fill="none" stroke="var(--logo-arcs)" stroke-width="9" stroke-linecap="round"/>`
  - *Outer Arc:* `<path d="M137.8 33.3 A38 38 0 0 1 164.7 60.2" fill="none" stroke="var(--logo-arcs)" stroke-width="9" stroke-linecap="round"/>`
  - *Tile version for icons (`viewBox="0 0 200 200"`):* `<rect width="200" height="200" rx="44" fill="#131210"/>` behind the same paths.
* **Brand Color Palette:**
  - *Vanilla:* `#EEEBDA` (Primary mark stroke `--logo-v` on dark surfaces: kiosk, dark admin, dark public notice)
  - *Ink:* `#131210` (Primary mark stroke `--logo-v` on light surfaces: light admin, light public page)
  - *Gold:* `#B08D57` (Signal arcs `--logo-arcs` on dark surfaces; 6.06:1 contrast ratio > 4.5:1 WCAG AA)
  - *Darker Gold:* `#8A6B3A` (Signal arcs `--logo-arcs` on light surfaces; 4.39:1 contrast ratio > 3:1 WCAG AA on vanilla `#F5F1E8`)
  - *Urgent Red:* `#EF4444` (Signal arcs takeover in urgent broadcast state)
* **Surface Rules & Theme Variables:**
  - *Dark Surfaces (Kiosk, Dark Admin):* `--logo-v: #EEEBDA`, `--logo-arcs: #B08D57`.
  - *Light Surfaces (Light Admin, Light Public Page):* `--logo-v: #131210`, `--logo-arcs: #8A6B3A`.
  - Driven by CSS custom properties with backward-compatible aliases:
    - `--logo-v`: `#EEEBDA` (dark) / `#131210` (light)
    - `--logo-arcs`: `#B08D57` (dark) / `#8A6B3A` (light)
    - Backward-compatible aliases: `--logo-mark: var(--logo-v)`, `--logo-accent: var(--logo-arcs)`
* **Typography & Lockups:**
  - *Wordmark "V Notice":* Outfit 600 (SemiBold) for clean geometric optical balance. Letter-spacing `-0.01em`, same color as the V, vertically centered on mark center line across lockups.
  - *Descriptor "DIGITAL NOTICE BOARD":* Inter 500 (Medium), uppercase, letter-spacing `0.25em`, muted. Left edge aligned flush with the left edge of "V" in wordmark.
  - *Visibility Rule:* Appears ONLY in lockup files and Open Graph image. Never in kiosk header, admin header, public page header, or favicons.
  - *Outlines:* Final lockup SVGs convert text to `<path>` outlines, accompanied by editable-text comment fallbacks specifying font families, sizes, and tracking.
* **Compact Cut for Tiny Sizes:**
  - For 16px and 32px resolutions, a compact cut is used: thicker V (stroke 30), only the inner arc (stroke 11), and no fine details so it stays crisp and readable.
  - Used for `favicon-16.svg`, `favicon-32.svg`, `favicon.ico` (16, 32, 48), `apple-touch-icon.png` (180), `icon-192.png`, `icon-512.png`, and maskable icons (full-bleed `#131210` background with mark inside central 80% safe zone).
* **Special States & Animation:**
  - *Urgent Broadcast Takeover:* The signal arcs turn `#EF4444`.
  - *Kiosk-Only Pulse:* A subtle 2.4s brightness pulse on the signal arcs only on the kiosk header, automatically disabled under `@media (prefers-reduced-motion: reduce)`.
  - *Admin Portal & Public Notice:* Zero animation.
* **Asset Catalog:**
  - `static/brand/logo-obsidian.svg` (Default dark surface mark: vanilla V, gold arcs)
  - `static/brand/logo-light-tile.svg` (Light surface mark: ink V, dark gold arcs)
  - `static/brand/logo-mono-dot.svg` (Standard brand mark asset)
  - `static/brand/logo-urgent.svg` (Urgent state with #EF4444 signal arcs)
  - `static/brand/favicon-16.svg` & `static/brand/favicon-32.svg` (Compact cut favicons: thicker V, single inner arc)
  - `static/favicon.svg` (Root favicon tile)
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
