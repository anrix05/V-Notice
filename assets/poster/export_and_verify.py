import os
import sys
import math
from pathlib import Path
from playwright.sync_api import sync_playwright
import PIL.Image
import pymupdf
import zxingcpp

def calculate_luminance(rgb_hex_or_tuple):
    if isinstance(rgb_hex_or_tuple, str):
        hex_str = rgb_hex_or_tuple.lstrip("#")
        r, g, b = tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    else:
        r, g, b = rgb_hex_or_tuple[:3]

    def channel_lum(val):
        v = val / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel_lum(r) + 0.7152 * channel_lum(g) + 0.0722 * channel_lum(b)

def contrast_ratio(lum1, lum2):
    brightest = max(lum1, lum2)
    darkest = min(lum1, lum2)
    return (brightest + 0.05) / (darkest + 0.05)

def parse_rgb_str(s):
    # Parses rgb(17, 19, 24) or rgba(238, 235, 218, 0.8)
    import re
    nums = [float(x) for x in re.findall(r"[\d.]+", s)]
    if len(nums) >= 3:
        return (int(nums[0]), int(nums[1]), int(nums[2]))
    return (0, 0, 0)

def main():
    poster_dir = Path("poster").resolve()
    html_file = poster_dir / "index.html"
    png_file = poster_dir / "poster.png"
    pdf_file = poster_dir / "poster.pdf"

    if not html_file.exists():
        print(f"[FAIL] {html_file} does not exist!")
        sys.exit(1)

    print("==================================================")
    print("V NOTICE POSTER: EXPORT & VERIFICATION AUDIT")
    print("==================================================")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Viewport: 1920x1080 with device_scale_factor=2 produces exact 3840x2160 pixels
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2
        )
        page = context.new_page()

        file_url = html_file.as_uri()
        page.goto(file_url, wait_until="networkidle")

        # 1. Overflow & Layout Verification
        overflow_info = page.evaluate("""() => {
            const body = document.body;
            const docEl = document.documentElement;
            const canvas = document.querySelector('.poster-canvas');
            return {
                scrollWidth: docEl.scrollWidth,
                scrollHeight: docEl.scrollHeight,
                clientWidth: docEl.clientWidth,
                clientHeight: docEl.clientHeight,
                canvasWidth: canvas ? canvas.offsetWidth : 0,
                canvasHeight: canvas ? canvas.offsetHeight : 0,
            };
        }""")

        print(f"[CHECK] Viewport Dimensions: {overflow_info['clientWidth']} x {overflow_info['clientHeight']}")
        print(f"[CHECK] Scroll Dimensions: {overflow_info['scrollWidth']} x {overflow_info['scrollHeight']}")
        print(f"[CHECK] Canvas Dimensions: {overflow_info['canvasWidth']} x {overflow_info['canvasHeight']}")

        assert overflow_info['scrollWidth'] <= overflow_info['clientWidth'], "Horizontal overflow detected!"
        assert overflow_info['scrollHeight'] <= overflow_info['clientHeight'], "Vertical overflow detected!"
        print("[PASS] Zero horizontal and vertical overflow at 1920x1080.")

        # 2. Typography & Text Hierarchy Check
        typo_info = page.evaluate("""() => {
            const h1 = document.querySelector('.headline');
            const h1Style = window.getComputedStyle(h1);
            const sub = document.querySelector('.subline');
            const subStyle = window.getComputedStyle(sub);
            const feature = document.querySelector('.feature-text');
            const featureStyle = window.getComputedStyle(feature);
            const qrUrl = document.querySelector('.qr-url');
            const qrUrlStyle = window.getComputedStyle(qrUrl);
            const bodyStyle = window.getComputedStyle(document.body);

            return {
                headlineFontSize: parseFloat(h1Style.fontSize),
                headlineColor: h1Style.color,
                sublineFontSize: parseFloat(subStyle.fontSize),
                sublineColor: subStyle.color,
                featureFontSize: parseFloat(featureStyle.fontSize),
                featureColor: featureStyle.color,
                qrUrlFontSize: parseFloat(qrUrlStyle.fontSize),
                bgColor: bodyStyle.backgroundColor,
                bodyFont: bodyStyle.fontFamily
            };
        }""")

        print(f"[CHECK] Headline font size: {typo_info['headlineFontSize']}px (target ~110px)")
        print(f"[CHECK] Feature text font size: {typo_info['featureFontSize']}px (minimum 28px)")
        assert 96 <= typo_info['headlineFontSize'] <= 120, "Headline font size out of expected range"
        assert typo_info['featureFontSize'] >= 28.0, "Feature text size must be at least 28px!"
        print("[PASS] Typographic scale verified.")

        # 3. Contrast Ratios Check
        bg_rgb = parse_rgb_str(typo_info['bgColor'])
        bg_lum = calculate_luminance(bg_rgb)

        headline_rgb = parse_rgb_str(typo_info['headlineColor'])
        headline_lum = calculate_luminance(headline_rgb)
        headline_contrast = contrast_ratio(headline_lum, bg_lum)

        subline_rgb = parse_rgb_str(typo_info['sublineColor'])
        subline_lum = calculate_luminance(subline_rgb)
        subline_contrast = contrast_ratio(subline_lum, bg_lum)

        feature_rgb = parse_rgb_str(typo_info['featureColor'])
        feature_lum = calculate_luminance(feature_rgb)
        feature_contrast = contrast_ratio(feature_lum, bg_lum)

        print(f"[CONTRAST] Background ({typo_info['bgColor']}): Lum = {bg_lum:.4f}")
        print(f"[CONTRAST] Headline Contrast: {headline_contrast:.2f}:1 (Requirement >= 7.0:1)")
        print(f"[CONTRAST] Subline/Body Contrast: {subline_contrast:.2f}:1 (Requirement >= 4.5:1)")
        print(f"[CONTRAST] Feature Text Contrast: {feature_contrast:.2f}:1 (Requirement >= 4.5:1)")

        assert headline_contrast >= 7.0, f"Headline contrast {headline_contrast:.2f} < 7.0:1"
        assert subline_contrast >= 4.5, f"Subline contrast {subline_contrast:.2f} < 4.5:1"
        assert feature_contrast >= 4.5, f"Feature text contrast {feature_contrast:.2f} < 4.5:1"
        print("[PASS] All WCAG contrast ratio requirements met or exceeded.")

        # 4. Export PNG (3840x2160)
        page.screenshot(path=str(png_file))
        png_im = PIL.Image.open(png_file)
        print(f"[EXPORT] Generated PNG: {png_file} (Dimensions: {png_im.size[0]} x {png_im.size[1]})")
        assert png_im.size == (3840, 2160), f"PNG dimensions {png_im.size} != (3840, 2160)"
        print("[PASS] PNG size is exactly 3840x2160 pixels.")

        # 5. QR Code Scan Test from Exported PNG
        qr_bbox = page.evaluate("""() => {
            const qrWrapper = document.querySelector('.qr-image-wrapper');
            const r = qrWrapper.getBoundingClientRect();
            return { x: r.x * 2, y: r.y * 2, width: r.width * 2, height: r.height * 2 };
        }""")

        qr_crop = png_im.crop((
            int(qr_bbox['x']),
            int(qr_bbox['y']),
            int(qr_bbox['x'] + qr_bbox['width']),
            int(qr_bbox['y'] + qr_bbox['height'])
        ))

        qr_result = zxingcpp.read_barcode(qr_crop)
        if not qr_result:
            # Fallback to reading whole image
            qr_result = zxingcpp.read_barcode(png_im)

        print(f"[QR SCAN] Scanned from rendered poster: '{qr_result.text if qr_result else 'NONE'}'")
        assert qr_result and "v-notice.onrender.com/admin" in qr_result.text, "QR code did not scan or did not match target URL!"
        print(f"[PASS] QR code successfully scanned: {qr_result.text}")

        # 6. Export PDF (16:9 Landscape)
        page.pdf(path=str(pdf_file), width="1920px", height="1080px", print_background=True)
        pdf_doc = pymupdf.open(str(pdf_file))
        page_count = len(pdf_doc)
        rect = pdf_doc[0].rect
        pdf_doc.close()
        ratio = rect.width / rect.height
        print(f"[EXPORT] Generated PDF: {pdf_file} (Pages: {page_count}, Width: {rect.width}pt, Height: {rect.height}pt, Ratio: {ratio:.4f})")
        assert page_count == 1, f"PDF should be a single page, got {page_count}"
        assert math.isclose(ratio, 16/9, rel_tol=1e-3), f"PDF aspect ratio {ratio} != 16:9"
        print("[PASS] PDF is a single 16:9 landscape page.")

        # 7. Screenshot Assets Audit
        screens_dir = poster_dir / "screens"
        expected = ["display-1080p.png", "admin-mobile.png", "public-mobile.png"]
        used_screens = []
        missing_screens = []
        for s in expected:
            sp = screens_dir / s
            if sp.is_file() and sp.stat().st_size > 0:
                used_screens.append(s)
            else:
                missing_screens.append(s)

        print("--------------------------------------------------")
        print("SCREENSHOT ASSETS STATUS:")
        print(f"Used ({len(used_screens)}): {used_screens}")
        print(f"Missing ({len(missing_screens)}): {missing_screens}")
        print("--------------------------------------------------")

        browser.close()

    print("[SUCCESS] ALL VERIFICATIONS PASSED CLEANLY.")

if __name__ == "__main__":
    main()
