import os
import sys
import json
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
# GEOMETRY DEFINITIONS (New Mark: Geometric V in Bow-Tie Frame + 3 Broadcast Arcs)
# Proportions: 415x292 (ratio 1.4212)
# Mark: Bow-tie screen frame + central V
# Arcs: 3 concentric broadcast arcs above V
# ---------------------------------------------------------------------------

MARK_PATH = "M 0 71 L 130 118 L 153.5 118 L 207 226 L 260.5 118 L 284 118 L 414 71 L 414 268 L 277 233 L 283 222 L 390 239 L 390 102 L 308 123 L 228 291 L 186 291 L 106 123 L 24 102 L 24 239 L 131 222 L 137 233 L 0 268 Z"
ARC3_PATH = "M 109.19 45.14 A 155.50 155.50 0 0 1 304.81 45.14"
ARC2_PATH = "M 142.13 75.87 A 116.00 116.00 0 0 1 271.87 75.87"
ARC1_PATH = "M 172.26 105.84 A 76.50 76.50 0 0 1 241.74 105.84"

# 1. Variant 1: Default Mark for Dark Surfaces (Vanilla #EEEBDA mark, Gold #B08D57 arcs)
LOGO_OBSIDIAN_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 415 292" width="100%" height="100%">
  <g id="mark" class="vnotice-mark" fill="var(--logo-mark, #EEEBDA)">
    <path d="{MARK_PATH}"/>
  </g>
  <g id="arcs" class="vnotice-arcs" fill="none" stroke="var(--logo-arcs, #B08D57)" stroke-linecap="round">
    <path d="{ARC3_PATH}" stroke-width="20"/>
    <path d="{ARC2_PATH}" stroke-width="19"/>
    <path d="{ARC1_PATH}" stroke-width="18"/>
  </g>
</svg>"""

# 2. Variant 2: Reversed Mark for Light Surfaces (Ink #131210 mark, Darker Gold #8A6B3A arcs)
LOGO_LIGHT_TILE_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 415 292" width="100%" height="100%">
  <g id="mark" class="vnotice-mark" fill="var(--logo-mark, #131210)">
    <path d="{MARK_PATH}"/>
  </g>
  <g id="arcs" class="vnotice-arcs" fill="none" stroke="var(--logo-arcs, #8A6B3A)" stroke-linecap="round">
    <path d="{ARC3_PATH}" stroke-width="20"/>
    <path d="{ARC2_PATH}" stroke-width="19"/>
    <path d="{ARC1_PATH}" stroke-width="18"/>
  </g>
</svg>"""

# 3. Variant 3: Fixed Mono Dot / Standard Mark (Kept for backwards compatibility)
LOGO_MONO_DOT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 415 292" width="100%" height="100%">
  <g id="mark" class="vnotice-mark" fill="#EEEBDA">
    <path d="{MARK_PATH}"/>
  </g>
  <g id="arcs" class="vnotice-arcs" fill="none" stroke="#B08D57" stroke-linecap="round">
    <path d="{ARC3_PATH}" stroke-width="20"/>
    <path d="{ARC2_PATH}" stroke-width="19"/>
    <path d="{ARC1_PATH}" stroke-width="18"/>
  </g>
</svg>"""

# 4. Variant 4: Urgent Takeover State (#EF4444 Arcs)
LOGO_URGENT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 415 292" width="100%" height="100%">
  <g id="mark" class="vnotice-mark" fill="var(--logo-mark, #EEEBDA)">
    <path d="{MARK_PATH}"/>
  </g>
  <g id="arcs" class="vnotice-arcs" fill="none" stroke="#EF4444" stroke-linecap="round">
    <path d="{ARC3_PATH}" stroke-width="20"/>
    <path d="{ARC2_PATH}" stroke-width="19"/>
    <path d="{ARC1_PATH}" stroke-width="18"/>
  </g>
</svg>"""

LOGO_URGENT_DARK_SVG = LOGO_URGENT_SVG

# 5. Compact Cut for Tiny Sizes (16px, 24px, 32px, 48px, app icons, maskable icons)
# Central geometric V with arcs above it inside rounded tile, no thin frame lines
V_PATH_32 = "M 75 130 H 125 L 160 215 L 195 130 H 245 L 185 270 H 135 Z"
ARC3_32 = "M 67.66 82.35 A 138.00 138.00 0 0 1 252.34 82.35"
ARC2_32 = "M 100.04 102.48 A 102.00 102.00 0 0 1 219.96 102.48"
ARC1_32 = "M 128.08 125.01 A 68.00 68.00 0 0 1 191.92 125.01"

# 16px & 24px: 2 thicker arcs so details stay sharp and never turn to mush
V_PATH_16 = "M 65 130 H 125 L 160 210 L 195 130 H 255 L 190 275 H 130 Z"
ARC2_16 = "M 73.01 93.30 A 130.00 130.00 0 0 1 246.99 93.30"
ARC1_16 = "M 117.61 122.13 A 80.00 80.00 0 0 1 202.39 122.13"

LOGO_FAVICON_16_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="100%" height="100%">
  <rect width="320" height="320" rx="64" fill="#131210"/>
  <g class="vnotice-mark" fill="#EEEBDA">
    <path d="{V_PATH_16}"/>
  </g>
  <g class="vnotice-arcs" fill="none" stroke="#B08D57" stroke-linecap="round">
    <path d="{ARC2_16}" stroke-width="32"/>
    <path d="{ARC1_16}" stroke-width="28"/>
  </g>
</svg>"""

LOGO_FAVICON_16_DARK_SVG = LOGO_FAVICON_16_SVG

LOGO_FAVICON_16_LIGHT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="100%" height="100%">
  <rect width="320" height="320" rx="64" fill="#F5F1E8"/>
  <g class="vnotice-mark" fill="#131210">
    <path d="{V_PATH_16}"/>
  </g>
  <g class="vnotice-arcs" fill="none" stroke="#8A6B3A" stroke-linecap="round">
    <path d="{ARC2_16}" stroke-width="32"/>
    <path d="{ARC1_16}" stroke-width="28"/>
  </g>
</svg>"""

LOGO_FAVICON_16_URGENT_DARK_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="100%" height="100%">
  <rect width="320" height="320" rx="64" fill="#131210"/>
  <g class="vnotice-mark" fill="#EEEBDA">
    <path d="{V_PATH_16}"/>
  </g>
  <g class="vnotice-arcs" fill="none" stroke="#EF4444" stroke-linecap="round">
    <path d="{ARC2_16}" stroke-width="32"/>
    <path d="{ARC1_16}" stroke-width="28"/>
  </g>
</svg>"""

LOGO_FAVICON_16_URGENT_LIGHT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="100%" height="100%">
  <rect width="320" height="320" rx="64" fill="#F5F1E8"/>
  <g class="vnotice-mark" fill="#131210">
    <path d="{V_PATH_16}"/>
  </g>
  <g class="vnotice-arcs" fill="none" stroke="#EF4444" stroke-linecap="round">
    <path d="{ARC2_16}" stroke-width="32"/>
    <path d="{ARC1_16}" stroke-width="28"/>
  </g>
</svg>"""

LOGO_FAVICON_32_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="100%" height="100%">
  <rect width="320" height="320" rx="64" fill="#131210"/>
  <g class="vnotice-mark" fill="#EEEBDA">
    <path d="{V_PATH_32}"/>
  </g>
  <g class="vnotice-arcs" fill="none" stroke="#B08D57" stroke-linecap="round">
    <path d="{ARC3_32}" stroke-width="22"/>
    <path d="{ARC2_32}" stroke-width="20"/>
    <path d="{ARC1_32}" stroke-width="18"/>
  </g>
</svg>"""

LOGO_FAVICON_ROOT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="100%" height="100%">
  <style>
    :root {{ --tile-bg: #131210; --mark-color: #EEEBDA; --arcs-color: #B08D57; }}
    @media (prefers-color-scheme: light) {{
      :root {{ --tile-bg: #F5F1E8; --mark-color: #131210; --arcs-color: #8A6B3A; }}
    }}
  </style>
  <rect width="320" height="320" rx="64" fill="var(--tile-bg)"/>
  <g fill="var(--mark-color)">
    <path d="{V_PATH_32}"/>
  </g>
  <g fill="none" stroke="var(--arcs-color)" stroke-linecap="round">
    <path d="{ARC3_32}" stroke-width="22"/>
    <path d="{ARC2_32}" stroke-width="20"/>
    <path d="{ARC1_32}" stroke-width="18"/>
  </g>
</svg>"""

# Load outlined typography paths generated with fontkit
lockup_paths = json.loads(Path(BASE_DIR / "scratch/lockup_paths.json").read_text(encoding="utf-8"))
TITLE_H_PATH = lockup_paths["TITLE_H_PATH"]
DESC_H_PATH = lockup_paths["DESC_H_PATH"]
TITLE_STACK_PATH = lockup_paths["TITLE_STACK_PATH"]
DESC_STACK_PATH = lockup_paths["DESC_STACK_PATH"]

# 6. Outlined Typography Lockups (Horizontal: 240x60, Stacked: 160x130)
# Mark transformed: translate(5, 10) scale(0.137) places mark in [5, 61.8] x [10, 50]
# Wordmark starts at x=68 (aligned), Descriptor starts at x=68 (aligned)
LOCKUP_HORIZONTAL_DARK_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 60" width="240" height="60">
  <!-- Editable text fallback:
       Font: Outfit Bold (700), size: 22px, letter-spacing: -0.01em
       Descriptor: Inter Medium (500), size: 4.8px, letter-spacing: 0.26em, color: rgba(238, 235, 218, 0.70)
       <text x="68" y="32.5" font-family="'Outfit', sans-serif" font-weight="700" font-size="22" letter-spacing="-0.01em" fill="#EEEBDA">V Notice</text>
       <text x="68" y="43.4" font-family="'Inter', sans-serif" font-weight="500" font-size="4.8" letter-spacing="0.20em" fill="rgba(238, 235, 218, 0.70)">DIGITAL NOTICE PLATFORM</text>
  -->
  <g transform="translate(5, 10) scale(0.137)">
    <path d="{MARK_PATH}" fill="#EEEBDA"/>
    <g fill="none" stroke="#B08D57" stroke-linecap="round">
      <path d="{ARC3_PATH}" stroke-width="20"/>
      <path d="{ARC2_PATH}" stroke-width="19"/>
      <path d="{ARC1_PATH}" stroke-width="18"/>
    </g>
  </g>
  <path d="{TITLE_H_PATH}" fill="#EEEBDA"/>
  <path d="{DESC_H_PATH}" fill="rgba(238, 235, 218, 0.70)"/>
</svg>"""

LOCKUP_HORIZONTAL_LIGHT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 60" width="240" height="60">
  <!-- Editable text fallback:
       Font: Outfit Bold (700), size: 22px, letter-spacing: -0.01em
       Descriptor: Inter Medium (500), size: 4.8px, letter-spacing: 0.26em, color: #6E685F
       <text x="68" y="32.5" font-family="'Outfit', sans-serif" font-weight="700" font-size="22" letter-spacing="-0.01em" fill="#131210">V Notice</text>
       <text x="68" y="43.4" font-family="'Inter', sans-serif" font-weight="500" font-size="4.8" letter-spacing="0.20em" fill="#6E685F">DIGITAL NOTICE PLATFORM</text>
  -->
  <g transform="translate(5, 10) scale(0.137)">
    <path d="{MARK_PATH}" fill="#131210"/>
    <g fill="none" stroke="#8A6B3A" stroke-linecap="round">
      <path d="{ARC3_PATH}" stroke-width="20"/>
      <path d="{ARC2_PATH}" stroke-width="19"/>
      <path d="{ARC1_PATH}" stroke-width="18"/>
    </g>
  </g>
  <path d="{TITLE_H_PATH}" fill="#131210"/>
  <path d="{DESC_H_PATH}" fill="#6E685F"/>
</svg>"""

LOCKUP_STACKED_DARK_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 130" width="160" height="130">
  <!-- Editable text fallback:
       Font: Outfit Bold (700), size: 22px, letter-spacing: -0.01em
       Descriptor: Inter Medium (500), size: 4.8px, letter-spacing: 0.26em, color: rgba(238, 235, 218, 0.70)
       <text x="80" y="96" font-family="'Outfit', sans-serif" font-weight="700" font-size="22" letter-spacing="-0.01em" text-anchor="middle" fill="#EEEBDA">V Notice</text>
       <text x="80" y="110" font-family="'Inter', sans-serif" font-weight="500" font-size="4.8" letter-spacing="0.20em" text-anchor="middle" fill="rgba(238, 235, 218, 0.70)">DIGITAL NOTICE PLATFORM</text>
  -->
  <g transform="translate(38, 12) scale(0.2024)">
    <path d="{MARK_PATH}" fill="#EEEBDA"/>
    <g fill="none" stroke="#B08D57" stroke-linecap="round">
      <path d="{ARC3_PATH}" stroke-width="20"/>
      <path d="{ARC2_PATH}" stroke-width="19"/>
      <path d="{ARC1_PATH}" stroke-width="18"/>
    </g>
  </g>
  <path d="{TITLE_STACK_PATH}" fill="#EEEBDA"/>
  <path d="{DESC_STACK_PATH}" fill="rgba(238, 235, 218, 0.70)"/>
</svg>"""

LOCKUP_STACKED_LIGHT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 130" width="160" height="130">
  <!-- Editable text fallback:
       Font: Outfit Bold (700), size: 22px, letter-spacing: -0.01em
       Descriptor: Inter Medium (500), size: 4.8px, letter-spacing: 0.26em, color: #6E685F
       <text x="80" y="96" font-family="'Outfit', sans-serif" font-weight="700" font-size="22" letter-spacing="-0.01em" text-anchor="middle" fill="#131210">V Notice</text>
       <text x="80" y="110" font-family="'Inter', sans-serif" font-weight="500" font-size="4.8" letter-spacing="0.20em" text-anchor="middle" fill="#6E685F">DIGITAL NOTICE PLATFORM</text>
  -->
  <g transform="translate(38, 12) scale(0.2024)">
    <path d="{MARK_PATH}" fill="#131210"/>
    <g fill="none" stroke="#8A6B3A" stroke-linecap="round">
      <path d="{ARC3_PATH}" stroke-width="20"/>
      <path d="{ARC2_PATH}" stroke-width="19"/>
      <path d="{ARC1_PATH}" stroke-width="18"/>
    </g>
  </g>
  <path d="{TITLE_STACK_PATH}" fill="#131210"/>
  <path d="{DESC_STACK_PATH}" fill="#6E685F"/>
</svg>"""


def write_svg_files():
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

    # Legacy static/images mappings
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

        # 1. Compact cut raster marks at 16, 24, 32, 48 and standard cuts at 64, 180
        fav_sizes = {
            16: (LOGO_FAVICON_16_SVG, BRAND_DIR / "mark-16.png"),
            24: (LOGO_FAVICON_16_SVG, BRAND_DIR / "mark-24.png"),
            32: (LOGO_FAVICON_32_SVG, BRAND_DIR / "mark-32.png"),
            48: (LOGO_FAVICON_32_SVG, BRAND_DIR / "mark-48.png"),
            64: (LOGO_FAVICON_32_SVG, BRAND_DIR / "mark-64.png"),
            180: (LOGO_FAVICON_32_SVG, BRAND_DIR / "mark-180.png"),
        }

        for sz, (svg_str, path) in fav_sizes.items():
            page.set_viewport_size({"width": sz, "height": sz})
            page.set_content(render_svg_html(svg_str, sz))
            page.screenshot(path=str(path), omit_background=True)
            print(f"Generated: {path.name} ({sz}x{sz})")

        # Apple touch icon (180x180) in static/ and brand/
        page.set_viewport_size({"width": 180, "height": 180})
        page.set_content(render_svg_html(LOGO_FAVICON_32_SVG, 180))
        page.screenshot(path=str(STATIC_DIR / "apple-touch-icon.png"), omit_background=True)
        page.screenshot(path=str(BRAND_DIR / "apple-touch-icon.png"), omit_background=True)

        # Favicon 32 in static/
        page.set_viewport_size({"width": 32, "height": 32})
        page.set_content(render_svg_html(LOGO_FAVICON_32_SVG, 32))
        page.screenshot(path=str(STATIC_DIR / "favicon.png"), omit_background=True)

        # PWA standard icons (192 and 512): Compact cut in rounded tile style
        page.set_viewport_size({"width": 192, "height": 192})
        page.set_content(render_svg_html(LOGO_FAVICON_32_SVG, 192))
        page.screenshot(path=str(ICONS_DIR / "icon-192.png"), omit_background=True)

        page.set_viewport_size({"width": 512, "height": 512})
        page.set_content(render_svg_html(LOGO_FAVICON_32_SVG, 512))
        page.screenshot(path=str(ICONS_DIR / "icon-512.png"), omit_background=True)
        page.screenshot(path=str(IMAGES_DIR / "logo.png"), omit_background=True)

        # PWA maskable icons (full-bleed #131210 background with compact mark inside central 80% safe zone)
        # Transparent inner SVG on #131210 full-bleed:
        COMPACT_INNER_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="100%" height="100%">
          <g fill="#EEEBDA"><path d="{V_PATH_32}"/></g>
          <g fill="none" stroke="#B08D57" stroke-linecap="round">
            <path d="{ARC3_32}" stroke-width="22"/>
            <path d="{ARC2_32}" stroke-width="20"/>
            <path d="{ARC1_32}" stroke-width="18"/>
          </g>
        </svg>"""

        page.set_viewport_size({"width": 192, "height": 192})
        page.set_content(render_svg_html(COMPACT_INNER_SVG, 192, bg="#131210", mark_scale=0.80))
        page.screenshot(path=str(ICONS_DIR / "icon-192-maskable.png"), omit_background=False)
        page.screenshot(path=str(ICONS_DIR / "icon-maskable-192.png"), omit_background=False)

        page.set_viewport_size({"width": 512, "height": 512})
        page.set_content(render_svg_html(COMPACT_INNER_SVG, 512, bg="#131210", mark_scale=0.80))
        page.screenshot(path=str(ICONS_DIR / "icon-512-maskable.png"), omit_background=False)
        page.screenshot(path=str(ICONS_DIR / "icon-maskable-512.png"), omit_background=False)
        print("Generated: PWA 192, 512, and maskable icons.")

        # Open Graph Preview Image (1200x630): dark warm background #131210, lockup with descriptor centered, nothing else
        og_html = f"""<!DOCTYPE html>
        <html><head><style>
          body {{
            margin: 0;
            padding: 0;
            width: 1200px;
            height: 630px;
            background: #131210;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
          }}
          .lockup-wrap {{
            width: 800px;
            height: 200px;
            display: flex;
            align-items: center;
            justify-content: center;
          }}
          .lockup-wrap svg {{
            width: 100%;
            height: 100%;
          }}
        </style></head><body>
          <div class="lockup-wrap">
            {LOCKUP_HORIZONTAL_DARK_SVG}
          </div>
        </body></html>"""

        page.set_viewport_size({"width": 1200, "height": 630})
        page.set_content(og_html)
        page.screenshot(path=str(BRAND_DIR / "og-image.png"))
        print("Generated: og-image.png (1200x630)")

        # ---------------------------------------------------------------------------
        # VERIFICATION: BRAND CONTACT SHEET
        # Sizes: 16, 24, 32, 48, 64, 180 px on:
        # 1. Light (#FFFFFF and #F5F1E8)
        # 2. Dark (#0B1020)
        # 3. #131210
        # For Normal AND Urgent states, for BOTH Full Mark and Compact Mark!
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
            gap: 32px;
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
          <p class="lead">Geometric V in Bow-Tie Screen Frame + 3 Broadcast Arcs (Vanilla #EEEBDA, Ink #131210, Gold #B08D57, Urgent #EF4444) at 16, 24, 32, 48, 64, 180px across Light, Dark, and #131210 surfaces for Full Mark and Compact Cut.</p>

          <div class="bg-matrix">
            <!-- 1. Dark Surface (#131210) -->
            <div class="bg-card" style="background:#131210; color:#F8FAFC;">
              <div class="bg-title"><span>1. Dark Surface (#131210) — Vanilla Mark (#EEEBDA), Gold Arcs (#B08D57)</span></div>
              
              <div class="variant-block">
                <div class="variant-name">A. Compact Cut (Normal)</div>
                <div class="sizes-flex">
                  <div class="size-col"><div class="preview-box"><div style="width:16px;height:16px;">{LOGO_FAVICON_16_SVG}</div></div><span class="size-lbl">16px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:24px;height:24px;">{LOGO_FAVICON_16_SVG}</div></div><span class="size-lbl">24px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:32px;height:32px;">{LOGO_FAVICON_32_SVG}</div></div><span class="size-lbl">32px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:48px;height:48px;">{LOGO_FAVICON_32_SVG}</div></div><span class="size-lbl">48px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:64px;height:64px;">{LOGO_FAVICON_32_SVG}</div></div><span class="size-lbl">64px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:180px;height:180px;">{LOGO_FAVICON_32_SVG}</div></div><span class="size-lbl">180px</span></div>
                </div>
              </div>

              <div class="variant-block">
                <div class="variant-name">B. Full Mark (Normal)</div>
                <div class="sizes-flex">
                  <div class="size-col"><div class="preview-box"><div style="width:23px;height:16px;">{LOGO_OBSIDIAN_SVG}</div></div><span class="size-lbl">16px h</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:34px;height:24px;">{LOGO_OBSIDIAN_SVG}</div></div><span class="size-lbl">24px h</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:45.5px;height:32px;">{LOGO_OBSIDIAN_SVG}</div></div><span class="size-lbl">32px h</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:68px;height:48px;">{LOGO_OBSIDIAN_SVG}</div></div><span class="size-lbl">48px h</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:91px;height:64px;">{LOGO_OBSIDIAN_SVG}</div></div><span class="size-lbl">64px h</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:256px;height:180px;">{LOGO_OBSIDIAN_SVG}</div></div><span class="size-lbl">180px h</span></div>
                </div>
              </div>

              <div class="variant-block">
                <div class="variant-name">C. Urgent Takeover State (#EF4444 Arcs)</div>
                <div class="sizes-flex">
                  <div class="size-col"><div class="preview-box"><div style="width:16px;height:16px;">{LOGO_FAVICON_16_URGENT_DARK_SVG}</div></div><span class="size-lbl">16px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:24px;height:24px;">{LOGO_FAVICON_16_URGENT_DARK_SVG}</div></div><span class="size-lbl">24px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:32px;height:32px;">{LOGO_URGENT_SVG}</div></div><span class="size-lbl">32px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:48px;height:48px;">{LOGO_URGENT_SVG}</div></div><span class="size-lbl">48px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:64px;height:64px;">{LOGO_URGENT_SVG}</div></div><span class="size-lbl">64px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:180px;height:180px;">{LOGO_URGENT_SVG}</div></div><span class="size-lbl">180px</span></div>
                </div>
              </div>
            </div>

            <!-- 2. Dark Admin Surface (#0B1020) -->
            <div class="bg-card" style="background:#0B1020; color:#F8FAFC;">
              <div class="bg-title"><span>2. Dark Admin Surface (#0B1020)</span></div>
              <div class="sizes-flex">
                <div class="size-col"><div class="preview-box"><div style="width:16px;height:16px;">{LOGO_FAVICON_16_SVG}</div></div><span class="size-lbl">16px</span></div>
                <div class="size-col"><div class="preview-box"><div style="width:24px;height:24px;">{LOGO_FAVICON_16_SVG}</div></div><span class="size-lbl">24px</span></div>
                <div class="size-col"><div class="preview-box"><div style="width:32px;height:32px;">{LOGO_FAVICON_32_SVG}</div></div><span class="size-lbl">32px</span></div>
                <div class="size-col"><div class="preview-box"><div style="width:48px;height:48px;">{LOGO_FAVICON_32_SVG}</div></div><span class="size-lbl">48px</span></div>
                <div class="size-col"><div class="preview-box"><div style="width:64px;height:64px;">{LOGO_FAVICON_32_SVG}</div></div><span class="size-lbl">64px</span></div>
                <div class="size-col"><div class="preview-box"><div style="width:180px;height:180px;">{LOGO_FAVICON_32_SVG}</div></div><span class="size-lbl">180px</span></div>
              </div>
            </div>

            <!-- 3. Light Surface (#F5F1E8) -->
            <div class="bg-card" style="background:#F5F1E8; color:#131210; border: 1px solid #E2E8F0;">
              <div class="bg-title"><span>3. Light Surface (#F5F1E8) — Ink Mark (#131210), Dark Gold Arcs (#8A6B3A)</span></div>
              
              <div class="variant-block">
                <div class="variant-name">A. Compact Cut (Normal)</div>
                <div class="sizes-flex">
                  <div class="size-col"><div class="preview-box"><div style="width:16px;height:16px;">{LOGO_FAVICON_16_LIGHT_SVG}</div></div><span class="size-lbl">16px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:24px;height:24px;">{LOGO_FAVICON_16_LIGHT_SVG}</div></div><span class="size-lbl">24px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:32px;height:32px;">{LOGO_FAVICON_16_LIGHT_SVG}</div></div><span class="size-lbl">32px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:48px;height:48px;">{LOGO_FAVICON_16_LIGHT_SVG}</div></div><span class="size-lbl">48px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:64px;height:64px;">{LOGO_FAVICON_16_LIGHT_SVG}</div></div><span class="size-lbl">64px</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:180px;height:180px;">{LOGO_FAVICON_16_LIGHT_SVG}</div></div><span class="size-lbl">180px</span></div>
                </div>
              </div>

              <div class="variant-block">
                <div class="variant-name">B. Full Mark (Normal)</div>
                <div class="sizes-flex">
                  <div class="size-col"><div class="preview-box"><div style="width:23px;height:16px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">16px h</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:34px;height:24px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">24px h</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:45.5px;height:32px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">32px h</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:68px;height:48px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">48px h</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:91px;height:64px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">64px h</span></div>
                  <div class="size-col"><div class="preview-box"><div style="width:256px;height:180px;">{LOGO_LIGHT_TILE_SVG}</div></div><span class="size-lbl">180px h</span></div>
                </div>
              </div>
            </div>

          </div>
        </body></html>"""

        page.set_viewport_size({"width": 1400, "height": 1750})
        page.set_content(contact_html)
        contact_path = BRAND_DIR / "contact-sheet.png"
        page.screenshot(path=str(contact_path))
        print("Generated: contact-sheet.png")

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
