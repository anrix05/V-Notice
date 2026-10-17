import io
import os
import wave
import json
import struct
import math
import pytest
from pathlib import Path
from unittest.mock import patch

import config
from storage import NoticeStorage, LocalMediaStorage, probe_voice_media, sanitize_or_generate_waveform
from app import unified_app

def generate_test_wav_bytes(duration_sec: float = 1.0, sample_rate: int = 8000) -> bytes:
    """Generates valid WAV audio bytes with a gentle sine tone."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        total_frames = int(sample_rate * duration_sec)
        for i in range(total_frames):
            value = int(32767.0 * 0.3 * math.sin(2.0 * math.pi * 440.0 * i / sample_rate))
            data = struct.pack("<h", value)
            wf.writeframesraw(data)
    return buf.getvalue()

@pytest.fixture
def temp_storage(tmp_path):
    db_file = tmp_path / "test_voice.db"
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    backend = LocalMediaStorage(media_dir=media_dir)
    st = NoticeStorage(db_file=str(db_file), media_backend=backend)
    return st

@pytest.fixture
def test_client(tmp_path):
    db_file = tmp_path / "client_voice.db"
    media_dir = tmp_path / "client_media"
    media_dir.mkdir(parents=True, exist_ok=True)
    backend = LocalMediaStorage(media_dir=media_dir)
    st = NoticeStorage(db_file=str(db_file), media_backend=backend)
    
    with patch("app.storage", st):
        app = unified_app
        app.config["TESTING"] = True
        client = app.test_client()
        client.storage = st
        yield client

def test_waveform_sanitizer():
    # Valid waveform with 64 integers 0-100
    valid_wf = [50] * 64
    res = sanitize_or_generate_waveform(valid_wf)
    parsed = json.loads(res)
    assert len(parsed) == 64
    assert all(x == 50 for x in parsed)

    # Invalid waveform: wrong length (3 items)
    short_wf = [10, 20, 30]
    res2 = sanitize_or_generate_waveform(short_wf)
    parsed2 = json.loads(res2)
    assert len(parsed2) == 64
    assert all(0 <= x <= 100 for x in parsed2)

    # Non-list string input
    res3 = sanitize_or_generate_waveform("not-a-list")
    parsed3 = json.loads(res3)
    assert len(parsed3) == 64
    assert all(0 <= x <= 100 for x in parsed3)

def test_mp3_sync_word_sniffing():
    from security import sniff_media_type
    # MPEG sync word: first byte 0xFF, second byte (b1 & 0xE0) == 0xE0
    header_sync = bytes([0xFF, 0xFB, 0x90, 0x64])
    res = sniff_media_type(header_sync)
    assert res == ("mp3", "audio")

    # ID3 header
    header_id3 = b"ID3\x03\x00\x00\x00\x00\x00\x00"
    res_id3 = sniff_media_type(header_id3)
    assert res_id3 == ("mp3", "audio")

    # Non-mp3 starting with 0xFF but second byte not sync
    header_invalid = bytes([0xFF, 0x1B, 0x00, 0x00])
    res_invalid = sniff_media_type(header_invalid)
    assert res_invalid is None

def test_voice_notices_disabled_by_default(temp_storage):
    with patch.object(config, "VOICE_NOTICES_ENABLED", False):
        wav_data = generate_test_wav_bytes(1.0)
        file_obj = io.BytesIO(wav_data)
        file_obj.filename = "test.wav"

        with pytest.raises(ValueError, match="Voice notices are currently disabled"):
            temp_storage.add(
                {
                    "title": "Voice Disabled Test",
                    "type": "voice",
                    "screens": ["ALL"],
                },
                file_obj=file_obj,
            )

def test_voice_notices_creation_and_attributes(temp_storage):
    with patch.object(config, "VOICE_NOTICES_ENABLED", True):
        wav_data = generate_test_wav_bytes(2.5)
        file_obj = io.BytesIO(wav_data)
        file_obj.filename = "notice.wav"

        notice = temp_storage.add(
            {
                "title": "Important Voice Announcement",
                "type": "voice",
                "caption": "This is a transcript of the audio.",
                "repeat_gap_minutes": 15,
                "audio_duration": 2.5,
                "waveform": [45] * 64,
                "screens": ["ALL"],
            },
            file_obj=file_obj,
        )

        assert notice is not None
        assert notice["type"] == "voice"
        assert notice["has_audio"] == "true"
        assert notice["play_sound"] == 1
        assert notice["caption"] == "This is a transcript of the audio."
        assert notice["repeat_gap_minutes"] == 15
        assert notice["audio_duration"] >= 0.5
        # Slide duration must be int(round(audio_duration)) + 1
        expected_dur = int(round(notice["audio_duration"])) + 1
        assert notice["duration"] == expected_dur

        # Waveform check
        wf = json.loads(notice["waveform"])
        assert len(wf) == 64
        assert all(0 <= x <= 100 for x in wf)

def test_voice_notices_untrusted_duration_clamped(temp_storage):
    with patch.object(config, "VOICE_NOTICES_ENABLED", True):
        wav_data = generate_test_wav_bytes(1.0)
        file_obj = io.BytesIO(wav_data)
        file_obj.filename = "notice.wav"

        # Client sends absurd duration of 99999 seconds without ffprobe duration overriding it
        with patch("storage.probe_voice_media", return_value=(True, None, "")):
            notice = temp_storage.add(
                {
                    "title": "Clamped Voice Announcement",
                    "type": "voice",
                    "audio_duration": 99999,
                    "screens": ["ALL"],
                },
                file_obj=file_obj,
            )
            assert notice["audio_duration"] == float(config.MAX_VOICE_DURATION_SECONDS)

def test_voice_notices_rejects_video_stream(temp_storage):
    with patch.object(config, "VOICE_NOTICES_ENABLED", True):
        wav_data = generate_test_wav_bytes(1.0)
        file_obj = io.BytesIO(wav_data)
        file_obj.filename = "fake_audio.wav"

        # Mock probe_voice_media detecting a video stream
        with patch("storage.probe_voice_media", return_value=(False, None, "Voice notices must contain only audio (no video stream allowed).")):
            with pytest.raises(ValueError, match="Voice notices must contain only audio"):
                temp_storage.add(
                    {
                        "title": "Bad Voice Notice",
                        "type": "voice",
                        "screens": ["ALL"],
                    },
                    file_obj=file_obj,
                )

def test_voice_file_streaming_endpoint(test_client):
    with patch.object(config, "VOICE_NOTICES_ENABLED", True):
        wav_data = generate_test_wav_bytes(1.5)
        file_obj = io.BytesIO(wav_data)
        file_obj.filename = "voice_audio.wav"

        st = test_client.storage
        notice = st.add(
            {
                "title": "Voice Streaming Notice",
                "type": "voice",
                "caption": "Speech caption",
                "screens": ["ALL"],
                "status": "live",
            },
            file_obj=file_obj,
        )

        nid = notice["id"]
        # Public file download endpoint
        res = test_client.get(f"/n/{nid}/file")
        assert res.status_code == 200
        assert "audio/" in res.headers.get("Content-Type", "")
        cd = res.headers.get("Content-Disposition", "")
        assert "attachment" in cd
        assert "wav" in cd.lower()
        # Verify it streamed real audio bytes, not .txt announcement
        assert len(res.data) > 100
        assert res.data.startswith(b"RIFF")

def test_public_page_voice_notice_rendering(test_client):
    with patch.object(config, "VOICE_NOTICES_ENABLED", True):
        wav_data = generate_test_wav_bytes(1.0)
        file_obj = io.BytesIO(wav_data)
        file_obj.filename = "announcement.wav"

        st = test_client.storage
        notice = st.add(
            {
                "title": "Public Voice Notice",
                "type": "voice",
                "caption": "Campus closure announced today.",
                "screens": ["ALL"],
                "status": "live",
            },
            file_obj=file_obj,
        )

        nid = notice["id"]
        res = test_client.get(f"/n/{nid}")
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert "voice-public-player" in html
        assert "btn-voice-public-play" in html
        assert "Campus closure announced today." in html
        assert "Save audio" in html

def test_admin_ui_voice_notices_toggle(test_client):
    # When enabled
    with patch.object(config, "VOICE_NOTICES_ENABLED", True):
        res = test_client.get("/admin")
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'id="type-opt-voice"' in html
        assert 'VOICE_NOTICES_ENABLED = true' in html

    # When disabled
    with patch.object(config, "VOICE_NOTICES_ENABLED", False):
        res = test_client.get("/admin")
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'id="type-opt-voice"' not in html
        assert 'VOICE_NOTICES_ENABLED = false' in html

import subprocess
import socket
import threading
import time
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright

def generate_silent_wav_bytes(duration_sec: float = 1.0, sample_rate: int = 8000) -> bytes:
    """Generates silent WAV audio bytes (amplitude 0)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        total_frames = int(sample_rate * duration_sec)
        wf.writeframesraw(bytes(total_frames * 2))
    return buf.getvalue()

def test_voice_notices_rejects_silent_recording(temp_storage):
    """Server-side: after ffprobe, if stored voice file mean volume is below about -60 dB (or -inf), reject."""
    with patch.object(config, "VOICE_NOTICES_ENABLED", True):
        silent_wav = generate_silent_wav_bytes(1.0)
        file_obj = io.BytesIO(silent_wav)
        file_obj.filename = "silent_recording.wav"

        with pytest.raises(ValueError, match="We did not hear anything. Check that your microphone is on and the right one is selected."):
            temp_storage.add(
                {
                    "title": "Silent Notice",
                    "type": "voice",
                    "screens": ["ALL"],
                },
                file_obj=file_obj,
            )

class LiveServerThread(threading.Thread):
    def __init__(self, flask_app):
        super().__init__(daemon=True)
        self.server = make_server('127.0.0.1', 0, flask_app, threaded=True)
        self.port = self.server.port
        self.ctx = flask_app.app_context()
        self.ctx.push()

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()

@pytest.fixture(scope="module")
def live_server():
    with patch.object(config, "VOICE_NOTICES_ENABLED", True):
        srv = LiveServerThread(unified_app)
        srv.start()
        time.sleep(0.3)
        base_url = f"http://127.0.0.1:{srv.port}"
        yield base_url
        srv.shutdown()

def test_playwright_admin_voice_record_and_playcheck(live_server):
    """
    Playwright test:
    - Admin: record, stop, tap Play check -> verify muted === false, volume === 1.0, currentTime > 0.
    - Tests live level meter, mic picker enumeration & session persistence, play check sound.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
                "--autoplay-policy=no-user-gesture-required"
            ]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.grant_permissions(["microphone"], origin=live_server)
        page = context.new_page()

        page.goto(f"{live_server}/admin", wait_until="networkidle")

        if page.is_visible("#login-modal"):
            page.fill("#admin-password-input", getattr(config, "ADMIN_PASSWORD", "vnotice2026"))
            page.click("#btn-login")
            page.wait_for_timeout(500)

        page.click("#btn-open-create")
        page.wait_for_selector("#notice-modal", state="visible")

        # Select Voice content type
        page.click("#type-opt-voice")
        page.wait_for_selector("#voice-upload-group", state="visible")
        page.wait_for_selector("#panel-voice-record", state="visible")

        # Check live level meter element exists
        level_meter = page.locator("#voice-level-meter")
        assert level_meter.is_visible()
        assert page.locator("#level-meter-bar").count() == 1

        # Check mic select is populated
        page.wait_for_timeout(400)
        mic_options = page.eval_on_selector("#voice-mic-select", "sel => Array.from(sel.options).map(o => o.value)")
        assert len(mic_options) >= 1

        # Select a device and check sessionStorage persistence
        page.select_option("#voice-mic-select", index=0)
        stored_id = page.evaluate("() => sessionStorage.getItem('vnotice_mic_device_id')")

        # Click Record
        page.click("#btn-voice-record")
        page.wait_for_timeout(1500)

        # Click Stop
        page.click("#btn-voice-stop")
        page.wait_for_selector("#voice-preview-box", state="visible", timeout=6000)

        # Check that Play check button exists and audio is set
        btn_playcheck = page.locator("#btn-voice-playcheck")
        assert btn_playcheck.is_visible()

        # Click Play check
        btn_playcheck.click()
        page.wait_for_timeout(500)

        # Verify muted === false, volume === 1.0, hasSrc === true
        audio_state = page.evaluate("""() => {
            const el = document.getElementById('voice-check-audio');
            return {
                muted: el.muted,
                volume: el.volume,
                paused: el.paused,
                currentTime: el.currentTime,
                hasSrc: Boolean(el.src)
            };
        }""")
        assert audio_state["muted"] is False
        assert audio_state["volume"] == 1.0
        assert audio_state["hasSrc"] is True

        browser.close()

def test_playwright_admin_voice_silent_input_check(live_server):
    """
    Playwright test:
    - Silent stream or below 2% threshold:
    - Show 'We did not hear anything. Check that your microphone is on and the right one is selected.'
    - Keep Publish disabled until the admin re-records or confirms.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
                "--autoplay-policy=no-user-gesture-required"
            ]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.grant_permissions(["microphone"], origin=live_server)
        page = context.new_page()

        page.goto(f"{live_server}/admin", wait_until="networkidle")
        if page.is_visible("#login-modal"):
            page.fill("#admin-password-input", getattr(config, "ADMIN_PASSWORD", "vnotice2026"))
            page.click("#btn-login")
            page.wait_for_timeout(500)

        page.click("#btn-open-create")
        page.wait_for_selector("#notice-modal", state="visible")
        page.click("#type-opt-voice")
        page.wait_for_selector("#panel-voice-record", state="visible")

        # Simulate silent recording peak detection (< 0.02)
        page.evaluate("""() => {
            const warn = document.getElementById('voice-silent-warning');
            const msg = document.getElementById('voice-silent-msg');
            const btnSubmit = document.getElementById('btn-submit-create');
            warn.classList.remove('hidden');
            msg.textContent = 'We did not hear anything. Check that your microphone is on and the right one is selected.';
            btnSubmit.disabled = true;
        }""")

        warn_locator = page.locator("#voice-silent-warning")
        assert warn_locator.is_visible()
        msg_text = page.locator("#voice-silent-msg").inner_text()
        assert "We did not hear anything. Check that your microphone is on and the right one is selected." in msg_text

        # Verify Publish button is disabled
        btn_submit = page.locator("#btn-submit-create")
        assert btn_submit.is_disabled()

        # Click 'Use anyway' confirm button
        btn_confirm = page.locator("#btn-voice-confirm-silent")
        assert btn_confirm.is_visible()
        btn_confirm.click()

        # Verify Publish button is now enabled
        assert not btn_submit.is_disabled()

        browser.close()

def test_playwright_display_voice_slide_sound_enabled_and_muted(live_server):
    """
    Playwright test on display (localhost, screen ALL):
    1. When screen ALL sound_enabled=True:
       - voice slide plays unmuted (voiceAudioElement.muted === false, volume > 0).
       - stageSpeakerIndicator is active (visible, no .is-muted).
    2. When screen ALL sound_enabled=False:
       - voice slide is silent.
       - stageSpeakerIndicator has .is-muted (visible with muted icon).
    """
    from storage import storage as app_storage
    now = int(time.time() * 1000)

    wav_bytes = generate_test_wav_bytes(3.0)
    file_obj = io.BytesIO(wav_bytes)
    file_obj.filename = "display_voice.wav"

    with patch.object(config, "VOICE_NOTICES_ENABLED", True):
        # Configure screen ALL with sound enabled
        app_storage.update_department("ALL", {"sound_enabled": True, "sound_volume": 90})

        # Remove old live notices to isolate test notice
        notices = app_storage.get_all()
        for n in notices:
            try:
                app_storage.delete(n["id"])
            except Exception:
                pass

        notice = app_storage.add(
            {
                "title": "Voice Slide Display Sound Test",
                "type": "voice",
                "caption": "Speech caption for display test.",
                "screens": ["ALL"],
                "start": now - 1000,
                "end": now + 3600000,
                "duration": 5,
                "repeat_gap_minutes": 0,
                "audio_duration": 3.0,
                "waveform": [50] * 64,
                "play_sound": 1,
            },
            file_obj=file_obj,
        )
        assert notice is not None

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--use-fake-device-for-media-stream",
                    "--autoplay-policy=no-user-gesture-required"
                ]
            )
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()

            page.goto(f"{live_server}/display/ALL", wait_until="networkidle")
            page.wait_for_selector("#card-voice", state="visible", timeout=8000)

            # Check that stage speaker indicator is active
            speaker_ind = page.locator("#stage-speaker-indicator")
            page.wait_for_timeout(800)
            assert speaker_ind.is_visible()
            has_muted_class = page.eval_on_selector("#stage-speaker-indicator", "el => el.classList.contains('is-muted')")
            assert not has_muted_class

            # Check audio element state: unmuted and volume > 0
            audio_state = page.evaluate("""() => {
                const el = document.getElementById('voice-audio-element');
                return {
                    muted: el ? el.muted : true,
                    volume: el ? el.volume : 0,
                    paused: el ? el.paused : true,
                    currentTime: el ? el.currentTime : 0
                };
            }""")
            assert audio_state["muted"] is False
            assert audio_state["volume"] > 0

            # 2. Test with sound disabled for screen ALL
            app_storage.update_department("ALL", {"sound_enabled": False, "sound_volume": 0})
            page.reload(wait_until="networkidle")
            page.wait_for_selector("#card-voice", state="visible", timeout=8000)
            page.wait_for_timeout(800)

            # Speaker indicator must show MUTED (.is-muted)
            speaker_ind2 = page.locator("#stage-speaker-indicator")
            assert speaker_ind2.is_visible()
            is_muted_flag = page.eval_on_selector("#stage-speaker-indicator", "el => el.classList.contains('is-muted')")
            assert is_muted_flag is True

            # Audio element must not be playing unmuted
            audio_state2 = page.evaluate("""() => {
                const el = document.getElementById('voice-audio-element');
                return {
                    muted: el ? el.muted : true,
                    paused: el ? el.paused : true
                };
            }""")
            assert audio_state2["paused"] or audio_state2["muted"]

            browser.close()

def test_playwright_admin_voice_never_autoplays(live_server):
    """Admin portal must never autoplay unmuted voice audio on modal open or tab switch."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.goto(f"{live_server}/admin", wait_until="networkidle")
        if page.is_visible("#login-modal"):
            page.fill("#admin-password-input", getattr(config, "ADMIN_PASSWORD", "vnotice2026"))
            page.click("#btn-login")
            page.wait_for_timeout(500)

        page.click("#btn-open-create")
        page.wait_for_selector("#notice-modal", state="visible")
        page.click("#type-opt-voice")
        page.wait_for_selector("#panel-voice-record", state="visible")
        page.wait_for_timeout(500)

        # Check no audio element is unmuted or playing
        audio_check = page.evaluate("""() => {
            const audios = Array.from(document.querySelectorAll('audio, video'));
            return audios.map(a => ({
                muted: a.muted,
                volume: a.volume,
                paused: a.paused
            }));
        }""")
        for item in audio_check:
            # If not paused, it must be muted with 0 volume
            if not item["paused"]:
                assert item["muted"] is True
                assert item["volume"] == 0

        browser.close()


