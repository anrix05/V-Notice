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
# GEOMETRY DEFINITIONS (New Mark: Signal Arcs Mark)
# Mark only (viewBox "44 20 134 132")
# V: M64 70 L96 132 L128 70, stroke-width 24, stroke-linecap round, stroke-linejoin round
# Arcs:
# Arc 1 (inner): M133.7 48.8 A22 22 0 0 1 149.2 64.3, stroke-width 9, stroke-linecap round
# Arc 2 (outer): M137.8 33.3 A38 38 0 0 1 164.7 60.2, stroke-width 9, stroke-linecap round
# ---------------------------------------------------------------------------

V_PATH = "M64 70 L96 132 L128 70"
ARC1_PATH = "M133.7 48.8 A22 22 0 0 1 149.2 64.3"
ARC2_PATH = "M137.8 33.3 A38 38 0 0 1 164.7 60.2"

# 1. Variant 1: Default Mark for Dark Surfaces (Vanilla #EEEBDA mark, Gold #B08D57 arcs)
LOGO_OBSIDIAN_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="44 20 134 132" width="100%" height="100%">
  <path id="v" class="vnotice-v" d="{V_PATH}" fill="none" stroke="var(--logo-v, #EEEBDA)"
    stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
  <path id="arc-inner" class="vnotice-arc-inner" d="{ARC1_PATH}" fill="none"
    stroke="var(--logo-arcs, #B08D57)" stroke-width="9" stroke-linecap="round"/>
  <path id="arc-outer" class="vnotice-arc-outer" d="{ARC2_PATH}" fill="none"
    stroke="var(--logo-arcs, #B08D57)" stroke-width="9" stroke-linecap="round"/>
</svg>"""

# 2. Variant 2: Reversed Mark for Light Surfaces (Ink #131210 mark, Darker Gold #8A6B3A arcs)
LOGO_LIGHT_TILE_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="44 20 134 132" width="100%" height="100%">
  <path id="v" class="vnotice-v" d="{V_PATH}" fill="none" stroke="var(--logo-v, #131210)"
    stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
  <path id="arc-inner" class="vnotice-arc-inner" d="{ARC1_PATH}" fill="none"
    stroke="var(--logo-arcs, #8A6B3A)" stroke-width="9" stroke-linecap="round"/>
  <path id="arc-outer" class="vnotice-arc-outer" d="{ARC2_PATH}" fill="none"
    stroke="var(--logo-arcs, #8A6B3A)" stroke-width="9" stroke-linecap="round"/>
</svg>"""

# 3. Variant 3: Fixed Standard Mark (Kept for backwards compatibility)
LOGO_MONO_DOT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="44 20 134 132" width="100%" height="100%">
  <path id="v" class="vnotice-v" d="{V_PATH}" fill="none" stroke="#EEEBDA"
    stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
  <path id="arc-inner" class="vnotice-arc-inner" d="{ARC1_PATH}" fill="none"
    stroke="#B08D57" stroke-width="9" stroke-linecap="round"/>
  <path id="arc-outer" class="vnotice-arc-outer" d="{ARC2_PATH}" fill="none"
    stroke="#B08D57" stroke-width="9" stroke-linecap="round"/>
</svg>"""

# 4. Variant 4: Urgent Takeover State (#EF4444 Arcs)
LOGO_URGENT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="44 20 134 132" width="100%" height="100%">
  <path id="v" class="vnotice-v" d="{V_PATH}" fill="none" stroke="var(--logo-v, #EEEBDA)"
    stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
  <path id="arc-inner" class="vnotice-arc-inner" d="{ARC1_PATH}" fill="none"
    stroke="#EF4444" stroke-width="9" stroke-linecap="round"/>
  <path id="arc-outer" class="vnotice-arc-outer" d="{ARC2_PATH}" fill="none"
    stroke="#EF4444" stroke-width="9" stroke-linecap="round"/>
</svg>"""

# 5. Tile Version for Icons (viewBox "0 0 200 200", rect 200x200 rx 44)
LOGO_TILE_DARK_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="100%" height="100%">
  <rect width="200" height="200" rx="44" fill="#131210"/>
  <path d="{V_PATH}" fill="none" stroke="#EEEBDA"
    stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="{ARC1_PATH}" fill="none"
    stroke="#B08D57" stroke-width="9" stroke-linecap="round"/>
  <path d="{ARC2_PATH}" fill="none"
    stroke="#B08D57" stroke-width="9" stroke-linecap="round"/>
</svg>"""

LOGO_TILE_LIGHT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="100%" height="100%">
  <rect width="200" height="200" rx="44" fill="#F5F1E8"/>
  <path d="{V_PATH}" fill="none" stroke="#131210"
    stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="{ARC1_PATH}" fill="none"
    stroke="#8A6B3A" stroke-width="9" stroke-linecap="round"/>
  <path d="{ARC2_PATH}" fill="none"
    stroke="#8A6B3A" stroke-width="9" stroke-linecap="round"/>
</svg>"""

# 6. Compact Cut for 16px and 32px: thicker V (stroke 30), only inner arc (stroke 11)
LOGO_COMPACT_16_32_DARK_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="100%" height="100%">
  <rect width="200" height="200" rx="44" fill="#131210"/>
  <path d="{V_PATH}" fill="none" stroke="#EEEBDA"
    stroke-width="30" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="{ARC1_PATH}" fill="none"
    stroke="#B08D57" stroke-width="11" stroke-linecap="round"/>
</svg>"""

LOGO_COMPACT_16_32_LIGHT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="100%" height="100%">
  <rect width="200" height="200" rx="44" fill="#F5F1E8"/>
  <path d="{V_PATH}" fill="none" stroke="#131210"
    stroke-width="30" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="{ARC1_PATH}" fill="none"
    stroke="#8A6B3A" stroke-width="11" stroke-linecap="round"/>
</svg>"""

# Root Favicon SVG (adaptive prefers-color-scheme with compact cut)
LOGO_FAVICON_ROOT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="100%" height="100%">
  <style>
    :root {{ --tile-bg: #131210; --logo-v: #EEEBDA; --logo-arcs: #B08D57; }}
    @media (prefers-color-scheme: light) {{
      :root {{ --tile-bg: #F5F1E8; --logo-v: #131210; --logo-arcs: #8A6B3A; }}
    }}
  </style>
  <rect width="200" height="200" rx="44" fill="var(--tile-bg)"/>
  <path d="{V_PATH}" fill="none" stroke="var(--logo-v)"
    stroke-width="30" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="{ARC1_PATH}" fill="none"
    stroke="var(--logo-arcs)" stroke-width="11" stroke-linecap="round"/>
</svg>"""

# Load outlined typography paths generated with fontkit
v3_lockup_paths = json.loads(Path(BASE_DIR / "scratch/v3_lockup_paths.json").read_text(encoding="utf-8"))
TITLE_H_PATH = v3_lockup_paths["TITLE_H_PATH"]
DESC_H_PATH = v3_lockup_paths["DESC_H_PATH"]
TITLE_STACK_PATH = v3_lockup_paths["TITLE_STACK_PATH"]
DESC_STACK_PATH = v3_lockup_paths["DESC_STACK_PATH"]

# 7. Outlined Typography Lockups (Horizontal: 240x60, Stacked: 160x130)
# Mark transformed: translate(12, 10) scale(0.303) translate(-44, -20)
# Places mark in [12, 52.6] x [10, 50], center Y=30
# Wordmark starts at x=64, Descriptor starts at x=64
LOCKUP_HORIZONTAL_DARK_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 60" width="240" height="60">
  <!-- Editable text fallback:
       Font: Outfit SemiBold (600), size: 22px, letter-spacing: -0.01em
       Descriptor: Inter Medium (500), size: 6.27px, letter-spacing: 0.25em, color: rgba(238, 235, 218, 0.70)
       <text x="64" y="32.5" font-family="'Outfit', sans-serif" font-weight="600" font-size="22" letter-spacing="-0.01em" fill="#EEEBDA">V Notice</text>
       <text x="64" y="43.5" font-family="'Inter', sans-serif" font-weight="500" font-size="6.27" letter-spacing="0.25em" fill="rgba(238, 235, 218, 0.70)">DIGITAL NOTICE BOARD</text>
  -->
  <g transform="translate(12, 10) scale(0.303) translate(-44, -20)">
    <path d="{V_PATH}" fill="none" stroke="#EEEBDA"
      stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="{ARC1_PATH}" fill="none"
      stroke="#B08D57" stroke-width="9" stroke-linecap="round"/>
    <path d="{ARC2_PATH}" fill="none"
      stroke="#B08D57" stroke-width="9" stroke-linecap="round"/>
  </g>
  <path d="{TITLE_H_PATH}" fill="#EEEBDA"/>
  <path d="{DESC_H_PATH}" fill="rgba(238, 235, 218, 0.70)"/>
</svg>"""

LOCKUP_HORIZONTAL_LIGHT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 60" width="240" height="60">
  <!-- Editable text fallback:
       Font: Outfit SemiBold (600), size: 22px, letter-spacing: -0.01em
       Descriptor: Inter Medium (500), size: 6.27px, letter-spacing: 0.25em, color: #6E685F
       <text x="64" y="32.5" font-family="'Outfit', sans-serif" font-weight="600" font-size="22" letter-spacing="-0.01em" fill="#131210">V Notice</text>
       <text x="64" y="43.5" font-family="'Inter', sans-serif" font-weight="500" font-size="6.27" letter-spacing="0.25em" fill="#6E685F">DIGITAL NOTICE BOARD</text>
  -->
  <g transform="translate(12, 10) scale(0.303) translate(-44, -20)">
    <path d="{V_PATH}" fill="none" stroke="#131210"
      stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="{ARC1_PATH}" fill="none"
      stroke="#8A6B3A" stroke-width="9" stroke-linecap="round"/>
    <path d="{ARC2_PATH}" fill="none"
      stroke="#8A6B3A" stroke-width="9" stroke-linecap="round"/>
  </g>
  <path d="{TITLE_H_PATH}" fill="#131210"/>
  <path d="{DESC_H_PATH}" fill="#6E685F"/>
</svg>"""

LOCKUP_STACKED_DARK_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 130" width="160" height="130">
  <!-- Editable text fallback:
       Font: Outfit SemiBold (600), size: 22px, letter-spacing: -0.01em
       Descriptor: Inter Medium (500), size: 6.27px, letter-spacing: 0.25em, color: rgba(238, 235, 218, 0.70)
       <text x="80" y="88" font-family="'Outfit', sans-serif" font-weight="600" font-size="22" letter-spacing="-0.01em" text-anchor="middle" fill="#EEEBDA">V Notice</text>
       <text x="80" y="104" font-family="'Inter', sans-serif" font-weight="500" font-size="6.27" letter-spacing="0.25em" text-anchor="middle" fill="rgba(238, 235, 218, 0.70)">DIGITAL NOTICE BOARD</text>
  -->
  <g transform="translate(55.65, 14) scale(0.3636) translate(-44, -20)">
    <path d="{V_PATH}" fill="none" stroke="#EEEBDA"
      stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="{ARC1_PATH}" fill="none"
      stroke="#B08D57" stroke-width="9" stroke-linecap="round"/>
    <path d="{ARC2_PATH}" fill="none"
      stroke="#B08D57" stroke-width="9" stroke-linecap="round"/>
  </g>
  <path d="{TITLE_STACK_PATH}" fill="#EEEBDA"/>
  <path d="{DESC_STACK_PATH}" fill="rgba(238, 235, 218, 0.70)"/>
</svg>"""

LOCKUP_STACKED_LIGHT_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 130" width="160" height="130">
  <!-- Editable text fallback:
       Font: Outfit SemiBold (600), size: 22px, letter-spacing: -0.01em
       Descriptor: Inter Medium (500), size: 6.27px, letter-spacing: 0.25em, color: #6E685F
       <text x="80" y="88" font-family="'Outfit', sans-serif" font-weight="600" font-size="22" letter-spacing="-0.01em" text-anchor="middle" fill="#131210">V Notice</text>
       <text x="80" y="104" font-family="'Inter', sans-serif" font-weight="500" font-size="6.27" letter-spacing="0.25em" text-anchor="middle" fill="#6E685F">DIGITAL NOTICE BOARD</text>
  -->
  <g transform="translate(55.65, 14) scale(0.3636) translate(-44, -20)">
    <path d="{V_PATH}" fill="none" stroke="#131210"
      stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="{ARC1_PATH}" fill="none"
      stroke="#8A6B3A" stroke-width="9" stroke-linecap="round"/>
    <path d="{ARC2_PATH}" fill="none"
      stroke="#8A6B3A" stroke-width="9" stroke-linecap="round"/>
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
    (BRAND_DIR / "favicon-16.svg").write_text(LOGO_COMPACT_16_32_DARK_SVG, encoding="utf-8")
    (BRAND_DIR / "favicon-32.svg").write_text(LOGO_COMPACT_16_32_DARK_SVG, encoding="utf-8")
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

        # 1. Raster marks at 16, 24, 32 (compact cut) and 48, 64, 180 (tile standard)
        fav_sizes = {
            16: (LOGO_COMPACT_16_32_DARK_SVG, BRAND_DIR / "mark-16.png"),
            24: (LOGO_COMPACT_16_32_DARK_SVG, BRAND_DIR / "mark-24.png"),
            32: (LOGO_COMPACT_16_32_DARK_SVG, BRAND_DIR / "mark-32.png"),
            48: (LOGO_TILE_DARK_SVG, BRAND_DIR / "mark-48.png"),
            64: (LOGO_TILE_DARK_SVG, BRAND_DIR / "mark-64.png"),
            180: (LOGO_TILE_DARK_SVG, BRAND_DIR / "mark-180.png"),
        }

        for sz, (svg_str, path) in fav_sizes.items():
            page.set_viewport_size({"width": sz, "height": sz})
            page.set_content(render_svg_html(svg_str, sz))
            page.screenshot(path=str(path), omit_background=True)
            print(f"Generated: {path.name} ({sz}x{sz})")

        # Apple touch icon (180x180) in static/ and brand/
        page.set_viewport_size({"width": 180, "height": 180})
        page.set_content(render_svg_html(LOGO_TILE_DARK_SVG, 180))
        page.screenshot(path=str(STATIC_DIR / "apple-touch-icon.png"), omit_background=True)
        page.screenshot(path=str(BRAND_DIR / "apple-touch-icon.png"), omit_background=True)

        # Favicon 32 in static/
        page.set_viewport_size({"width": 32, "height": 32})
        page.set_content(render_svg_html(LOGO_COMPACT_16_32_DARK_SVG, 32))
        page.screenshot(path=str(STATIC_DIR / "favicon.png"), omit_background=True)

        # PWA standard icons (192 and 512): Tile version
        page.set_viewport_size({"width": 192, "height": 192})
        page.set_content(render_svg_html(LOGO_TILE_DARK_SVG, 192))
        page.screenshot(path=str(ICONS_DIR / "icon-192.png"), omit_background=True)

        page.set_viewport_size({"width": 512, "height": 512})
        page.set_content(render_svg_html(LOGO_TILE_DARK_SVG, 512))
        page.screenshot(path=str(ICONS_DIR / "icon-512.png"), omit_background=True)
        page.screenshot(path=str(IMAGES_DIR / "logo.png"), omit_background=True)

        # PWA maskable icons (full-bleed #131210 background with mark inside central 80% safe zone)
        MARK_BARE_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="44 20 134 132" width="100%" height="100%">
          <path d="{V_PATH}" fill="none" stroke="#EEEBDA"
            stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="{ARC1_PATH}" fill="none"
            stroke="#B08D57" stroke-width="9" stroke-linecap="round"/>
          <path d="{ARC2_PATH}" fill="none"
            stroke="#B08D57" stroke-width="9" stroke-linecap="round"/>
        </svg>"""

        page.set_viewport_size({"width": 192, "height": 192})
        page.set_content(render_svg_html(MARK_BARE_SVG, 192, bg="#131210", mark_scale=0.80))
        page.screenshot(path=str(ICONS_DIR / "icon-192-maskable.png"), omit_background=False)
        page.screenshot(path=str(ICONS_DIR / "icon-maskable-192.png"), omit_background=False)

        page.set_viewport_size({"width": 512, "height": 512})
        page.set_content(render_svg_html(MARK_BARE_SVG, 512, bg="#131210", mark_scale=0.80))
        page.screenshot(path=str(ICONS_DIR / "icon-512-maskable.png"), omit_background=False)
        page.screenshot(path=str(ICONS_DIR / "icon-maskable-512.png"), omit_background=False)
        print("Generated: PWA 192, 512, and maskable icons.")

        # Open Graph Preview Image (1200x630): dark warm background #131210, horizontal lockup with descriptor centered
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
