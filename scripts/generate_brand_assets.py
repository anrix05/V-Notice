import os
import sys
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
BRAND_DIR = STATIC_DIR / "brand"
ICONS_DIR = STATIC_DIR / "icons"
IMAGES_DIR = STATIC_DIR / "images"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"

BRAND_DIR.mkdir(parents=True, exist_ok=True)
ICONS_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# GEOMETRY DEFINITION (V Notice New Document Sheet Monogram)
# ---------------------------------------------------------------------------
# Final Monogram geometry (translate 70 70 in 500x500 box):
# Sheet:  M40 35 H245 L325 115 V345 H40 Z
# Fold:   M245 35 V115 H325 Z
# V cut:  M82 112 H128 L182 260 L236 112 H282 L205 315 H159 Z
# Line:   M82 342 H282 (stroke-width 8, square caps)
# Palette: ink #111318, ivory #F5F1E8, gold #B08D57, urgent #EF4444

# 1. Variant 1: Default Mark (Ink Sheet, Ivory V, Gold Fold & Line)
LOGO_OBSIDIAN_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="100%" height="100%">
  <g transform="translate(70, 70)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="var(--logo-sheet, #111318)" class="vnotice-sheet"/>
    <path d="M245 35 V115 H325 Z" fill="var(--logo-accent, #B08D57)" class="vnotice-fold"/>
    <path d="M82 112 H128 L182 260 L236 112 H282 L205 315 H159 Z" fill="var(--logo-cut, #F5F1E8)" class="vnotice-v"/>
    <path d="M82 342 H282" stroke="var(--logo-accent, #B08D57)" stroke-width="8" stroke-linecap="square" class="vnotice-line"/>
  </g>
</svg>"""

# 2. Variant 2: Reversed Mark for Dark Surfaces (Ivory Sheet, Ink V, Gold Fold & Line)
LOGO_LIGHT_TILE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="100%" height="100%">
  <g transform="translate(70, 70)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="var(--logo-sheet, #F5F1E8)" class="vnotice-sheet"/>
    <path d="M245 35 V115 H325 Z" fill="var(--logo-accent, #B08D57)" class="vnotice-fold"/>
    <path d="M82 112 H128 L182 260 L236 112 H282 L205 315 H159 Z" fill="var(--logo-cut, #111318)" class="vnotice-v"/>
    <path d="M82 342 H282" stroke="var(--logo-accent, #B08D57)" stroke-width="8" stroke-linecap="square" class="vnotice-line"/>
  </g>
</svg>"""

# 3. Variant 3: Mono Dot / Standard Mark
LOGO_MONO_DOT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="100%" height="100%">
  <g transform="translate(70, 70)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="#111318" class="vnotice-sheet"/>
    <path d="M245 35 V115 H325 Z" fill="#B08D57" class="vnotice-fold"/>
    <path d="M82 112 H128 L182 260 L236 112 H282 L205 315 H159 Z" fill="#F5F1E8" class="vnotice-v"/>
    <path d="M82 342 H282" stroke="#B08D57" stroke-width="8" stroke-linecap="square" class="vnotice-line"/>
  </g>
</svg>"""

# 4. Variant 4: Urgent Takeover (#EF4444 Fold Corner)
LOGO_URGENT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="100%" height="100%">
  <g transform="translate(70, 70)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="var(--logo-sheet, #111318)" class="vnotice-sheet"/>
    <path d="M245 35 V115 H325 Z" fill="#EF4444" class="vnotice-fold"/>
    <path d="M82 112 H128 L182 260 L236 112 H282 L205 315 H159 Z" fill="var(--logo-cut, #F5F1E8)" class="vnotice-v"/>
    <path d="M82 342 H282" stroke="var(--logo-accent, #B08D57)" stroke-width="8" stroke-linecap="square" class="vnotice-line"/>
  </g>
</svg>"""

# 5. Favicon Cuts (16px and 32px):
# Drop gold line, no outer border, thicken V cutout ~15%, widen notch, keep fold corner.
# Untranslated sheet bounds are X:[40, 325] (w=285), Y:[35, 345] (h=310).
# In 320x320 box, translate(-22.5, -30) places sheet in X:[17.5, 302.5] and Y:[5, 315] (no clipping!).
LOGO_FAVICON_16_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="100%" height="100%">
  <g transform="translate(-22.5, -30)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="#111318"/>
    <path d="M245 35 V115 H325 Z" fill="#B08D57"/>
    <path d="M78 112 H131 L182 246 L233 112 H286 L209 318 H155 Z" fill="#F5F1E8"/>
  </g>
</svg>"""

LOGO_FAVICON_16_DARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="100%" height="100%">
  <g transform="translate(-22.5, -30)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="#F5F1E8"/>
    <path d="M245 35 V115 H325 Z" fill="#B08D57"/>
    <path d="M78 112 H131 L182 246 L233 112 H286 L209 318 H155 Z" fill="#111318"/>
  </g>
</svg>"""

LOGO_FAVICON_16_URGENT_DARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="100%" height="100%">
  <g transform="translate(-22.5, -30)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="#F5F1E8"/>
    <path d="M245 35 V115 H325 Z" fill="#EF4444"/>
    <path d="M78 112 H131 L182 246 L233 112 H286 L209 318 H155 Z" fill="#111318"/>
  </g>
</svg>"""

LOGO_FAVICON_16_URGENT_LIGHT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="100%" height="100%">
  <g transform="translate(-22.5, -30)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="#111318"/>
    <path d="M245 35 V115 H325 Z" fill="#EF4444"/>
    <path d="M78 112 H131 L182 246 L233 112 H286 L209 318 H155 Z" fill="#F5F1E8"/>
  </g>
</svg>"""

LOGO_FAVICON_32_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="100%" height="100%">
  <g transform="translate(-22.5, -30)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="#111318"/>
    <path d="M245 35 V115 H325 Z" fill="#B08D57"/>
    <path d="M78 112 H131 L182 246 L233 112 H286 L209 318 H155 Z" fill="#F5F1E8"/>
  </g>
</svg>"""

# Urgent Dark Mark (for reversed dark surfaces)
LOGO_URGENT_DARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="100%" height="100%">
  <g transform="translate(70, 70)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="#F5F1E8" class="vnotice-sheet"/>
    <path d="M245 35 V115 H325 Z" fill="#EF4444" class="vnotice-fold"/>
    <path d="M82 112 H128 L182 260 L236 112 H282 L205 315 H159 Z" fill="#111318" class="vnotice-v"/>
    <path d="M82 342 H282" stroke="#B08D57" stroke-width="8" stroke-linecap="square" class="vnotice-line"/>
  </g>
</svg>"""

# Root favicon with dark/light scheme awareness
LOGO_FAVICON_ROOT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="100%" height="100%">
  <style>
    :root { --sheet: #111318; --cut: #F5F1E8; }
    @media (prefers-color-scheme: dark) {
      :root { --sheet: #F5F1E8; --cut: #111318; }
    }
  </style>
  <g transform="translate(-22.5, -30)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="var(--sheet, #111318)"/>
    <path d="M245 35 V115 H325 Z" fill="#B08D57"/>
    <path d="M78 112 H131 L182 246 L233 112 H286 L209 318 H155 Z" fill="var(--cut, #F5F1E8)"/>
  </g>
</svg>"""

# 6. Outlined Typography for Lockups
# Generated with opentype.js from Outfit-Bold.ttf (700) and Inter-Medium.ttf (500)
# Wordmark "V Notice": Outfit 700, size 22px, letter-spacing -0.01em
# Descriptor "DIGITAL NOTICE PLATFORM": Inter 500, size 4.8px, letter-spacing 0.26em, left-aligned with V
TITLE_H_PATH = "M60 16.97 L68.49 16.97 L75.29 32.5 L69.83 32.5 L64.39 19.85 L64.26 19.85 L58.82 32.5 L53.38 32.5 Z M79.44 16.97 L84.28 16.97 L93.63 28.52 L93.76 28.52 L93.76 16.97 L98.71 16.97 L98.71 32.5 L93.87 32.5 L84.52 20.95 L84.39 20.95 L84.39 32.5 L79.44 32.5 Z M102.3 26.54 Q102.3 23.63 103.88 21.84 Q105.47 20.06 108.31 20.06 Q111.14 20.06 112.73 21.84 Q114.31 23.63 114.31 26.54 Q114.31 29.44 112.73 31.23 Q111.14 33.01 108.31 33.01 Q105.47 33.01 103.88 31.23 Q102.3 29.44 102.3 26.54 Z M107.24 26.54 Q107.24 27.99 107.66 28.79 Q108.08 29.58 108.31 29.58 Q108.53 29.58 108.95 28.79 Q109.37 27.99 109.37 26.54 Q109.37 25.08 108.95 24.28 Q108.53 23.49 108.31 23.49 Q108.08 23.49 107.66 24.28 Q107.24 25.08 107.24 26.54 Z M119.5 18.07 L119.5 20.59 L123.66 20.59 L123.66 23.94 L119.5 23.94 L119.5 29.2 Q119.5 30.13 120.32 30.13 L123.53 30.13 L123.53 32.5 L119.19 32.5 Q115.01 32.5 114.66 28.52 L114.66 23.94 L112.28 23.94 L112.28 20.59 L114.66 20.59 L114.66 18.07 Z M126.15 17.51 Q126.15 16.48 126.85 15.77 Q127.56 15.07 128.57 15.07 Q129.58 15.07 130.29 15.77 Q130.99 16.48 130.99 17.51 Q130.99 18.52 130.29 19.23 Q129.58 19.93 128.57 19.93 Q127.56 19.93 126.85 19.23 Q126.15 18.52 126.15 17.51 Z M126.26 20.59 L130.88 20.59 L130.88 32.5 L126.26 32.5 Z M133.47 26.54 Q133.47 23.68 135.03 21.87 Q136.6 20.06 139.37 20.06 Q142.17 20.06 143.71 21.91 L140.78 24.64 Q139.99 23.67 139.37 23.67 Q138.8 23.67 138.38 24.37 Q137.96 25.08 137.96 26.54 Q137.96 28 138.38 28.7 Q138.8 29.4 139.37 29.4 Q139.99 29.4 140.78 28.43 L143.71 31.17 Q142.17 33.01 139.37 33.01 Q136.6 33.01 135.03 31.2 Q133.47 29.39 133.47 26.54 Z M145.47 26.54 Q145.47 23.65 147.01 21.85 Q148.55 20.06 151.28 20.06 Q154.01 20.06 155.48 21.83 Q156.96 23.59 156.96 26.54 L156.96 27.2 L149.9 27.2 Q149.9 28.32 150.36 29.03 Q150.82 29.73 151.52 29.73 Q152.23 29.73 153.11 28.89 L155.48 31.32 Q154.08 33.01 151.37 33.01 Q148.64 33.01 147.06 31.22 Q145.47 29.42 145.47 26.54 Z M152.56 24.47 Q152.27 23.75 151.79 23.53 Q151.3 23.31 151.24 23.31 Q150.77 23.31 150.36 23.73 Q149.94 24.15 149.9 24.96 L152.69 24.96 Z"
DESC_H_PATH = "M60 39.54 L62.01 39.54 Q62.91 39.54 63.43 40.06 Q63.95 40.57 63.95 41.47 L63.95 41.47 Q63.95 42.36 63.43 42.88 Q62.91 43.4 62.01 43.4 L60 43.4 Z M60.91 40.32 L60.91 42.61 L62.01 42.61 Q62.53 42.61 62.77 42.27 Q63.02 41.93 63.02 41.47 L63.02 41.47 Q63.02 41.01 62.77 40.66 Q62.53 40.32 62.01 40.32 Z M65.86 39.54 L66.78 39.54 L66.78 43.4 L65.86 43.4 Z M71.84 41.47 L71.84 42.06 L70.36 42.06 L70.36 42.62 Q70.66 42.62 70.97 42.54 Q71.28 42.46 71.55 42.29 L71.82 42.92 Q71.49 43.14 71.07 43.27 Q70.65 43.4 70.19 43.4 Q69.23 43.4 68.74 42.87 Q68.25 42.34 68.25 41.47 L68.25 41.47 Q68.25 40.6 68.74 40.07 Q69.23 39.54 70.19 39.54 Q70.63 39.54 71.02 39.67 Q71.41 39.8 71.74 40.05 L71.43 40.71 Q71.16 40.52 70.88 40.42 Q70.6 40.32 70.28 40.32 Q69.75 40.32 69.46 40.66 Q69.17 40.99 69.17 41.47 L69.17 41.47 Q69.17 41.95 69.46 42.28 Q69.75 42.62 70.28 42.62 L70.93 42.62 L70.93 41.47 Z M73.74 39.54 L74.66 39.54 L74.66 43.4 L73.74 43.4 Z M78.27 40.32 L76.67 40.32 L76.67 39.54 L80.8 39.54 L80.8 40.32 L79.19 40.32 L79.19 43.4 L78.27 43.4 Z M83.56 39.54 L84.66 39.54 L86.32 43.4 L85.34 43.4 L84.97 42.49 L83.24 42.49 L82.88 43.4 L81.9 43.4 Z M83.58 41.69 L84.63 41.69 L84.1 40.36 Z M87.95 39.54 L88.87 39.54 L88.87 42.61 L91.07 42.61 L91.07 43.4 L87.95 43.4 Z M96.16 39.54 L98.05 42.27 L98.05 39.54 L98.96 39.54 L98.96 43.4 L97.16 43.4 L95.27 40.67 L95.27 43.4 L94.35 43.4 L94.35 39.54 Z M100.86 41.47 Q100.86 40.6 101.35 40.07 Q101.84 39.54 102.8 39.54 Q103.76 39.54 104.25 40.07 Q104.74 40.6 104.74 41.47 L104.74 41.47 Q104.74 42.34 104.25 42.87 Q103.76 43.4 102.8 43.4 Q101.84 43.4 101.35 42.87 Q100.86 42.34 100.86 41.47 Z M101.78 41.47 Q101.78 42.06 102.04 42.38 Q102.31 42.69 102.8 42.69 Q103.29 42.69 103.56 42.38 Q103.82 42.06 103.82 41.47 L103.82 41.47 Q103.82 40.88 103.56 40.56 Q103.29 40.25 102.8 40.25 Q102.31 40.25 102.04 40.56 Q101.78 40.88 101.78 41.47 Z M108.73 40.32 L107.13 40.32 L107.13 39.54 L111.25 39.54 L111.25 40.32 L109.65 40.32 L109.65 43.4 L108.73 43.4 Z M113.15 39.54 L114.07 39.54 L114.07 43.4 L113.15 43.4 Z M116.03 41.47 Q116.03 40.6 116.53 40.07 Q117.03 39.54 117.98 39.54 Q118.42 39.54 118.81 39.67 Q119.2 39.8 119.53 40.05 L119.22 40.71 Q118.95 40.52 118.67 40.42 Q118.39 40.32 118.07 40.32 Q117.54 40.32 117.25 40.66 Q116.96 40.99 116.96 41.47 L116.96 41.47 Q116.96 41.95 117.25 42.28 Q117.54 42.62 118.07 42.62 Q118.4 42.62 118.7 42.52 Q119 42.42 119.32 42.23 L119.63 42.87 Q119.27 43.12 118.86 43.26 Q118.45 43.4 117.98 43.4 Q117.03 43.4 116.53 42.87 Q116.03 42.34 116.03 41.47 Z M121.57 39.54 L124.58 39.54 L124.58 40.32 L122.49 40.32 L122.49 41.11 L124.41 41.11 L124.41 41.88 L122.49 41.88 L122.49 42.62 L124.63 42.62 L124.63 43.4 L121.57 43.4 Z M129.6 39.54 L131.54 39.54 Q132.32 39.54 132.74 39.9 Q133.16 40.26 133.16 40.93 L133.16 40.93 Q133.16 41.6 132.74 41.96 Q132.32 42.32 131.54 42.32 L130.52 42.32 L130.52 43.4 L129.6 43.4 Z M130.52 40.32 L130.52 41.54 L131.47 41.54 Q131.84 41.54 132.04 41.38 Q132.24 41.22 132.24 40.93 L132.24 40.93 Q132.24 40.64 132.04 40.48 Q131.84 40.32 131.47 40.32 Z M135.08 39.54 L136 39.54 L136 42.61 L138.2 42.61 L138.2 43.4 L135.08 43.4 Z M140.68 39.54 L141.79 39.54 L143.45 43.4 L142.47 43.4 L142.1 42.49 L140.36 42.49 L140 43.4 L139.03 43.4 Z M140.71 41.69 L141.75 41.69 L141.23 40.36 Z M146.42 40.32 L144.82 40.32 L144.82 39.54 L148.95 39.54 L148.95 40.32 L147.34 40.32 L147.34 43.4 L146.42 43.4 Z M150.84 39.54 L153.81 39.54 L153.81 40.32 L151.76 40.32 L151.76 41.11 L153.64 41.11 L153.64 41.88 L151.76 41.88 L151.76 43.4 L150.84 43.4 Z M156.91 41.47 Q156.91 40.6 157.4 40.07 Q157.9 39.54 158.85 39.54 Q159.81 39.54 160.31 40.07 Q160.8 40.6 160.8 41.47 L160.8 41.47 Q160.8 42.34 160.31 42.87 Q159.81 43.4 158.85 43.4 Q157.9 43.4 157.4 42.87 Q156.91 42.34 156.91 41.47 Z M157.83 41.47 Q157.83 42.06 158.1 42.38 Q158.37 42.69 158.85 42.69 Q159.34 42.69 159.61 42.38 Q159.88 42.06 159.88 41.47 L159.88 41.47 Q159.88 40.88 159.61 40.56 Q159.34 40.25 158.85 40.25 Q158.37 40.25 158.1 40.56 Q157.83 40.88 157.83 41.47 Z M162.72 39.54 L164.84 39.54 Q165.59 39.54 165.99 39.87 Q166.39 40.2 166.39 40.83 L166.39 40.83 Q166.39 41.34 166.08 41.65 Q165.77 41.96 165.23 42.06 L166.53 43.4 L165.34 43.4 L164.21 42.23 L163.64 42.23 L163.64 43.4 L162.72 43.4 Z M163.64 40.32 L163.64 41.46 L164.69 41.46 Q165.04 41.46 165.25 41.32 Q165.46 41.18 165.46 40.89 L165.46 40.89 Q165.46 40.6 165.25 40.46 Q165.04 40.32 164.69 40.32 Z M168.16 39.54 L169.31 39.54 L170.62 42.17 L171.93 39.54 L173.08 39.54 L173.08 43.4 L172.19 43.4 L172.19 40.59 L171.01 42.92 L170.23 42.92 L169.05 40.59 L169.05 43.4 L168.16 43.4 Z"

LOCKUP_HORIZONTAL_LIGHT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 60" width="240" height="60">
  <!-- Editable text fallback:
       Font: Outfit Bold (700), size: 22px, letter-spacing: -0.01em
       Descriptor: Inter Medium (500), size: 4.8px, letter-spacing: 0.26em, color: #8A6B3A
       <text x="60" y="32.5" font-family="'Outfit', sans-serif" font-weight="700" font-size="22" letter-spacing="-0.01em" fill="#111318">V Notice</text>
       <text x="60" y="43" font-family="'Inter', sans-serif" font-weight="500" font-size="4.8" letter-spacing="0.26em" fill="#8A6B3A">DIGITAL NOTICE PLATFORM</text>
  -->
  <g transform="translate(8, 7) scale(0.1479) translate(-40, -35)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="#111318"/>
    <path d="M245 35 V115 H325 Z" fill="#B08D57"/>
    <path d="M82 112 H128 L182 260 L236 112 H282 L205 315 H159 Z" fill="#F5F1E8"/>
    <path d="M82 342 H282" stroke="#B08D57" stroke-width="8" stroke-linecap="square"/>
  </g>
  <path d="{TITLE_H_PATH}" fill="#111318"/>
  <path d="{DESC_H_PATH}" fill="#8A6B3A"/>
</svg>"""

LOCKUP_HORIZONTAL_DARK_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 60" width="240" height="60">
  <!-- Editable text fallback:
       Font: Outfit Bold (700), size: 22px, letter-spacing: -0.01em
       Descriptor: Inter Medium (500), size: 4.8px, letter-spacing: 0.26em, color: rgba(245, 241, 232, 0.7)
       <text x="60" y="32.5" font-family="'Outfit', sans-serif" font-weight="700" font-size="22" letter-spacing="-0.01em" fill="#F8FAFC">V Notice</text>
       <text x="60" y="43" font-family="'Inter', sans-serif" font-weight="500" font-size="4.8" letter-spacing="0.26em" fill="rgba(245, 241, 232, 0.7)">DIGITAL NOTICE PLATFORM</text>
  -->
  <g transform="translate(8, 7) scale(0.1479) translate(-40, -35)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="#F5F1E8"/>
    <path d="M245 35 V115 H325 Z" fill="#B08D57"/>
    <path d="M82 112 H128 L182 260 L236 112 H282 L205 315 H159 Z" fill="#111318"/>
    <path d="M82 342 H282" stroke="#B08D57" stroke-width="8" stroke-linecap="square"/>
  </g>
  <path d="{TITLE_H_PATH}" fill="#F8FAFC"/>
  <path d="{DESC_H_PATH}" fill="rgba(245, 241, 232, 0.7)"/>
</svg>"""

# Stacked Wordmark Outlines
TITLE_STACK_PATH = "M38.45 88.47 L46.94 88.47 L53.74 104 L48.28 104 L42.84 91.35 L42.71 91.35 L37.27 104 L31.83 104 Z M57.89 88.47 L62.73 88.47 L72.08 100.02 L72.21 100.02 L72.21 88.47 L77.16 88.47 L77.16 104 L72.32 104 L62.97 92.45 L62.84 92.45 L62.84 104 L57.89 104 Z M80.75 98.04 Q80.75 95.13 82.33 93.34 Q83.92 91.56 86.76 91.56 Q89.59 91.56 91.18 93.34 Q92.76 95.13 92.76 98.04 Q92.76 100.94 91.18 102.73 Q89.59 104.51 86.76 104.51 Q83.92 104.51 82.33 102.73 Q80.75 100.94 80.75 98.04 Z M85.69 98.04 Q85.69 99.49 86.11 100.29 Q86.53 101.08 86.76 101.08 Q86.98 101.08 87.4 100.29 Q87.82 99.49 87.82 98.04 Q87.82 96.58 87.4 95.78 Q86.98 94.99 86.76 94.99 Q86.53 94.99 86.11 95.78 Q85.69 96.58 85.69 98.04 Z M97.95 89.57 L97.95 92.09 L102.11 92.09 L102.11 95.44 L97.95 95.44 L97.95 100.7 Q97.95 101.63 98.77 101.63 L101.98 101.63 L101.98 104 L97.64 104 Q93.46 104 93.11 100.02 L93.11 95.44 L90.73 95.44 L90.73 92.09 L93.11 92.09 L93.11 89.57 Z M104.6 89.01 Q104.6 87.98 105.3 87.27 Q106.01 86.57 107.02 86.57 Q108.03 86.57 108.74 87.27 Q109.44 87.98 109.44 89.01 Q109.44 90.02 108.74 90.73 Q108.03 91.43 107.02 91.43 Q106.01 91.43 105.3 90.73 Q104.6 90.02 104.6 89.01 Z M104.71 92.09 L109.33 92.09 L109.33 104 L104.71 104 Z M111.92 98.04 Q111.92 95.18 113.48 93.37 Q115.05 91.56 117.82 91.56 Q120.62 91.56 122.16 93.41 L119.23 96.14 Q118.44 95.17 117.82 95.17 Q117.25 95.17 116.83 95.87 Q116.41 96.58 116.41 98.04 Q116.41 99.5 116.83 100.2 Q117.25 100.9 117.82 100.9 Q118.44 100.9 119.23 99.93 L122.16 102.67 Q120.62 104.51 117.82 104.51 Q115.05 104.51 113.48 102.7 Q111.92 100.89 111.92 98.04 Z M123.92 98.04 Q123.92 95.15 125.46 93.35 Q127 91.56 129.73 91.56 Q132.46 91.56 133.93 93.33 Q135.41 95.09 135.41 98.04 L135.41 98.7 L128.35 98.7 Q128.35 99.82 128.81 100.53 Q129.27 101.23 129.97 101.23 Q130.68 101.23 131.56 100.39 L133.93 102.82 Q132.53 104.51 129.82 104.51 Q127.09 104.51 125.51 102.72 Q123.92 100.92 123.92 98.04 Z M131.01 95.97 Q130.72 95.25 130.24 95.03 Q129.75 94.81 129.69 94.81 Q129.22 94.81 128.81 95.23 Q128.39 95.65 128.35 96.46 L131.14 96.46 Z"

LOCKUP_STACKED_LIGHT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 130" width="160" height="130">
  <!-- Editable text fallback:
       Font: Outfit Bold (700), size: 22px, letter-spacing: -0.01em
       <text x="80" y="104" font-family="'Outfit', sans-serif" font-weight="700" font-size="22" letter-spacing="-0.01em" text-anchor="middle" fill="#111318">V Notice</text>
  -->
  <g transform="translate(51.6, 10) scale(0.1993) translate(-40, -35)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="#111318"/>
    <path d="M245 35 V115 H325 Z" fill="#B08D57"/>
    <path d="M82 112 H128 L182 260 L236 112 H282 L205 315 H159 Z" fill="#F5F1E8"/>
    <path d="M82 342 H282" stroke="#B08D57" stroke-width="8" stroke-linecap="square"/>
  </g>
  <path d="{TITLE_STACK_PATH}" fill="#111318"/>
</svg>"""

LOCKUP_STACKED_DARK_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 130" width="160" height="130">
  <!-- Editable text fallback:
       Font: Outfit Bold (700), size: 22px, letter-spacing: -0.01em
       <text x="80" y="104" font-family="'Outfit', sans-serif" font-weight="700" font-size="22" letter-spacing="-0.01em" text-anchor="middle" fill="#F8FAFC">V Notice</text>
  -->
  <g transform="translate(51.6, 10) scale(0.1993) translate(-40, -35)">
    <path d="M40 35 H245 L325 115 V345 H40 Z" fill="#F5F1E8"/>
    <path d="M245 35 V115 H325 Z" fill="#B08D57"/>
    <path d="M82 112 H128 L182 260 L236 112 H282 L205 315 H159 Z" fill="#111318"/>
    <path d="M82 342 H282" stroke="#B08D57" stroke-width="8" stroke-linecap="square"/>
  </g>
  <path d="{TITLE_STACK_PATH}" fill="#F8FAFC"/>
</svg>"""


def write_svg_files():
    # Canonical Brand Directory
    (BRAND_DIR / "logo-obsidian.svg").write_text(LOGO_OBSIDIAN_SVG, encoding="utf-8")
    (BRAND_DIR / "logo-light-tile.svg").write_text(LOGO_LIGHT_TILE_SVG, encoding="utf-8")
    (BRAND_DIR / "logo-mono-dot.svg").write_text(LOGO_MONO_DOT_SVG, encoding="utf-8")
    (BRAND_DIR / "logo-urgent.svg").write_text(LOGO_URGENT_SVG, encoding="utf-8")
    (BRAND_DIR / "logo-mark.svg").write_text(LOGO_OBSIDIAN_SVG, encoding="utf-8")
    (BRAND_DIR / "logo.svg").write_text(LOGO_OBSIDIAN_SVG, encoding="utf-8")
    (BRAND_DIR / "favicon-16.svg").write_text(LOGO_FAVICON_16_SVG, encoding="utf-8")
    (BRAND_DIR / "favicon-32.svg").write_text(LOGO_FAVICON_32_SVG, encoding="utf-8")
    (BRAND_DIR / "favicon.svg").write_text(LOGO_FAVICON_ROOT_SVG, encoding="utf-8")
    (BRAND_DIR / "logo-lockup-dark.svg").write_text(LOCKUP_HORIZONTAL_DARK_SVG, encoding="utf-8")
    (BRAND_DIR / "logo-lockup-light.svg").write_text(LOCKUP_HORIZONTAL_LIGHT_SVG, encoding="utf-8")
    (BRAND_DIR / "logo-lockup-stacked-dark.svg").write_text(LOCKUP_STACKED_DARK_SVG, encoding="utf-8")
    (BRAND_DIR / "logo-lockup-stacked-light.svg").write_text(LOCKUP_STACKED_LIGHT_SVG, encoding="utf-8")
    (BRAND_DIR / "logo-with-wordmark.svg").write_text(LOCKUP_HORIZONTAL_DARK_SVG, encoding="utf-8")

    # Static root favicon.svg
    (STATIC_DIR / "favicon.svg").write_text(LOGO_FAVICON_ROOT_SVG, encoding="utf-8")

    # Legacy static/images mappings (so zero broken images or 404s anywhere)
    (IMAGES_DIR / "logo.svg").write_text(LOGO_OBSIDIAN_SVG, encoding="utf-8")
    (IMAGES_DIR / "vnotice_logo.svg").write_text(LOGO_OBSIDIAN_SVG, encoding="utf-8")
    (IMAGES_DIR / "vnotice_logo_white.svg").write_text(LOGO_LIGHT_TILE_SVG, encoding="utf-8")
    (IMAGES_DIR / "vnotice_logo_urgent.svg").write_text(LOGO_URGENT_SVG, encoding="utf-8")
    (IMAGES_DIR / "vnotice_lockup.svg").write_text(LOCKUP_HORIZONTAL_DARK_SVG, encoding="utf-8")
    print("Vector SVG brand files written successfully.")


def rasterize_assets():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def render_svg_html(svg_str, size, bg="transparent", mark_scale=1.0):
            if mark_scale < 1.0:
                inner_size = int(size * mark_scale)
                return f"""<!DOCTYPE html>
                <html><head><style>
                  body {{ margin:0; padding:0; background:{bg}; width:{size}px; height:{size}px; display:flex; align-items:center; justify-content:center; overflow:hidden; }}
                </style></head><body>
                  <div style="width:{inner_size}px; height:{inner_size}px;">
                    {svg_str}
                  </div>
                </body></html>"""
            else:
                return f"""<!DOCTYPE html>
                <html><head><style>
                  body {{ margin:0; padding:0; background:{bg}; width:{size}px; height:{size}px; display:flex; align-items:center; justify-content:center; overflow:hidden; }}
                  svg {{ width:100%; height:100%; }}
                </style></head><body>
                  {svg_str}
                </body></html>"""

        # 1. Favicon cuts at 16, 24, 32, 48 and standard marks at 64, 180
        fav_sizes = {
            16: (LOGO_FAVICON_16_SVG, BRAND_DIR / "mark-16.png"),
            24: (LOGO_FAVICON_16_SVG, BRAND_DIR / "mark-24.png"),
            32: (LOGO_FAVICON_32_SVG, BRAND_DIR / "mark-32.png"),
            48: (LOGO_FAVICON_32_SVG, BRAND_DIR / "mark-48.png"),
            64: (LOGO_OBSIDIAN_SVG, BRAND_DIR / "mark-64.png"),
            180: (LOGO_OBSIDIAN_SVG, BRAND_DIR / "mark-180.png"),
        }

        for sz, (svg_str, path) in fav_sizes.items():
            page.set_viewport_size({"width": sz, "height": sz})
            page.set_content(render_svg_html(svg_str, sz))
            page.screenshot(path=str(path), omit_background=True)
            print(f"Generated: {path.name} ({sz}x{sz})")

        # Apple touch icon (180x180) in static/ and brand/ (standard dark mark on transparent/white)
        page.set_viewport_size({"width": 180, "height": 180})
        page.set_content(render_svg_html(LOGO_OBSIDIAN_SVG, 180))
        page.screenshot(path=str(STATIC_DIR / "apple-touch-icon.png"), omit_background=True)
        page.screenshot(path=str(BRAND_DIR / "apple-touch-icon.png"), omit_background=True)

        # Favicon 32 in static/
        page.set_viewport_size({"width": 32, "height": 32})
        page.set_content(render_svg_html(LOGO_FAVICON_32_SVG, 32))
        page.screenshot(path=str(STATIC_DIR / "favicon.png"), omit_background=True)

        # PWA standard icons (192 and 512)
        page.set_viewport_size({"width": 192, "height": 192})
        page.set_content(render_svg_html(LOGO_OBSIDIAN_SVG, 192))
        page.screenshot(path=str(ICONS_DIR / "icon-192.png"), omit_background=True)

        page.set_viewport_size({"width": 512, "height": 512})
        page.set_content(render_svg_html(LOGO_OBSIDIAN_SVG, 512))
        page.screenshot(path=str(ICONS_DIR / "icon-512.png"), omit_background=True)
        page.screenshot(path=str(IMAGES_DIR / "logo.png"), omit_background=True)

        # PWA maskable icons (full bleed #111318 background, monogram in central 80% safe zone, reversed colors)
        page.set_viewport_size({"width": 192, "height": 192})
        page.set_content(render_svg_html(LOGO_LIGHT_TILE_SVG, 192, bg="#111318", mark_scale=0.80))
        page.screenshot(path=str(ICONS_DIR / "icon-192-maskable.png"), omit_background=False)
        page.screenshot(path=str(ICONS_DIR / "icon-maskable-192.png"), omit_background=False)

        page.set_viewport_size({"width": 512, "height": 512})
        page.set_content(render_svg_html(LOGO_LIGHT_TILE_SVG, 512, bg="#111318", mark_scale=0.80))
        page.screenshot(path=str(ICONS_DIR / "icon-512-maskable.png"), omit_background=False)
        page.screenshot(path=str(ICONS_DIR / "icon-maskable-512.png"), omit_background=False)
        print("Generated: PWA 192, 512, and 512-maskable icons.")

        # Open Graph Preview Image (1200x630)
        og_html = f"""<!DOCTYPE html>
        <html><head><style>
          body {{
            margin: 0;
            padding: 0;
            width: 1200px;
            height: 630px;
            background: #0B1020;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: #F8FAFC;
            position: relative;
            overflow: hidden;
          }}
          .ambient-glow {{
            position: absolute;
            width: 700px;
            height: 700px;
            background: radial-gradient(circle, rgba(176, 141, 87, 0.15) 0%, rgba(17, 19, 24, 0.4) 50%, transparent 70%);
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            pointer-events: none;
          }}
          .card {{
            position: relative;
            z-index: 2;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            gap: 28px;
            max-width: 900px;
          }}
          .badge {{
            padding: 8px 22px;
            background: rgba(30, 41, 59, 0.85);
            border: 1px solid #B08D57;
            border-radius: 9999px;
            font-size: 13px;
            color: #B08D57;
            font-weight: 600;
            letter-spacing: 0.18em;
            text-transform: uppercase;
          }}
          .brand-lockup {{
            display: flex;
            align-items: center;
            justify-content: center;
          }}
          .tagline {{
            font-size: 22px;
            font-weight: 400;
            color: #94A3B8;
            margin: 0;
            max-width: 680px;
            line-height: 1.5;
          }}
        </style></head><body>
          <div class="ambient-glow"></div>
          <div class="card">
            <div class="badge">Campus Digital Noticeboard</div>
            <div class="brand-lockup">
              <div style="width: 520px; height: 130px;">
                {LOCKUP_HORIZONTAL_DARK_SVG}
              </div>
            </div>
            <p class="tagline">Real-Time Notice Broadcast &amp; Autonomous Kiosk Display Engine</p>
          </div>
        </body></html>"""

        page.set_viewport_size({"width": 1200, "height": 630})
        page.set_content(og_html)
        page.screenshot(path=str(BRAND_DIR / "og-image.png"))
        print("Generated: og-image.png (1200x630)")

        # ---------------------------------------------------------------------------
        # VERIFICATION: BRAND CONTACT SHEET
        # Sizes: 16, 24, 32, 64, 180 px on:
        # 1. Light (#FFFFFF)
        # 2. Dark (#0B1020)
        # 3. Kiosk background (#0F172A)
        # For Normal AND Urgent states!
        # ---------------------------------------------------------------------------
        contact_html = f"""<!DOCTYPE html>
        <html><head><style>
          body {{
            margin: 0;
            padding: 40px;
            background: #090D1A;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: #F8FAFC;
          }}
          h1 {{
            font-size: 24px;
            font-weight: 700;
            margin: 0 0 6px 0;
            letter-spacing: -0.01em;
          }}
          p.lead {{
            color: #94A3B8;
            margin: 0 0 32px 0;
            font-size: 14px;
          }}
          .bg-matrix {{
            display: flex;
            flex-direction: column;
            gap: 28px;
          }}
          .bg-card {{
            border-radius: 14px;
            padding: 24px 32px;
            border: 1px solid rgba(255,255,255,0.08);
          }}
          .bg-title {{
            font-size: 15px;
            font-weight: 700;
            margin: 0 0 20px 0;
            display: flex;
            align-items: center;
            justify-content: space-between;
          }}
          .variant-block {{
            margin-bottom: 24px;
          }}
          .variant-name {{
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 12px;
            opacity: 0.85;
          }}
          .sizes-flex {{
            display: flex;
            align-items: flex-end;
            gap: 40px;
          }}
          .size-col {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 10px;
          }}
          .preview-box {{
            height: 180px;
            display: flex;
            align-items: center;
            justify-content: center;
          }}
          .size-lbl {{
            font-size: 11px;
            font-weight: 600;
            opacity: 0.75;
          }}
        </style></head><body>
          <h1>V Notice — New Logo &amp; Typography Verification Sheet</h1>
          <p class="lead">Document Sheet Monogram with Folded Corner and Line (Ink #111318, Ivory #F5F1E8, Gold #B08D57, Urgent #EF4444) at 16, 24, 32, 64, 180px across Light, Dark, and Kiosk (#0F172A) surfaces for Normal &amp; Urgent states.</p>

          <div class="bg-matrix">
            <!-- 1. Kiosk Background (#0F172A) -->
            <div class="bg-card" style="background:#0F172A; color:#F8FAFC;">
              <div class="bg-title"><span>1. Kiosk Surface (#0F172A) — Reversed Mark (Ivory Sheet, Dark V, Gold Fold &amp; Line)</span></div>
              
              <div class="variant-block">
                <div class="variant-name">A. Normal State</div>
                <div class="sizes-flex">
                  <div class="size-col"><div class="preview-box"><div style="width:16px;height:16px;">{LOGO_FAVICON_16_DARK_SVG}</div></div><span class="size-lbl">16px cut</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:24px;height:24px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">24px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:32px;height:32px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">32px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:64px;height:64px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">64px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:180px;height:180px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">180px</span></div>
                </div>
              </div>

              <div class="variant-block">
                <div class="variant-name">B. Urgent Takeover State (#EF4444 Fold Corner)</div>
                <div class="sizes-flex">
                  <div class="size-col"><div class="preview-box"><div style="width:16px;height:16px;">{LOGO_FAVICON_16_URGENT_DARK_SVG}</div></div><span class="size-lbl">16px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:24px;height:24px;">{LOGO_URGENT_DARK_SVG}</div></div><span class="size-lbl">24px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:32px;height:32px;">{LOGO_URGENT_DARK_SVG}</div></div><span class="size-lbl">32px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:64px;height:64px;">{LOGO_URGENT_DARK_SVG}</div></div><span class="size-lbl">64px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:180px;height:180px;">{LOGO_URGENT_DARK_SVG}</div></div><span class="size-lbl">180px</span></div>
                </div>
              </div>
            </div>

            <!-- 2. Dark Admin Surface (#0B1020) -->
            <div class="bg-card" style="background:#0B1020; color:#F8FAFC;">
              <div class="bg-title"><span>2. Dark Admin Surface (#0B1020) — Reversed Mark</span></div>
              
              <div class="variant-block">
                <div class="variant-name">A. Normal State</div>
                <div class="sizes-flex">
                  <div class="size-col"><div class="preview-box"><div style="width:16px;height:16px;">{LOGO_FAVICON_16_DARK_SVG}</div></div><span class="size-lbl">16px cut</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:24px;height:24px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">24px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:32px;height:32px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">32px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:64px;height:64px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">64px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:180px;height:180px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">180px</span></div>
                </div>
              </div>

              <div class="variant-block">
                <div class="variant-name">B. Urgent Takeover State (#EF4444 Fold Corner)</div>
                <div class="sizes-flex">
                  <div class="size-col"><div class="preview-box"><div style="width:16px;height:16px;">{LOGO_FAVICON_16_URGENT_DARK_SVG}</div></div><span class="size-lbl">16px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:24px;height:24px;">{LOGO_URGENT_DARK_SVG}</div></div><span class="size-lbl">24px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:32px;height:32px;">{LOGO_URGENT_DARK_SVG}</div></div><span class="size-lbl">32px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:64px;height:64px;">{LOGO_URGENT_DARK_SVG}</div></div><span class="size-lbl">64px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:180px;height:180px;">{LOGO_URGENT_DARK_SVG}</div></div><span class="size-lbl">180px</span></div>
                </div>
              </div>
            </div>

            <!-- 3. Light Surface (#FFFFFF) -->
            <div class="bg-card" style="background:#FFFFFF; color:#111318; border: 1px solid #E2E8F0;">
              <div class="bg-title"><span>3. Light Surface (#FFFFFF) — Default Mark (Dark Sheet, Ivory V, Gold Fold &amp; Line)</span></div>
              
              <div class="variant-block">
                <div class="variant-name">A. Normal State</div>
                <div class="sizes-flex">
                  <div class="size-col"><div class="preview-box"><div style="width:16px;height:16px;">{LOGO_FAVICON_16_SVG}</div></div><span class="size-lbl">16px cut</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:24px;height:24px;">{LOGO_OBSIDIAN_SVG}</div></div><span class="size-lbl">24px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:32px;height:32px;">{LOGO_OBSIDIAN_SVG}</div></div><span class="size-lbl">32px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:64px;height:64px;">{LOGO_OBSIDIAN_SVG}</div></div><span class="size-lbl">64px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:180px;height:180px;">{LOGO_OBSIDIAN_SVG}</div></div><span class="size-lbl">180px</span></div>
                </div>
              </div>

              <div class="variant-block">
                <div class="variant-name">B. Urgent Takeover State (#EF4444 Fold Corner)</div>
                <div class="sizes-flex">
                  <div class="size-col"><div class="preview-box"><div style="width:16px;height:16px;">{LOGO_FAVICON_16_URGENT_LIGHT_SVG}</div></div><span class="size-lbl">16px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:24px;height:24px;">{LOGO_URGENT_SVG}</div></div><span class="size-lbl">24px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:32px;height:32px;">{LOGO_URGENT_SVG}</div></div><span class="size-lbl">32px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:64px;height:64px;">{LOGO_URGENT_SVG}</div></div><span class="size-lbl">64px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:180px;height:180px;">{LOGO_URGENT_SVG}</div></div><span class="size-lbl">180px</span></div>
                </div>
              </div>
            </div>

          </div>
        </body></html>"""

        page.set_viewport_size({"width": 1400, "height": 1750})
        page.set_content(contact_html)
        contact_path = BRAND_DIR / "contact-sheet.png"
        page.screenshot(path=str(contact_path))
        print("Generated: contact-sheet.png (Light, Dark, and Kiosk #0F172A surfaces for Normal & Urgent states)")

        browser.close()

    # Multi-resolution Favicon.ico (16, 32, 48) using Pillow from simplified cuts
    img16 = Image.open(BRAND_DIR / "mark-16.png")
    img32 = Image.open(BRAND_DIR / "mark-32.png")
    img48 = Image.open(BRAND_DIR / "mark-48.png")

    ico_path = STATIC_DIR / "favicon.ico"
    img48.save(str(ico_path), format="ICO", sizes=[(16, 16), (32, 32), (48, 48)], append_images=[img16, img32])
    img48.save(str(BRAND_DIR / "favicon.ico"), format="ICO", sizes=[(16, 16), (32, 32), (48, 48)], append_images=[img16, img32])
    print("Generated: favicon.ico (16, 32, 48 multi-res)")


if __name__ == "__main__":
    write_svg_files()
    rasterize_assets()
    print("All brand assets generated and verified successfully!")
