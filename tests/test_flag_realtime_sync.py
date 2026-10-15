import os
import sys
import time
import datetime
import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from storage import NoticeStorage, KOLKATA_TZ

ADMIN_PWD = getattr(config, "ADMIN_PASSWORD", "vnotice2026")
SERVER_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "notices.db")
server_storage = NoticeStorage(db_file=SERVER_DB_PATH)

def login_admin(admin_page):
    """Log into admin portal and switch to Settings tab."""
    admin_page.goto("http://localhost:5001/", wait_until="networkidle")
    if admin_page.is_visible("#login-modal"):
        admin_page.fill("#admin-password-input", ADMIN_PWD)
        admin_page.click("#btn-login")
        admin_page.wait_for_timeout(500)
    admin_page.evaluate("() => window.switchTab('settings')")
    admin_page.wait_for_selector("#settings-card-flag-event", state="visible", timeout=5000)

def set_admin_flag_settings(admin_page, enabled=True, start_time="11:00", duration=60, days=None):
    """Fill and save flag settings via the admin UI form."""
    admin_page.evaluate("""({ enabled, start_time, duration, days }) => {
        const sw = document.getElementById('flag-enabled-switch');
        if (sw) sw.checked = enabled;
        const st = document.getElementById('flag-start-time');
        if (st) st.value = start_time;
        const dur = document.getElementById('flag-duration');
        if (dur) dur.value = String(duration);
        if (Array.isArray(days)) {
            document.querySelectorAll("input[name='flag_day']").forEach(cb => {
                cb.checked = days.includes(cb.value);
            });
        }
    }""", {"enabled": enabled, "start_time": start_time, "duration": duration, "days": days or ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]})
    admin_page.click("#btn-save-flag-settings")
    admin_page.wait_for_timeout(600)

# ==============================================================================
# TESTS (Playwright, fake clock, display open and never reloaded)
# ==============================================================================

def test_show_flag_now_and_end_flag_now_within_4s():
    """
    Playwright test:
    - Display open and never reloaded.
    - Click Show flag now in admin: the flag appears on the display within 4 s.
    - Click End flag now: the rotation returns within 4 s.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Open display page
        display_page = browser.new_page(viewport={"width": 1920, "height": 1080})
        display_page.goto("http://localhost:5000/display/ALL", wait_until="networkidle")
        display_page.wait_for_selector(".display-header", state="visible", timeout=5000)

        # Clear any overrides initially
        server_storage.clear_flag_manual_override(ended_early=False)

        # Open admin in separate page
        admin_page = browser.new_page(viewport={"width": 1440, "height": 900})
        login_admin(admin_page)

        # Verify display is in normal rotation
        assert not display_page.is_visible("#flag-overlay:not(.hidden)")

        # 1. Click Show flag now
        t0 = time.time()
        admin_page.click("#btn-flag-show-now")

        # Must appear within 4 seconds
        display_page.wait_for_selector("body.flag-active", state="attached", timeout=4000)
        display_page.wait_for_selector("#flag-screen", state="visible", timeout=4000)
        elapsed_show = time.time() - t0
        assert elapsed_show <= 4.0, f"Show flag took {elapsed_show:.2f}s, must be <= 4.0s"

        # 2. Click End flag now
        t1 = time.time()
        admin_page.click("#btn-flag-end-now")

        # Rotation returns within 4 seconds
        display_page.wait_for_selector("#flag-overlay.hidden", state="attached", timeout=4000)
        display_page.wait_for_selector("body:not(.flag-active)", state="attached", timeout=4000)
        elapsed_end = time.time() - t1
        assert elapsed_end <= 4.0, f"End flag took {elapsed_end:.2f}s, must be <= 4.0s"
        assert display_page.is_visible(".display-header")

        browser.close()

def test_run_now_for_20s_resumes_by_itself():
    """
    Playwright test:
    - Display open and never reloaded.
    - Run now for 20 s: flag appears, then rotation resumes by itself.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        display_page = browser.new_page(viewport={"width": 1920, "height": 1080})
        display_page.goto("http://localhost:5000/display/ALL", wait_until="networkidle")
        display_page.wait_for_selector(".display-header", state="visible", timeout=5000)

        server_storage.clear_flag_manual_override(ended_early=False)

        admin_page = browser.new_page(viewport={"width": 1440, "height": 900})
        login_admin(admin_page)

        # Configure 20s in duration input and click Run now
        admin_page.fill("#flag-duration", "20")
        admin_page.click("#btn-flag-run-now")
        admin_page.wait_for_selector("#flag-confirm-modal:not(.hidden)", state="visible", timeout=3000)
        admin_page.click("#btn-proceed-flag-confirm")

        # Flag appears on display within 4s
        display_page.wait_for_selector("body.flag-active", state="attached", timeout=4000)
        display_page.wait_for_selector("#flag-screen", state="visible", timeout=4000)

        # After 20 seconds duration expires, rotation resumes by itself
        display_page.wait_for_selector("#flag-overlay.hidden", state="attached", timeout=26000)
        display_page.wait_for_selector("body:not(.flag-active)", state="attached", timeout=4000)
        assert display_page.is_visible(".display-header")

        browser.close()

def advance_to_time(page, target_ms):
    now = page.evaluate("() => Date.now()")
    diff = target_ms - now
    if diff > 0:
        page.clock.run_for(diff)

def test_schedule_run_2_minutes_ahead_after_display_loaded():
    """
    Playwright test with fake clock:
    - Display open and never reloaded.
    - Schedule a run 2 minutes ahead after display loaded.
    - Flag appears at the right second without a refresh.
    """
    # Thursday 2026-10-15 10:58:00 IST
    sim_base = datetime.datetime(2026, 10, 15, 10, 58, 0, tzinfo=KOLKATA_TZ)
    target_start_ms = int(datetime.datetime(2026, 10, 15, 11, 0, 0, tzinfo=KOLKATA_TZ).timestamp() * 1000)
    target_end_ms = target_start_ms + 60000

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        display_page = browser.new_page(viewport={"width": 1920, "height": 1080})
        display_page.clock.install(time=sim_base)

        def handle_route(route):
            fake_now = display_page.evaluate("() => Date.now()")
            headers = dict(route.request.headers)
            headers["X-Simulated-Now"] = str(int(fake_now))
            route.continue_(headers=headers)

        display_page.route("**/api/events/today*", handle_route)
        display_page.goto("http://localhost:5000/display/ALL", wait_until="networkidle")

        admin_page = browser.new_page(viewport={"width": 1440, "height": 900})
        login_admin(admin_page)

        # Schedule flag 2 minutes ahead (11:00) with 60s duration
        server_storage.clear_flag_manual_override(ended_early=False)
        set_admin_flag_settings(admin_page, enabled=True, start_time="11:00", duration=60, days=["thu"])

        # Display polls and receives new schedule without reload
        for _ in range(10):
            sched = display_page.evaluate("() => flagScheduler ? flagScheduler.getSchedule() : null")
            if sched and sched.get("flag_start_ms") == target_start_ms:
                break
            display_page.clock.run_for(1000)
        assert display_page.evaluate("() => flagScheduler ? flagScheduler.getSchedule() : null")["flag_start_ms"] == target_start_ms

        # At 10:59:58 (2s before start): still in rotation
        advance_to_time(display_page, target_start_ms - 2000)
        assert not display_page.evaluate("() => document.body.classList.contains('flag-active')")

        # Advance to 11:00:00 (tick loop 250ms): flag appears at right second!
        advance_to_time(display_page, target_start_ms + 500)
        is_flag = display_page.evaluate("() => document.body.classList.contains('flag-active') && !document.getElementById('flag-screen').classList.contains('hidden')")
        assert is_flag is True, "Flag must appear at the exact second without a refresh"

        # Advance past end: rotation resumes
        advance_to_time(display_page, target_end_ms + 1000)
        is_rotation = display_page.evaluate("() => !document.body.classList.contains('flag-active') && document.getElementById('flag-overlay').classList.contains('hidden')")
        assert is_rotation is True, "Rotation must resume automatically after duration"

        browser.close()

def test_edit_start_time_while_display_is_open():
    """
    Playwright test with fake clock:
    - Display open and never reloaded.
    - Edit the start time while the display is open: the new time is honored.
    """
    sim_base = datetime.datetime(2026, 10, 15, 10, 58, 0, tzinfo=KOLKATA_TZ)
    target_new_start_ms = int(datetime.datetime(2026, 10, 15, 11, 5, 0, tzinfo=KOLKATA_TZ).timestamp() * 1000)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        display_page = browser.new_page(viewport={"width": 1920, "height": 1080})
        display_page.clock.install(time=sim_base)

        def handle_route(route):
            fake_now = display_page.evaluate("() => Date.now()")
            headers = dict(route.request.headers)
            headers["X-Simulated-Now"] = str(int(fake_now))
            route.continue_(headers=headers)

        display_page.route("**/api/events/today*", handle_route)
        display_page.goto("http://localhost:5000/display/ALL", wait_until="networkidle")

        admin_page = browser.new_page(viewport={"width": 1440, "height": 900})
        login_admin(admin_page)

        # Initial schedule at 11:00
        server_storage.clear_flag_manual_override(ended_early=False)
        set_admin_flag_settings(admin_page, enabled=True, start_time="11:00", duration=60, days=["thu"])
        display_page.clock.run_for(3500)

        # While display is open, admin edits start time to 11:05
        set_admin_flag_settings(admin_page, enabled=True, start_time="11:05", duration=60, days=["thu"])
        display_page.clock.run_for(3500)

        # Advance time to 11:01:00 (past old 11:00 time): flag must NOT appear
        advance_to_time(display_page, target_new_start_ms - 240000)
        assert not display_page.evaluate("() => document.body.classList.contains('flag-active')"), "Must not appear at old 11:00 time"

        # Advance time to 11:05:00: flag appears at the new time!
        advance_to_time(display_page, target_new_start_ms + 500)
        is_flag_new = display_page.evaluate("() => document.body.classList.contains('flag-active') && !document.getElementById('flag-screen').classList.contains('hidden')")
        assert is_flag_new is True, "Flag must appear at the newly updated 11:05 time"

        browser.close()

def test_daily_schedule_two_consecutive_simulated_days_without_reload():
    """
    Playwright test with fake clock:
    - Display open and never reloaded across 2 consecutive simulated days.
    - Both days show the flag.
    """
    sim_base = datetime.datetime(2026, 10, 15, 10, 58, 0, tzinfo=KOLKATA_TZ)
    day1_start_ms = int(datetime.datetime(2026, 10, 15, 11, 0, 0, tzinfo=KOLKATA_TZ).timestamp() * 1000)
    day1_end_ms = day1_start_ms + 60000

    day2_start_ms = int(datetime.datetime(2026, 10, 16, 11, 0, 0, tzinfo=KOLKATA_TZ).timestamp() * 1000)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        display_page = browser.new_page(viewport={"width": 1920, "height": 1080})
        display_page.clock.install(time=sim_base)

        def handle_route(route):
            fake_now = display_page.evaluate("() => Date.now()")
            headers = dict(route.request.headers)
            headers["X-Simulated-Now"] = str(int(fake_now))
            route.continue_(headers=headers)

        display_page.route("**/api/events/today*", handle_route)
        display_page.goto("http://localhost:5000/display/ALL", wait_until="networkidle")

        admin_page = browser.new_page(viewport={"width": 1440, "height": 900})
        login_admin(admin_page)

        # Set schedule active on both Thursday and Friday
        server_storage.clear_flag_manual_override(ended_early=False)
        set_admin_flag_settings(admin_page, enabled=True, start_time="11:00", duration=60, days=["thu", "fri"])

        # Day 1: sync and advance to 11:00:00
        for _ in range(10):
            sched = display_page.evaluate("() => flagScheduler ? flagScheduler.getSchedule() : null")
            if sched and sched.get("flag_start_ms") == day1_start_ms:
                break
            display_page.clock.run_for(1000)
        advance_to_time(display_page, day1_start_ms + 500)
        day1_flag = display_page.evaluate("() => document.body.classList.contains('flag-active') && !document.getElementById('flag-screen').classList.contains('hidden')")
        assert day1_flag is True, "Day 1 flag must appear at 11:00"

        # Day 1 flag finishes, rotation resumes
        advance_to_time(display_page, day1_end_ms + 1000)
        assert not display_page.evaluate("() => document.body.classList.contains('flag-active')")

        # Jump directly to Day 2 at 10:58:00 (Friday 2026-10-16) without reloading display!
        day2_base = datetime.datetime(2026, 10, 16, 10, 58, 0, tzinfo=KOLKATA_TZ)
        display_page.clock.set_system_time(day2_base)

        # Display polls and arms Day 2 schedule
        for _ in range(10):
            sched = display_page.evaluate("() => flagScheduler ? flagScheduler.getSchedule() : null")
            if sched and sched.get("flag_start_ms") == day2_start_ms:
                break
            display_page.clock.run_for(1000)

        # Advance to 11:00:00 on Day 2
        advance_to_time(display_page, day2_start_ms + 500)
        day2_flag = display_page.evaluate("() => document.body.classList.contains('flag-active') && !document.getElementById('flag-screen').classList.contains('hidden')")
        assert day2_flag is True, "Day 2 flag must appear at 11:00 on the second consecutive day without reload"

        browser.close()

def test_kiosk_still_works_offline():
    """
    Playwright test:
    - The kiosk still works offline using the last known schedule and clock offset.
    """
    sim_base = datetime.datetime(2026, 10, 15, 10, 58, 0, tzinfo=KOLKATA_TZ)
    target_start_ms = int(datetime.datetime(2026, 10, 15, 11, 0, 0, tzinfo=KOLKATA_TZ).timestamp() * 1000)
    target_end_ms = target_start_ms + 60000

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        display_page = context.new_page()
        display_page.clock.install(time=sim_base)

        def handle_route(route):
            fake_now = display_page.evaluate("() => Date.now()")
            headers = dict(route.request.headers)
            headers["X-Simulated-Now"] = str(int(fake_now))
            route.continue_(headers=headers)

        display_page.route("**/api/events/today*", handle_route)
        display_page.goto("http://localhost:5000/display/ALL", wait_until="networkidle")

        admin_page = browser.new_page(viewport={"width": 1440, "height": 900})
        login_admin(admin_page)

        # Arm schedule at 11:00
        server_storage.clear_flag_manual_override(ended_early=False)
        set_admin_flag_settings(admin_page, enabled=True, start_time="11:00", duration=60, days=["thu"])

        # Display fetches while online and caches in localStorage
        for _ in range(10):
            sched = display_page.evaluate("() => flagScheduler ? flagScheduler.getSchedule() : null")
            if sched and sched.get("flag_start_ms") == target_start_ms:
                break
            display_page.clock.run_for(1000)

        # Disconnect network completely (offline mode)
        context.set_offline(True)

        # Advance time to 11:00:00 while offline
        advance_to_time(display_page, target_start_ms + 500)

        # Flag appears on time offline using last known schedule & clock offset!
        is_offline_flag = display_page.evaluate("() => document.body.classList.contains('flag-active') && !document.getElementById('flag-screen').classList.contains('hidden')")
        assert is_offline_flag is True, "Kiosk must show flag on time even when completely offline"

        # Advance past duration: rotation resumes offline
        advance_to_time(display_page, target_end_ms + 1000)
        is_offline_rotation = display_page.evaluate("() => !document.body.classList.contains('flag-active') && document.getElementById('flag-overlay').classList.contains('hidden')")
        assert is_offline_rotation is True, "Kiosk rotation must resume offline when flag finishes"

        browser.close()

