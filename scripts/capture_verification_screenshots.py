import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image, ImageChops

OUTPUT_DIR = Path(r"C:\Users\pbclu\.gemini\antigravity-ide\brain\7f7d6ca2-2857-4e4b-8eff-d549dc5377db\verification_after")
BEFORE_DIR = Path(r"C:\Users\pbclu\.gemini\antigravity-ide\brain\7f7d6ca2-2857-4e4b-8eff-d549dc5377db\baseline_before")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DISPLAY_URL = "http://localhost:5000"
ADMIN_URL = "http://localhost:5001"
PASSWORD = "vnotice2026"

def capture():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # 1. Display 1920x1080
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(f"{DISPLAY_URL}/display/ALL")
        page.wait_for_selector("#display-header-logo", state="visible")
        # Freeze animations/time for stability
        time.sleep(1.0)
        page.screenshot(path=str(OUTPUT_DIR / "after_display_1920.png"))
        print("Captured after_display_1920.png")
        page.close()

        # 2. Display 800x480
        page = browser.new_page(viewport={"width": 800, "height": 480})
        page.goto(f"{DISPLAY_URL}/display/ALL")
        page.wait_for_selector("#display-header-logo", state="visible")
        time.sleep(1.0)
        page.screenshot(path=str(OUTPUT_DIR / "after_display_800.png"))
        print("Captured after_display_800.png")
        page.close()

        # 3. Admin Login Card (Logged out)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{ADMIN_URL}/")
        # Ensure logged out
        page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch(e){} }")
        page.reload()
        page.wait_for_selector(".auth-card", state="visible")
        time.sleep(0.5)
        page.screenshot(path=str(OUTPUT_DIR / "after_admin_login.png"))
        print("Captured after_admin_login.png")

        # 4. Admin Dashboard (Logged in)
        page.fill("#admin-password-input", PASSWORD)
        page.click("#login-form button[type='submit']")
        page.wait_for_selector("#notices-table, .notice-card, .sidebar-brand", state="visible", timeout=10000)
        time.sleep(1.0)
        page.screenshot(path=str(OUTPUT_DIR / "after_admin.png"))
        print("Captured after_admin.png")
        page.close()

        # 5. Public Notice View
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{DISPLAY_URL}/n/ETHkPjylc1Y")
        page.wait_for_selector(".brand-group", state="visible")
        time.sleep(0.5)
        page.screenshot(path=str(OUTPUT_DIR / "after_public_notice.png"))
        print("Captured after_public_notice.png")
        page.close()

        browser.close()

def generate_comparisons():
    pairs = [
        ("display_1920", "before_display_1920.png", "after_display_1920.png"),
        ("display_800", "before_display_800.png", "after_display_800.png"),
        ("admin", "before_admin.png", "after_admin.png"),
        ("admin_login", "before_admin_login.png", "after_admin_login.png"),
        ("public_notice", "before_public_notice.png", "after_public_notice.png"),
    ]

    for name, before_name, after_name in pairs:
        b_path = BEFORE_DIR / before_name
        a_path = OUTPUT_DIR / after_name
        if not b_path.exists() or not a_path.exists():
            continue

        img_b = Image.open(b_path).convert("RGB")
        img_a = Image.open(a_path).convert("RGB")

        # Resize img_b if sizes differ slightly
        if img_b.size != img_a.size:
            img_b = img_b.resize(img_a.size)

        w, h = img_a.size
        # Side by side: Before | After
        comparison = Image.new("RGB", (w * 2, h))
        comparison.paste(img_b, (0, 0))
        comparison.paste(img_a, (w, 0))
        comp_path = OUTPUT_DIR / f"compare_{name}.png"
        comparison.save(str(comp_path))
        print(f"Generated side-by-side: {comp_path.name}")

if __name__ == "__main__":
    capture()
    generate_comparisons()
    print("All verification screenshots and comparisons generated!")
