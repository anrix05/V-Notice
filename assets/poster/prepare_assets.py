import os
import sys
import base64
import json
from pathlib import Path
import zxingcpp
import numpy as np
import PIL.Image

def main():
    poster_dir = Path("poster")
    poster_dir.mkdir(parents=True, exist_ok=True)
    screens_dir = poster_dir / "screens"
    screens_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate QR code
    target_url = "https://v-notice.onrender.com"
    barcode = zxingcpp.create_barcode(target_url, zxingcpp.BarcodeFormat.QRCode, ec_level="M")
    qr_img = zxingcpp.write_barcode_to_image(barcode, scale=8, add_quiet_zones=True)
    qr_pil = PIL.Image.fromarray(np.array(qr_img, copy=False))
    qr_path = poster_dir / "qr.png"
    qr_pil.save(qr_path)
    print(f"[OK] Generated QR code: {qr_path} (size: {qr_pil.size})")

    # Verify decode
    qr_read = zxingcpp.read_barcode(qr_pil)
    assert qr_read.text == target_url, f"QR decode failed: {qr_read.text} != {target_url}"
    print(f"[OK] Verified QR decode: {qr_read.text}")

    # Read QR as base64 for standalone HTML embedding
    with open(qr_path, "rb") as f:
        qr_b64 = base64.b64encode(f.read()).decode("ascii")

    # 2. Read font files
    font_b64 = {}
    for name in ["Outfit-Bold", "Outfit-Regular", "Inter-Bold", "Inter-Regular"]:
        font_path = Path(f"static/fonts/{name}.woff2")
        if font_path.exists():
            with open(font_path, "rb") as f:
                font_b64[name] = base64.b64encode(f.read()).decode("ascii")
            print(f"[OK] Loaded local font {name}")
        else:
            print(f"[WARN] Local font {name} not found")

    # 3. Check for screenshots in poster/screens/
    expected_screens = {
        "display-1080p.png": "1920×1080 kiosk display with image or video notice",
        "admin-mobile.png": "Notices list or New notice sheet on mobile",
        "public-mobile.png": "Public notice page with QR scan view on mobile"
    }

    screen_status = {}
    for filename, desc in expected_screens.items():
        p = screens_dir / filename
        exists = p.is_file() and p.stat().st_size > 0
        screen_status[filename] = {
            "exists": exists,
            "path": f"screens/{filename}",
            "desc": desc
        }
        print(f"[{'FOUND' if exists else 'MISSING'}] poster/screens/{filename}")

    return qr_b64, font_b64, screen_status

if __name__ == "__main__":
    main()
