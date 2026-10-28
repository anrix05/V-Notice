import os
import sys
import base64
from pathlib import Path
import zxingcpp
import numpy as np
import PIL.Image

def generate_poster():
    poster_dir = Path("poster")
    poster_dir.mkdir(parents=True, exist_ok=True)
    screens_dir = poster_dir / "screens"
    screens_dir.mkdir(parents=True, exist_ok=True)

    # 1. Ensure QR code exists (296x296 at 8x scale, error correction M)
    target_url = "https://v-notice.onrender.com/admin"
    barcode = zxingcpp.create_barcode(target_url, zxingcpp.BarcodeFormat.QRCode, ec_level="M")
    qr_img = zxingcpp.write_barcode_to_image(barcode, scale=8, add_quiet_zones=True)
    qr_pil = PIL.Image.fromarray(np.array(qr_img, copy=False))
    qr_path = poster_dir / "qr.png"
    qr_pil.save(qr_path)

    with open(qr_path, "rb") as f:
        qr_b64 = base64.b64encode(f.read()).decode("ascii")

    # 2. Fonts base64
    font_b64 = {}
    for name in ["Outfit-Bold", "Outfit-Regular", "Inter-Bold", "Inter-Regular"]:
        fp = Path(f"static/fonts/{name}.woff2")
        if fp.exists():
            with open(fp, "rb") as f:
                font_b64[name] = base64.b64encode(f.read()).decode("ascii")

    # 3. Check screenshots
    has_display = (screens_dir / "display-1080p.png").is_file() and (screens_dir / "display-1080p.png").stat().st_size > 0
    has_admin = (screens_dir / "admin-mobile.png").is_file() and (screens_dir / "admin-mobile.png").stat().st_size > 0
    has_public = (screens_dir / "public-mobile.png").is_file() and (screens_dir / "public-mobile.png").stat().st_size > 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>V Notice Exhibition Poster</title>
  <!-- Google Fonts fallback -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Outfit:wght@600;700&display=swap" rel="stylesheet">
  <style>
    /* Embedded Brand Fonts */
    @font-face {{
      font-family: 'Outfit';
      font-style: normal;
      font-weight: 700;
      font-display: swap;
      src: url('data:font/woff2;base64,{font_b64.get("Outfit-Bold", "")}') format('woff2'),
           url('../static/fonts/Outfit-Bold.woff2') format('woff2');
    }}
    @font-face {{
      font-family: 'Outfit';
      font-style: normal;
      font-weight: 600;
      font-display: swap;
      src: url('data:font/woff2;base64,{font_b64.get("Outfit-Bold", "")}') format('woff2'),
           url('../static/fonts/Outfit-Bold.woff2') format('woff2');
    }}
    @font-face {{
      font-family: 'Outfit';
      font-style: normal;
      font-weight: 400;
      font-display: swap;
      src: url('data:font/woff2;base64,{font_b64.get("Outfit-Regular", "")}') format('woff2'),
           url('../static/fonts/Outfit-Regular.woff2') format('woff2');
    }}
    @font-face {{
      font-family: 'Inter';
      font-style: normal;
      font-weight: 700;
      font-display: swap;
      src: url('data:font/woff2;base64,{font_b64.get("Inter-Bold", "")}') format('woff2'),
           url('../static/fonts/Inter-Bold.woff2') format('woff2');
    }}
    @font-face {{
      font-family: 'Inter';
      font-style: normal;
      font-weight: 500;
      font-display: swap;
      src: url('data:font/woff2;base64,{font_b64.get("Inter-Regular", "")}') format('woff2'),
           url('../static/fonts/Inter-Regular.woff2') format('woff2');
    }}
    @font-face {{
      font-family: 'Inter';
      font-style: normal;
      font-weight: 400;
      font-display: swap;
      src: url('data:font/woff2;base64,{font_b64.get("Inter-Regular", "")}') format('woff2'),
           url('../static/fonts/Inter-Regular.woff2') format('woff2');
    }}

    /* Print & 16:9 Canvas Setup */
    @page {{
      size: 1920px 1080px;
      margin: 0;
    }}

    *, *::before, *::after {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    :root {{
      --color-ink: #111318;
      --color-vanilla: #EEEBDA;
      --color-gold: #B08D57;
      --color-panel: #1C1B17;
      --color-panel-border: #282620;
      --color-text-dim: rgba(238, 235, 218, 0.78);
      --font-headline: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      --font-body: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }}

    html, body {{
      width: 1920px;
      height: 1080px;
      overflow: hidden;
      background-color: var(--color-ink);
      color: var(--color-vanilla);
      font-family: var(--font-body);
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }}

    /* Outer Canvas with 80px Safe Margins */
    .poster-canvas {{
      width: 1920px;
      height: 1080px;
      padding: 80px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      position: relative;
    }}

    /* TOP / MAIN SECTION (520px height): Left 45% (780px), Right 55% (940px) */
    .poster-main {{
      width: 1760px;
      height: 520px;
      display: grid;
      grid-template-columns: 780px 940px;
      gap: 40px;
      align-items: start;
    }}

    /* LEFT 45% COLUMN */
    .hero-column {{
      display: flex;
      flex-direction: column;
      height: 520px;
      justify-content: flex-start;
    }}

    /* Logo Header */
    .brand-row {{
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 16px;
    }}

    .brand-logo {{
      width: 40px;
      height: 40px;
      flex-shrink: 0;
    }}

    .brand-name {{
      font-family: var(--font-headline);
      font-size: 30px;
      font-weight: 700;
      letter-spacing: -0.01em;
      color: var(--color-vanilla);
    }}

    /* Eyebrow */
    .eyebrow {{
      font-family: var(--font-body);
      font-size: 16px;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--color-gold);
      margin-bottom: 10px;
    }}

    /* Headline (106px, Outfit 700, 3 lines, about 110px) */
    .headline {{
      font-family: var(--font-headline);
      font-size: 106px;
      font-weight: 700;
      line-height: 0.93;
      letter-spacing: -0.035em;
      color: var(--color-vanilla);
      margin-bottom: 12px;
    }}

    /* Subline */
    .subline {{
      font-family: var(--font-body);
      font-size: 17.5px;
      font-weight: 400;
      line-height: 1.38;
      color: var(--color-text-dim);
      margin-bottom: 16px;
      max-width: 740px;
    }}

    /* Three-Step Flow */
    .steps-row {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 20px;
      padding-top: 14px;
      border-top: 1px solid var(--color-panel-border);
      height: 90px;
    }}

    .step-item {{
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}

    .step-header {{
      display: flex;
      align-items: baseline;
      gap: 8px;
    }}

    .step-num {{
      font-family: var(--font-headline);
      font-size: 14px;
      font-weight: 700;
      color: var(--color-gold);
      letter-spacing: 0.05em;
    }}

    .step-label {{
      font-family: var(--font-headline);
      font-size: 18px;
      font-weight: 700;
      color: var(--color-vanilla);
    }}

    .step-text {{
      font-family: var(--font-body);
      font-size: 13px;
      font-weight: 400;
      line-height: 1.38;
      color: var(--color-text-dim);
    }}

    /* RIGHT 55% COLUMN: Device Frames (Monitor + Overlapping Phones) */
    .preview-column {{
      width: 940px;
      height: 520px;
      position: relative;
    }}

    /* Monitor Device Frame (CSS Shapes) */
    .monitor-frame {{
      position: absolute;
      top: 12px;
      left: 125px;
      width: 690px;
      background-color: var(--color-panel);
      border: 1px solid var(--color-panel-border);
      border-radius: 12px;
      padding: 10px 10px 16px 10px;
      z-index: 1;
    }}

    .monitor-screen {{
      width: 668px;
      height: 376px;
      background-color: #0c0d10;
      border: 1px solid var(--color-panel-border);
      border-radius: 6px;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
    }}

    .monitor-chin {{
      display: flex;
      justify-content: center;
      align-items: center;
      margin-top: 8px;
      height: 6px;
    }}

    .monitor-led {{
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background-color: var(--color-gold);
    }}

    .monitor-stand-neck {{
      width: 60px;
      height: 24px;
      background-color: var(--color-panel);
      border-left: 1px solid var(--color-panel-border);
      border-right: 1px solid var(--color-panel-border);
      margin: 0 auto;
    }}

    .monitor-stand-base {{
      width: 180px;
      height: 8px;
      background-color: var(--color-panel);
      border: 1px solid var(--color-panel-border);
      border-radius: 4px;
      margin: 0 auto;
    }}

    /* Overlapping Phones (CSS Shapes, Left & Right Flanks) */
    .phone-frame {{
      position: absolute;
      top: 145px;
      width: 180px;
      height: 355px;
      background-color: var(--color-panel);
      border: 1px solid var(--color-panel-border);
      border-radius: 26px;
      padding: 8px 8px 10px 8px;
    }}

    .phone-admin {{
      left: 15px;
      z-index: 3;
    }}

    .phone-public {{
      right: 15px;
      z-index: 4;
    }}

    .phone-island {{
      width: 50px;
      height: 10px;
      background-color: #0c0d10;
      border-radius: 5px;
      margin: 2px auto 6px auto;
    }}

    .phone-screen {{
      width: 162px;
      height: 320px;
      background-color: #0c0d10;
      border: 1px solid var(--color-panel-border);
      border-radius: 18px;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
    }}

    /* Screenshot Images */
    .device-img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}

    /* Grey Placeholder Boxes for Missing Screenshots */
    .screen-placeholder {{
      width: 100%;
      height: 100%;
      background-color: #161512;
      border: 1px dashed rgba(176, 141, 87, 0.4);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 14px;
      text-align: center;
      gap: 6px;
    }}

    .placeholder-badge {{
      font-family: var(--font-body);
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--color-gold);
    }}

    .placeholder-filename {{
      font-family: var(--font-headline);
      font-size: 14px;
      font-weight: 700;
      color: var(--color-vanilla);
      word-break: break-all;
    }}

    .placeholder-hint {{
      font-family: var(--font-body);
      font-size: 11px;
      font-weight: 400;
      color: var(--color-text-dim);
      line-height: 1.35;
      max-width: 210px;
    }}

    /* Device Caption Badges */
    .device-badge {{
      position: absolute;
      top: -11px;
      left: 18px;
      background-color: var(--color-panel);
      border: 1px solid var(--color-panel-border);
      border-radius: 3px;
      padding: 2px 8px;
      font-family: var(--font-body);
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--color-gold);
      z-index: 5;
    }}

    /* BOTTOM STRIP: Five Feature Points in One Row (>= 28px text) */
    .features-strip {{
      width: 1760px;
      height: 100px;
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 28px;
      border-top: 1px solid var(--color-panel-border);
      padding-top: 14px;
    }}

    .feature-point {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      border-top: 2px solid var(--color-gold);
      padding-top: 10px;
    }}

    .feature-index {{
      font-family: var(--font-headline);
      font-size: 13px;
      font-weight: 700;
      color: var(--color-gold);
      letter-spacing: 0.05em;
    }}

    .feature-text {{
      font-family: var(--font-headline);
      font-size: 28px;
      font-weight: 600;
      line-height: 1.15;
      color: var(--color-vanilla);
      letter-spacing: -0.015em;
    }}

    /* FOOTER STRIP (236px height to accommodate 220px QR code cleanly) */
    .poster-footer {{
      width: 1760px;
      height: 236px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-top: 1px solid var(--color-panel-border);
      padding-top: 12px;
    }}

    .footer-credits {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}

    .credit-main {{
      font-family: var(--font-body);
      font-size: 20px;
      font-weight: 400;
      color: var(--color-vanilla);
      letter-spacing: -0.01em;
    }}

    .credit-highlight {{
      color: var(--color-gold);
      font-weight: 700;
    }}

    .credit-sep {{
      color: var(--color-gold);
      margin: 0 8px;
      opacity: 0.7;
    }}

    .credit-sub {{
      font-family: var(--font-body);
      font-size: 15px;
      font-weight: 400;
      color: var(--color-text-dim);
    }}

    /* QR Code Group */
    .footer-qr-group {{
      display: flex;
      align-items: center;
      gap: 24px;
    }}

    .qr-text-block {{
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 4px;
      text-align: right;
    }}

    .qr-live-label {{
      font-family: var(--font-body);
      font-size: 14px;
      font-weight: 600;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--color-gold);
    }}

    .qr-url {{
      font-family: var(--font-headline);
      font-size: 24px;
      font-weight: 700;
      color: var(--color-vanilla);
      letter-spacing: -0.01em;
    }}

    .qr-hint {{
      font-family: var(--font-body);
      font-size: 13px;
      font-weight: 400;
      color: var(--color-text-dim);
    }}

    .qr-image-wrapper {{
      width: 220px;
      height: 220px;
      background-color: #FFFFFF;
      border: 1px solid var(--color-panel-border);
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 6px;
      flex-shrink: 0;
    }}

    .qr-image {{
      width: 208px;
      height: 208px;
      display: block;
      image-rendering: pixelated;
    }}
  </style>
</head>
<body>
  <div class="poster-canvas">

    <!-- TOP SECTION: Asymmetric Grid (Left 45%, Right 55%) -->
    <div class="poster-main">

      <!-- LEFT COLUMN -->
      <div class="hero-column">
        <!-- Logo Row -->
        <div class="brand-row">
          <svg class="brand-logo" viewBox="0 0 500 500" width="40" height="40" fill="none" aria-label="V Notice Logo">
            <g transform="translate(70, 70)">
              <path d="M40 35 H245 L325 115 V345 H40 Z" fill="#EEEBDA"/>
              <path d="M245 35 V115 H325 Z" fill="#B08D57"/>
              <path d="M82 112 H128 L182 260 L236 112 H282 L205 315 H159 Z" fill="#111318"/>
              <path d="M82 342 H282" stroke="#B08D57" stroke-width="8" stroke-linecap="square"/>
            </g>
          </svg>
          <span class="brand-name">V Notice</span>
        </div>

        <!-- Eyebrow -->
        <div class="eyebrow">Smart campus notice board</div>

        <!-- Headline (92px) -->
        <h1 class="headline">Every notice.<br>Every screen.<br>In seconds.</h1>

        <!-- Subline -->
        <p class="subline">
          V Notice lets any department publish to its own display from a phone, and lets students take the notice with them by scanning a QR code.
        </p>

        <!-- Three-Step Flow -->
        <div class="steps-row">
          <div class="step-item">
            <div class="step-header">
              <span class="step-num">01</span>
              <span class="step-label">Post</span>
            </div>
            <p class="step-text">Write, upload an image, video or voice message from any phone in about 30 seconds.</p>
          </div>
          <div class="step-item">
            <div class="step-header">
              <span class="step-num">02</span>
              <span class="step-label">Show</span>
            </div>
            <p class="step-text">Department screens update live. Urgent notices take over the display.</p>
          </div>
          <div class="step-item">
            <div class="step-header">
              <span class="step-num">03</span>
              <span class="step-label">Scan</span>
            </div>
            <p class="step-text">Students scan the QR code to read or save the notice on their phone.</p>
          </div>
        </div>
      </div>

      <!-- RIGHT COLUMN: CSS Device Frames -->
      <div class="preview-column">

        <!-- Monitor Frame (Display Kiosk) -->
        <div class="monitor-frame">
          <div class="device-badge">Campus Display</div>
          <div class="monitor-screen">
            {"<img src='screens/display-1080p.png' alt='Kiosk Display' class='device-img'>" if has_display else """
            <div class="screen-placeholder">
              <span class="placeholder-badge">Screen 1 of 3 · Display</span>
              <span class="placeholder-filename">display-1080p.png</span>
              <p class="placeholder-hint">Add 1920×1080 kiosk screenshot to poster/screens/display-1080p.png</p>
            </div>
            """}
          </div>
          <div class="monitor-chin">
            <div class="monitor-led"></div>
          </div>
        </div>
        <div class="monitor-stand-neck" style="position: absolute; top: 426px; left: 440px; z-index: 0;"></div>
        <div class="monitor-stand-base" style="position: absolute; top: 450px; left: 370px; width: 200px; height: 10px; z-index: 0;"></div>

        <!-- Phone 1: Admin Mobile -->
        <div class="phone-frame phone-admin">
          <div class="device-badge">Admin</div>
          <div class="phone-island"></div>
          <div class="phone-screen">
            {"<img src='screens/admin-mobile.png' alt='Admin Mobile' class='device-img'>" if has_admin else """
            <div class="screen-placeholder">
              <span class="placeholder-badge">Screen 2 of 3</span>
              <span class="placeholder-filename">admin-mobile.png</span>
              <p class="placeholder-hint">Add notices list to poster/screens/admin-mobile.png</p>
            </div>
            """}
          </div>
        </div>

        <!-- Phone 2: Public Mobile -->
        <div class="phone-frame phone-public">
          <div class="device-badge">Public Page</div>
          <div class="phone-island"></div>
          <div class="phone-screen">
            {"<img src='screens/public-mobile.png' alt='Public Page Mobile' class='device-img'>" if has_public else """
            <div class="screen-placeholder">
              <span class="placeholder-badge">Screen 3 of 3</span>
              <span class="placeholder-filename">public-mobile.png</span>
              <p class="placeholder-hint">Add QR notice view to poster/screens/public-mobile.png</p>
            </div>
            """}
          </div>
        </div>

      </div>

    </div>

    <!-- BOTTOM STRIP: Five Feature Points in One Row (>= 28px text) -->
    <div class="features-strip">
      <div class="feature-point">
        <span class="feature-index">01</span>
        <div class="feature-text">Screen for every department</div>
      </div>
      <div class="feature-point">
        <span class="feature-index">02</span>
        <div class="feature-text">Image, video, voice and text notices</div>
      </div>
      <div class="feature-point">
        <span class="feature-index">03</span>
        <div class="feature-text">Scheduled start and expiry</div>
      </div>
      <div class="feature-point">
        <span class="feature-index">04</span>
        <div class="feature-text">Works offline on a Raspberry Pi</div>
      </div>
      <div class="feature-point">
        <span class="feature-index">05</span>
        <div class="feature-text">Daily national flag screen</div>
      </div>
    </div>

    <!-- FOOTER STRIP -->
    <footer class="poster-footer">
      <div class="footer-credits">
        <div class="credit-main">
          Built at <strong class="credit-highlight">VIT</strong> by <strong class="credit-highlight">Team Anrix</strong> <span class="credit-sep">|</span> Guided by <strong class="credit-highlight">Manoj Suryawanshi Sir</strong>
        </div>
        <div class="credit-sub">
          Digital signage platform designed for academic institutions
        </div>
      </div>

      <div class="footer-qr-group">
        <div class="qr-text-block">
          <div class="qr-live-label">Try it live</div>
          <div class="qr-url">v-notice.onrender.com/admin</div>
          <div class="qr-hint">Scan with your phone camera</div>
        </div>
        <div class="qr-image-wrapper">
          <img class="qr-image" src="data:image/png;base64,{qr_b64}" alt="QR Code: https://v-notice.onrender.com/admin" width="208" height="208">
        </div>
      </div>
    </footer>

  </div>
</body>
</html>
"""

    index_path = poster_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    print(f"[OK] Wrote poster HTML: {index_path} ({len(html)} chars)")
    return index_path

if __name__ == "__main__":
    generate_poster()
