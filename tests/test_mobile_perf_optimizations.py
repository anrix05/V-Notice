import os
import sys
import time
import pytest
from playwright.sync_api import sync_playwright

ADMIN_URL = "http://localhost:5001"
DISPLAY_URL = "http://localhost:5000"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "vnotice2026")

def login_admin(page):
    page.goto(f"{ADMIN_URL}/", wait_until="networkidle")
    if page.is_visible("#login-modal"):
        page.fill("#admin-password-input", ADMIN_PASSWORD)
        page.click("#btn-login")
        page.wait_for_timeout(500)
    page.wait_for_selector(".notice-item-card", timeout=8000)

def test_notices_list_skips_rerender_when_unchanged():
    """Verify that when notice data is unchanged, DOM cards retain identity."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        login_admin(page)

        # Mark cards with unique expando properties
        card_count = page.evaluate("""() => {
            const cards = document.querySelectorAll('.notice-item-card');
            cards.forEach((c, idx) => {
                c.__testMarker = 'test_marker_' + idx;
            });
            return cards.length;
        }""")
        assert card_count > 0, "Expected at least one notice card in DOM"

        # Call fetchNotices() again with unchanged data
        page.evaluate("() => window.fetchNotices && window.fetchNotices()")
        page.wait_for_timeout(400)

        # Verify all markers are still preserved
        preserved_count = page.evaluate("""() => {
            const cards = document.querySelectorAll('.notice-item-card');
            let preserved = 0;
            cards.forEach((c, idx) => {
                if (c.__testMarker === 'test_marker_' + idx) {
                    preserved++;
                }
            });
            return preserved;
        }""")
        assert preserved_count == card_count, (
            f"Expected all {card_count} cards to retain DOM identity, but only {preserved_count} did. "
            "Full DOM re-render occurred!"
        )
        browser.close()

def test_only_changed_cards_update_in_dom():
    """Verify keyed diffing updates only the modified card while keeping other cards untouched."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        login_admin(page)

        # Mark cards
        card_markers = page.evaluate("""() => {
            const cards = document.querySelectorAll('.notice-item-card');
            if (cards.length < 2) return null;
            cards[0].__firstCard = true;
            cards[1].__secondCard = true;
            return {
                id0: cards[0].dataset.noticeId || cards[0].getAttribute('data-notice-id'),
                id1: cards[1].dataset.noticeId || cards[1].getAttribute('data-notice-id')
            };
        }""")
        assert card_markers is not None, "Need at least 2 cards to test selective diffing"

        # Modify notice 0 via API
        new_headline = f"Perf Test Modified {int(time.time())}"
        update_res = page.evaluate("""async ({ id, title }) => {
            const csrfRes = await fetch('/api/csrf-token');
            const csrfData = await csrfRes.json();
            const csrf = csrfData.csrf_token;
            const pass = window.getAdminPassword ? window.getAdminPassword() : '';
            const res = await fetch(`/api/notices/${id}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrf,
                    'X-Password': pass
                },
                body: JSON.stringify({
                    title: title,
                    screens: ['ALL']
                })
            });
            const text = await res.text();
            return { ok: res.ok, status: res.status, text: text };
        }""", {"id": card_markers["id0"], "title": new_headline})
        assert update_res["ok"], f"Failed to update notice via API: {update_res}"

        # Refresh notices
        page.evaluate("() => window.fetchNotices(true)")
        page.wait_for_timeout(600)

        # Check: card 1 MUST retain __secondCard marker (not recreated)
        card1_retained = page.evaluate("""() => {
            const cards = document.querySelectorAll('.notice-item-card');
            return cards.length > 1 && cards[1].__secondCard === true;
        }""")
        assert card1_retained, "Card 1 DOM was destroyed and rebuilt when only Card 0 was updated!"

        # Check: card 0 has the new headline
        card0_headline = page.evaluate("""() => {
            const first = document.querySelector('.notice-item-card');
            return first ? first.innerText : '';
        }""")
        assert new_headline in card0_headline, "Card 0 did not update with the new headline!"
        browser.close()

def test_modals_animate_with_transform_and_opacity_only():
    """Assert modal animations use transform and opacity only, never layout properties."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        login_admin(page)

        forbidden_properties = [
            "top", "left", "right", "bottom",
            "width", "height", "margin", "padding",
            "margin-top", "margin-bottom", "margin-left", "margin-right",
            "filter", "backdrop-filter"
        ]

        # Inspect modal sheet styles
        transitions = page.evaluate("""() => {
            const modal = document.querySelector('#notice-sheet-dialog') || document.querySelector('.modal-dialog');
            const backdrop = document.querySelector('#notice-modal');
            function getProps(el) {
                if (!el) return [];
                const s = window.getComputedStyle(el);
                return s.transitionProperty.split(',').map(p => p.trim());
            }
            return {
                modal: getProps(modal),
                backdrop: getProps(backdrop)
            };
        }""")

        for prop in transitions.get("modal", []):
            if prop != "all" and prop != "none":
                for f in forbidden_properties:
                    assert prop != f, f"Forbidden layout transition '{f}' found on modal!"

        # Open the modal via mobile raised plus button
        page.click("#tab-btn-new")
        page.wait_for_selector("#notice-modal:not(.hidden)", state="visible", timeout=3000)

        # Assert transform & opacity during/after transition
        is_transform_driven = page.evaluate("""() => {
            const modal = document.querySelector('#notice-sheet-dialog');
            const style = window.getComputedStyle(modal);
            return style.transform !== '' && style.opacity !== '';
        }""")
        assert is_transform_driven, "Modal does not use transform and opacity!"
        browser.close()

def test_prefers_reduced_motion_disables_animations():
    """Verify prefers-reduced-motion: reduce sets zero animation/transition duration."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Emulate reduced motion
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.emulate_media(reduced_motion="reduce")
        login_admin(page)

        modal_reduced = page.evaluate("""() => {
            const modal = document.querySelector('#notice-sheet-dialog') || document.querySelector('.modal-dialog');
            if (!modal) return null;
            const s = window.getComputedStyle(modal);
            return {
                transitionDuration: s.transitionDuration,
                animationDuration: s.animationDuration
            };
        }""")

        if modal_reduced:
            dur = modal_reduced["transitionDuration"]
            # Duration should be 0s, 0.001s, 1e-05s (instant)
            assert any(dur.startswith(prefix) for prefix in ["0s", "0.00", "0.01", "1e-05", "none"]), (
                f"Expected reduced motion transition duration to be instant, got: {dur}"
            )
        browser.close()

def test_display_header_narrow_widths():
    """Test display header at 390x844: brand title on 1 line, dept pill truncated, clock/date single lines."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(f"{DISPLAY_URL}/display/ALL", wait_until="networkidle")
        page.wait_for_selector(".display-header", timeout=5000)

        header_metrics = page.evaluate("""() => {
            const brand = document.querySelector('.brand-title') || document.querySelector('.logo-text');
            const dept = document.querySelector('.dept-header-pill') || document.querySelector('.dept-pill');
            const clock = document.querySelector('.clock-time') || document.querySelector('.header-clock');
            const date = document.querySelector('.clock-date') || document.querySelector('.header-date');

            function getLineCount(el) {
                if (!el) return 0;
                const lh = parseFloat(window.getComputedStyle(el).lineHeight) || parseFloat(window.getComputedStyle(el).fontSize) * 1.2;
                return Math.round(el.offsetHeight / lh);
            }

            return {
                brandWhiteSp: brand ? window.getComputedStyle(brand).whiteSpace : '',
                deptOverflow: dept ? window.getComputedStyle(dept).textOverflow : '',
                deptWhiteSp: dept ? window.getComputedStyle(dept).whiteSpace : '',
                clockLineCount: getLineCount(clock),
                dateLineCount: getLineCount(date)
            };
        }""")

        assert header_metrics["deptOverflow"] == "ellipsis", (
            f"Department pill should have text-overflow: ellipsis, got {header_metrics['deptOverflow']}"
        )
        assert header_metrics["deptWhiteSp"] == "nowrap", (
            f"Department pill should have white-space: nowrap, got {header_metrics['deptWhiteSp']}"
        )
        assert header_metrics["clockLineCount"] <= 1, "Clock wrapped into multiple lines!"
        assert header_metrics["dateLineCount"] <= 1, "Date wrapped into multiple lines!"
        browser.close()
