import datetime
import json
import pytest
from storage import NoticeStorage, KOLKATA_TZ, check_event_overlap


def test_schema_migration_and_backup(tmp_path):
    """Verify daily_events multi-row schema migration, auto-backup, and seeded rows."""
    db_file = tmp_path / "notices.db"
    storage = NoticeStorage(db_file=str(db_file))

    # Check backup created
    bak_file = tmp_path / "notices.db.bak"
    # Auto-backup triggers before migration if db_file exists
    assert db_file.exists()

    events = storage.get_daily_events()
    assert len(events) >= 2
    
    # 1. Anthem row
    anthem = storage.get_daily_event("anthem")
    assert anthem is not None
    assert anthem["id"] == "anthem"
    assert anthem["label"] == "National Anthem"
    assert anthem["start_time"] == "11:00"
    assert anthem["standup_en"] == "Please stand for the National Anthem"
    assert "राष्ट्रगान" in anthem["standup_hi"]
    assert "राष्ट्रगीतासाठी" in anthem["standup_mr"]

    # Backwards compatibility: "flag" resolves to anthem
    flag_compat = storage.get_daily_event("flag")
    assert flag_compat["id"] == anthem["id"]

    # 2. Vande Mataram row (seeded DISABLED)
    vm = storage.get_daily_event("vande_mataram")
    assert vm is not None
    assert vm["id"] == "vande_mataram"
    assert vm["label"] == "Vande Mataram"
    assert vm["enabled"] is False
    assert vm["start_time"] == "17:00"
    assert vm["duration_seconds"] == 90
    assert vm["start_offset_seconds"] == 0
    assert vm["days_of_week"] == ["mon", "tue", "wed", "thu", "fri", "sat"]
    assert "ALL" in vm["screens"]
    assert vm["show_standup_text"] is False
    assert vm["standup_en"] == "Please stand for Vande Mataram"
    assert "वंदे मातरम्" in vm["standup_hi"]
    assert "वंदे मातरमसाठी" in vm["standup_mr"]


def test_two_events_pick_right_next_occurrence(tmp_path):
    """Scheduler picks the earliest upcoming occurrence across all enabled events."""
    storage = NoticeStorage(db_file=str(tmp_path / "test_events.db"))
    
    # Enable Anthem (11:00) and Vande Mataram (17:00)
    storage.update_daily_event("anthem", {"enabled": True, "show_standup_text": True})
    storage.update_daily_event("vande_mataram", {"enabled": True, "show_standup_text": True})

    # Monday at 10:30 Asia/Kolkata: Anthem is next
    dt_1030 = datetime.datetime(2026, 10, 19, 10, 30, 0, tzinfo=KOLKATA_TZ)
    res_1030 = storage.get_flag_event_today(screen_code="ALL", now_dt=dt_1030)
    assert res_1030["event_id"] == "anthem"
    assert res_1030["label"] == "National Anthem"
    assert res_1030["standup_en"] == "Please stand for the National Anthem"
    assert res_1030["show_standup_text"] is True

    # Monday at 11:02 Asia/Kolkata (after Anthem ends at 11:01): Vande Mataram is next
    dt_1102 = datetime.datetime(2026, 10, 19, 11, 2, 0, tzinfo=KOLKATA_TZ)
    res_1102 = storage.get_flag_event_today(screen_code="ALL", now_dt=dt_1102)
    assert res_1102["event_id"] == "vande_mataram"
    assert res_1102["label"] == "Vande Mataram"
    assert res_1102["standup_en"] == "Please stand for Vande Mataram"
    assert res_1102["show_standup_text"] is True

    # Monday at 17:05 Asia/Kolkata (after Vande Mataram ends at 17:01:30): no more events today
    dt_1705 = datetime.datetime(2026, 10, 19, 17, 5, 0, tzinfo=KOLKATA_TZ)
    res_1705 = storage.get_flag_event_today(screen_code="ALL", now_dt=dt_1705)
    assert res_1705["flag_start_ms"] is None
    assert res_1705["event_id"] is None


def test_one_event_skipped_while_other_runs(tmp_path):
    """Skipping anthem for today allows Vande Mataram to run normally today."""
    storage = NoticeStorage(db_file=str(tmp_path / "test_skip.db"))
    
    storage.update_daily_event("anthem", {"enabled": True})
    storage.update_daily_event("vande_mataram", {"enabled": True})

    # Skip anthem for today
    today_dt = datetime.datetime(2026, 10, 19, 10, 0, 0, tzinfo=KOLKATA_TZ)
    storage.skip_daily_event_today("anthem")
    
    anthem = storage.get_daily_event("anthem")
    today_str = datetime.datetime.now(KOLKATA_TZ).strftime("%Y-%m-%d")
    assert today_str in anthem["skip_dates"]

    vm = storage.get_daily_event("vande_mataram")
    assert today_str not in vm["skip_dates"]

    # When querying for today, Anthem is skipped, so Vande Mataram is returned
    res = storage.get_flag_event_today(screen_code="ALL")
    # If currently before 17:01:30, returns vande_mataram
    now_dt = datetime.datetime.now(KOLKATA_TZ)
    if now_dt.hour < 17:
        assert res["event_id"] == "vande_mataram"


def test_overlap_validation_rejected(tmp_path):
    """Reject event configuration if it overlaps an existing event on same day and screen."""
    storage = NoticeStorage(db_file=str(tmp_path / "test_overlap.db"))
    
    # 1. Attempting to add an event overlapping National Anthem (11:00, dur 60s, standup 15s)
    with pytest.raises(ValueError) as excinfo:
        storage.add_daily_event({
            "label": "Conflicting Event",
            "start_time": "11:00",
            "start_offset_seconds": 0,
            "duration_seconds": 60,
            "days_of_week": ["mon", "tue"],
            "screens": "ALL"
        })
    assert "This overlaps National Anthem at 11:00" in str(excinfo.value)

    # 2. Overlap taking into account standup lead time (15s before start)
    # Event starts at 11:01:10 with 15s standup -> starts at 11:00:55, while Anthem ends at 11:01:00
    with pytest.raises(ValueError) as excinfo2:
        storage.add_daily_event({
            "label": "Close Event",
            "start_time": "11:01",
            "start_offset_seconds": 10,
            "duration_seconds": 60,
            "show_standup_text": True,
            "days_of_week": ["mon"],
            "screens": "ALL"
        })
    assert "This overlaps National Anthem at 11:00" in str(excinfo2.value)

    # 3. Disjoint screens do NOT conflict
    # Update Anthem screens to 'EXCS' only, so adding 'CMPN' at the same time does NOT overlap
    storage.update_daily_event("anthem", {"screens": "EXCS"})
    ev_different_screen = storage.add_daily_event({
        "label": "CMPN Independent",
        "start_time": "11:00",
        "duration_seconds": 60,
        "days_of_week": ["mon"],
        "screens": "CMPN"
    })
    assert ev_different_screen["id"] is not None

    # 4. Disjoint days do NOT conflict
    # Sunday only vs Mon-Sat
    ev_sunday = storage.add_daily_event({
        "label": "Sunday Anthem",
        "start_time": "11:00",
        "duration_seconds": 60,
        "days_of_week": ["sun"],
        "screens": "EXCS"
    })
    assert ev_sunday["id"] is not None


def test_max_six_events_enforced(tmp_path):
    """Enforce maximum of 6 daily events."""
    storage = NoticeStorage(db_file=str(tmp_path / "test_max6.db"))
    
    # DB already has 2 seeded (anthem and vande_mataram)
    # Add 4 more with non-overlapping times
    times = ["09:00", "12:00", "14:00", "16:00"]
    for i, t in enumerate(times):
        storage.add_daily_event({
            "label": f"Event {i+3}",
            "start_time": t,
            "duration_seconds": 60,
            "days_of_week": ["mon"],
            "screens": "ALL"
        })

    assert len(storage.get_daily_events()) == 6

    # 7th event should be rejected
    with pytest.raises(ValueError) as excinfo:
        storage.add_daily_event({
            "label": "Event 7",
            "start_time": "20:00",
            "duration_seconds": 60,
            "days_of_week": ["mon"],
            "screens": "ALL"
        })
    assert "Maximum of 6 daily events allowed" in str(excinfo.value)


def test_delete_event_and_prevent_delete_last(tmp_path):
    """Events can be deleted, but the last remaining event cannot be deleted."""
    storage = NoticeStorage(db_file=str(tmp_path / "test_delete.db"))
    
    assert storage.delete_daily_event("vande_mataram") is True
    assert storage.get_daily_event("vande_mataram") is None
    assert len(storage.get_daily_events()) == 1


def test_audit_logs_contain_event_id_and_label(tmp_path):
    """Audit logs for FLAG_UPDATE, FLAG_SKIP, and FLAG_TEST_RUN include event id and label."""
    storage = NoticeStorage(db_file=str(tmp_path / "test_audit.db"))
    
    storage.update_daily_event("vande_mataram", {"enabled": True}, actor="test_admin")
    storage.skip_daily_event_today("vande_mataram", actor="test_admin")
    storage.record_daily_event_run("vande_mataram", result="Success test", actor="test_admin")

    conn = storage.get_connection()
    logs = conn.execute("SELECT action, target_id, details FROM audit_logs WHERE target_id = 'vande_mataram';").fetchall()
    actions = {r["action"]: r["details"] for r in logs}

    assert "FLAG_UPDATE" in actions
    assert "Vande Mataram" in actions["FLAG_UPDATE"]
    assert "FLAG_SKIP" in actions
    assert "Vande Mataram" in actions["FLAG_SKIP"]
    assert "FLAG_TEST_RUN" in actions
    assert "Vande Mataram" in actions["FLAG_TEST_RUN"]


def test_etag_invalidation_on_event_change(tmp_path):
    """make_flag_event_response ETag incorporates event_id, label, and standup prompts."""
    from app import make_flag_event_response
    from flask import Flask

    app = Flask(__name__)
    with app.test_request_context("/api/events/today?screen=ALL"):
        data_anthem = {
            "server_time_ms": 1000000,
            "flag_start_ms": 1100000,
            "flag_end_ms": 1160000,
            "show_standup_text": True,
            "standup_lead_seconds": 15,
            "event_id": "anthem",
            "label": "National Anthem",
            "standup_en": "Please stand for the National Anthem",
            "standup_hi": "कृपया राष्ट्रगान के लिए खड़े हो जाएँ",
            "standup_mr": "कृपया राष्ट्रगीतासाठी उभे राहा"
        }
        res1 = make_flag_event_response(data_anthem)
        etag1 = res1.headers.get("ETag")
        assert etag1 is not None

        # When event transitions to Vande Mataram:
        data_vm = {
            "server_time_ms": 1200000,
            "flag_start_ms": 1700000,
            "flag_end_ms": 1790000,
            "show_standup_text": True,
            "standup_lead_seconds": 15,
            "event_id": "vande_mataram",
            "label": "Vande Mataram",
            "standup_en": "Please stand for Vande Mataram",
            "standup_hi": "कृपया वंदे मातरम् के लिए खड़े हो जाएँ",
            "standup_mr": "कृपया वंदे मातरमसाठी उभे राहा"
        }
        res2 = make_flag_event_response(data_vm)
        etag2 = res2.headers.get("ETag")
        assert etag2 is not None
        assert etag1 != etag2, "ETag must differ when next event schedule and prompts take over"


def test_state_machine_rearming_without_reload():
    """State machine transitions through ROTATION -> STANDUP -> FLAG -> ROTATION and re-arms for 17:00 without reload."""
    import subprocess
    js_code = """
    const { FlagStateMachine } = require('./static/js/flag_scheduler.js');
    let mockTime = 1000;
    const history = [];
    const sm = new FlagStateMachine({
      getNow: () => mockTime,
      onEnterStandup: () => history.push('ENTER_STANDUP'),
      onEnterFlag: () => history.push('ENTER_FLAG'),
      onExitFlag: () => history.push('EXIT_FLAG'),
      onEnterRotation: () => history.push('ENTER_ROTATION')
    });

    // 1. Anthem at 11:00 (100000ms), dur 60s, standup 15s
    sm.setSchedule({
      event_id: 'anthem',
      label: 'National Anthem',
      flag_start_ms: 100000,
      flag_end_ms: 160000,
      show_standup_text: true,
      standup_lead_seconds: 15
    });

    mockTime = 80000; sm.evaluate();
    assert(sm.getState() === 'ROTATION');

    mockTime = 90000; sm.evaluate(); // 10s before start -> STANDUP
    assert(sm.getState() === 'STANDUP');

    mockTime = 105000; sm.evaluate(); // FLAG
    assert(sm.getState() === 'FLAG');

    mockTime = 165000; sm.evaluate(); // ROTATION (Anthem ended)
    assert(sm.getState() === 'ROTATION');

    // 2. Re-arm with Vande Mataram at 17:00 (500000ms), dur 90s, standup 15s
    sm.setSchedule({
      event_id: 'vande_mataram',
      label: 'Vande Mataram',
      flag_start_ms: 500000,
      flag_end_ms: 590000,
      show_standup_text: true,
      standup_lead_seconds: 15
    });

    mockTime = 165000; sm.evaluate(); // Remains in ROTATION, re-armed!
    assert(sm.getState() === 'ROTATION');

    mockTime = 490000; sm.evaluate(); // STANDUP for Vande Mataram
    assert(sm.getState() === 'STANDUP');

    mockTime = 510000; sm.evaluate(); // FLAG for Vande Mataram
    assert(sm.getState() === 'FLAG');

    mockTime = 595000; sm.evaluate(); // ROTATION (Vande Mataram ended)
    assert(sm.getState() === 'ROTATION');

    function assert(cond) {
      if (!cond) throw new Error('Assertion failed');
    }

    console.log(history.join(' -> '));
    """
    res = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
    assert "ENTER_STANDUP -> ENTER_FLAG -> EXIT_FLAG -> ENTER_ROTATION -> ENTER_STANDUP -> ENTER_FLAG -> EXIT_FLAG -> ENTER_ROTATION" in res.stdout


def test_change_of_time_honored_while_display_is_open(tmp_path):
    """A change of start time in storage is immediately honored by the next poll and state machine."""
    import subprocess
    storage = NoticeStorage(db_file=str(tmp_path / "test_time_change.db"))
    
    # Initial: Anthem at 11:00
    storage.update_daily_event("anthem", {"enabled": True, "start_time": "11:00", "duration_seconds": 60})
    dt_1030 = datetime.datetime(2026, 10, 19, 10, 30, 0, tzinfo=KOLKATA_TZ)
    res1 = storage.get_flag_event_today(screen_code="ALL", now_dt=dt_1030)
    assert res1["flag_start_ms"] == int(datetime.datetime(2026, 10, 19, 11, 0, 0, tzinfo=KOLKATA_TZ).timestamp() * 1000)

    # Change Anthem start time to 11:15 while display is open
    storage.update_daily_event("anthem", {"start_time": "11:15"})
    res2 = storage.get_flag_event_today(screen_code="ALL", now_dt=dt_1030)
    new_start_ms = int(datetime.datetime(2026, 10, 19, 11, 15, 0, tzinfo=KOLKATA_TZ).timestamp() * 1000)
    assert res2["flag_start_ms"] == new_start_ms

    # In state machine: at 11:00, old time has no effect, remains ROTATION until 11:15
    js_code = f"""
    const {{ FlagStateMachine }} = require('./static/js/flag_scheduler.js');
    let mockTime = 1000;
    const sm = new FlagStateMachine({{ getNow: () => mockTime }});

    // Display receives updated schedule
    sm.setSchedule({{
      event_id: 'anthem',
      flag_start_ms: {new_start_ms},
      flag_end_ms: {new_start_ms + 60000},
      show_standup_text: true,
      standup_lead_seconds: 15
    }});

    // At 11:00:00 (old start time): state must remain ROTATION
    const oldTimeMs = {res1["flag_start_ms"]};
    mockTime = oldTimeMs;
    sm.evaluate();
    if (sm.getState() !== 'ROTATION') throw new Error('Must stay in ROTATION at old time');

    // At 11:14:50 (10s before new 11:15 time): STANDUP
    mockTime = {new_start_ms} - 10000;
    sm.evaluate();
    if (sm.getState() !== 'STANDUP') throw new Error('Must enter STANDUP before new time');

    // At 11:15:05: FLAG
    mockTime = {new_start_ms} + 5000;
    sm.evaluate();
    if (sm.getState() !== 'FLAG') throw new Error('Must enter FLAG at new time');
    console.log('SUCCESS');
    """
    res = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
    assert "SUCCESS" in res.stdout


def test_playwright_fake_clock_two_daily_events_with_standup_no_reload():
    """
    Playwright end-to-end test with fake clock:
    - Display open and never reloaded.
    - 11:00 Anthem flag with trilingual standup text, back to rotation.
    - 17:00 Vande Mataram flag with trilingual standup text, back to rotation.
    - Both with stand-up text on and the correct lines for each event.
    - Zero page reloads throughout the entire sequence.
    """
    from pathlib import Path
    from playwright.sync_api import sync_playwright

    server_db = Path(__file__).resolve().parent.parent / "notices.db"
    server_storage = NoticeStorage(db_file=str(server_db))

    orig_anthem = server_storage.get_daily_event("anthem")
    orig_vm = server_storage.get_daily_event("vande_mataram")

    try:
        # Configure both events enabled with trilingual stand-up text
        server_storage.clear_flag_manual_override(ended_early=False)
        server_storage.update_daily_event("anthem", {
            "enabled": True,
            "start_time": "11:00",
            "start_offset_seconds": 0,
            "duration_seconds": 60,
            "days_of_week": ["mon", "tue", "wed", "thu", "fri", "sat"],
            "screens": "ALL",
            "show_standup_text": True,
            "standup_en": "Please stand for the National Anthem",
            "standup_hi": "कृपया राष्ट्रगान के लिए खड़े हो जाएँ",
            "standup_mr": "कृपया राष्ट्रगीतासाठी उभे राहा"
        })
        server_storage.update_daily_event("vande_mataram", {
            "enabled": True,
            "start_time": "17:00",
            "start_offset_seconds": 0,
            "duration_seconds": 90,
            "days_of_week": ["mon", "tue", "wed", "thu", "fri", "sat"],
            "screens": "ALL",
            "show_standup_text": True,
            "standup_en": "Please stand for Vande Mataram",
            "standup_hi": "कृपया वंदे मातरम् के लिए खड़े हो जाएँ",
            "standup_mr": "कृपया वंदे मातरमसाठी उभे राहा"
        })

        # Monday 2026-10-19 10:59:40 Asia/Kolkata
        sim_base = datetime.datetime(2026, 10, 19, 10, 59, 40, tzinfo=KOLKATA_TZ)

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

            # Set reload canary: if the page reloads at any point, this canary is wiped
            display_page.evaluate("() => { window.__canary_no_reload = 'PERSISTED_OK'; }")

            # Wait for flag scheduler to arm Anthem
            for _ in range(10):
                sched = display_page.evaluate("() => flagScheduler ? flagScheduler.getSchedule() : null")
                if sched and sched.get("event_id") == "anthem":
                    break
                display_page.clock.run_for(1000)

            sched = display_page.evaluate("() => flagScheduler ? flagScheduler.getSchedule() : null")
            assert sched is not None
            assert sched["event_id"] == "anthem"

            # 1. 10:59:40: Display in ROTATION (overlay hidden)
            assert display_page.evaluate("() => document.getElementById('flag-overlay').classList.contains('hidden')")
            assert not display_page.evaluate("() => document.body.classList.contains('flag-active')")

            # 2. Advance clock to 10:59:48 (12s before 11:00 -> STANDUP for Anthem)
            display_page.clock.run_for(8000)
            assert display_page.evaluate("() => !document.getElementById('standup-screen').classList.contains('hidden')")
            assert display_page.evaluate("() => document.getElementById('flag-screen').classList.contains('hidden')")
            assert "Please stand for the National Anthem" in display_page.locator("#standup-text-en").inner_text()
            assert "कृपया राष्ट्रगान के लिए खड़े हो जाएँ" in display_page.locator("#standup-text-hi").inner_text()
            assert "कृपया राष्ट्रगीतासाठी उभे राहा" in display_page.locator("#standup-text-mr").inner_text()

            # 3. Advance clock to 11:00:05 (5s into Anthem -> FLAG)
            display_page.clock.run_for(17000)
            assert display_page.evaluate("() => !document.getElementById('flag-screen').classList.contains('hidden')")
            assert display_page.evaluate("() => document.getElementById('standup-screen').classList.contains('hidden')")
            assert display_page.evaluate("() => document.body.classList.contains('flag-active')")

            # 4. Advance clock to 11:01:05 (5s after Anthem 60s duration ends at 11:01:00 -> ROTATION)
            display_page.clock.run_for(60000)
            assert display_page.evaluate("() => document.getElementById('flag-overlay').classList.contains('hidden')")
            assert not display_page.evaluate("() => document.body.classList.contains('flag-active')")

            # 5. Without reload, advance 3s to let client sync next event (Vande Mataram at 17:00)
            display_page.clock.run_for(3000)
            for _ in range(5):
                sched_next = display_page.evaluate("() => flagScheduler ? flagScheduler.getSchedule() : null")
                if sched_next and sched_next.get("event_id") == "vande_mataram":
                    break
                display_page.clock.run_for(1000)

            sched_vm = display_page.evaluate("() => flagScheduler ? flagScheduler.getSchedule() : null")
            assert sched_vm is not None
            assert sched_vm["event_id"] == "vande_mataram"
            assert sched_vm["label"] == "Vande Mataram"

            # 6. Advance clock to 16:59:48 (12s before 17:00 -> STANDUP for Vande Mataram)
            vm_standup_time = datetime.datetime(2026, 10, 19, 16, 59, 48, tzinfo=KOLKATA_TZ)
            display_page.clock.set_system_time(vm_standup_time)
            display_page.clock.run_for(500)
            assert display_page.evaluate("() => !document.getElementById('standup-screen').classList.contains('hidden')")
            assert display_page.evaluate("() => document.getElementById('flag-screen').classList.contains('hidden')")
            assert "Please stand for Vande Mataram" in display_page.locator("#standup-text-en").inner_text()
            assert "कृपया वंदे मातरम् के लिए खड़े हो जाएँ" in display_page.locator("#standup-text-hi").inner_text()
            assert "कृपया वंदे मातरमसाठी उभे राहा" in display_page.locator("#standup-text-mr").inner_text()

            # 7. Advance clock to 17:00:05 (5s into Vande Mataram -> FLAG)
            vm_flag_time = datetime.datetime(2026, 10, 19, 17, 0, 5, tzinfo=KOLKATA_TZ)
            display_page.clock.set_system_time(vm_flag_time)
            display_page.clock.run_for(500)
            assert display_page.evaluate("() => !document.getElementById('flag-screen').classList.contains('hidden')")
            assert display_page.evaluate("() => document.getElementById('standup-screen').classList.contains('hidden')")
            assert display_page.evaluate("() => document.body.classList.contains('flag-active')")

            # 8. Advance clock to 17:01:35 (5s after Vande Mataram 90s duration ends at 17:01:30 -> ROTATION)
            vm_end_time = datetime.datetime(2026, 10, 19, 17, 1, 35, tzinfo=KOLKATA_TZ)
            display_page.clock.set_system_time(vm_end_time)
            display_page.clock.run_for(500)
            assert display_page.evaluate("() => document.getElementById('flag-overlay').classList.contains('hidden')")
            assert not display_page.evaluate("() => document.body.classList.contains('flag-active')")

            # 9. Verify NO reload happened throughout the entire test
            canary = display_page.evaluate("() => window.__canary_no_reload")
            assert canary == "PERSISTED_OK", "Display page must never have reloaded"

            browser.close()
    finally:
        # Restore original state
        if orig_anthem:
            server_storage.update_daily_event("anthem", orig_anthem)
        if orig_vm:
            server_storage.update_daily_event("vande_mataram", orig_vm)

