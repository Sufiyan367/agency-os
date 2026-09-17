"""
Comprehensive Playwright Verification for Agency OS Cinematic Landing Page.
Tests all 27 specified test conditions and 7-viewport responsive matrix.
"""

import time
import threading
import pytest
import uvicorn
pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright

from app.api.app import app

TEST_PORT = 8765
BASE_URL = f"http://127.0.0.1:{TEST_PORT}"

class ServerThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        config = uvicorn.Config(app, host="127.0.0.1", port=TEST_PORT, log_level="error")
        self.server = uvicorn.Server(config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True

@pytest.fixture(scope="module")
def live_server():
    server = ServerThread()
    server.start()
    # Wait for server readiness
    import urllib.request
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=1) as r:
                if r.getcode() == 200:
                    break
        except Exception:
            time.sleep(0.2)
    yield BASE_URL
    server.stop()

def test_playwright_all_criteria(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # 1. Desktop test at 1440x900
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        response = page.goto(live_server)
        assert response.status == 200, f"Expected 200 OK, got {response.status}"

        # 1. Title test
        assert page.title() == "Intelligence Designed To Evolve"

        # 2. Video element exists & 3. exact CloudFront URL
        video = page.locator("video.bg-video")
        assert video.count() == 1, "Video element not found"
        source = video.locator("source")
        exact_url = "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260809_012548_ef22562c-c0ae-4816-ad9d-f8922af4e6a7.mp4"
        assert source.get_attribute("src") == exact_url

        # 4, 5, 6, 7. Video attributes
        assert video.get_attribute("muted") is not None
        assert video.get_attribute("autoplay") is not None
        assert video.get_attribute("loop") is not None
        assert video.get_attribute("playsinline") is not None

        # 8. Logo element
        logo_img = page.locator(".logo-button img")
        assert logo_img.count() == 1
        assert "assets/logo.webp" in logo_img.get_attribute("src")

        # 9, 10, 11. Fonts and stylesheets
        head_html = page.locator("head").inner_html()
        assert "BubbledotICG-FinePos" in head_html
        assert "fonts.googleapis.com/css2?family=Inter" in head_html
        assert "font-awesome" in head_html

        # 12, 13, 14. Trust icons
        assert page.locator(".fa-microsoft").count() >= 1
        assert page.locator(".fa-amazon").count() >= 1
        assert page.locator(".fa-google").count() >= 1
        assert "Trusted by 2000+ Enterprises" in page.locator(".trust-pill-text").inner_text()

        # 15. Desktop navigation visible
        assert page.locator(".nav-pill").is_visible()
        assert page.locator(".sign-in-btn").is_visible()
        # Burger hidden on desktop
        assert not page.locator(".burger-btn").is_visible()

        # Headline exact copy
        headline = page.locator(".headline")
        assert headline.is_visible()
        spans = headline.locator("span")
        assert spans.nth(0).inner_text() == "Intelligence"
        assert spans.nth(1).inner_text() == "Designed To Evolve"

        # Subhead exact copy
        subhead = page.locator(".subhead")
        assert subhead.inner_text() == "Build applications that reason, adapt and collaborate using a modular AI platform designed for production."

        # CTA exact text and visibility
        cta = page.locator(".cta-button")
        assert cta.is_visible()
        assert cta.inner_text() == "Get Started"

        # 23, 24. Stats count up and check values
        page.wait_for_timeout(2500)
        stat_values = page.locator(".stat-value").all_inner_texts()
        assert "120" in stat_values[0]
        assert "99.99" in stat_values[1]
        assert "24" in stat_values[2]
        assert "2.4" in stat_values[3]

        # CTA opens modal
        cta.click()
        page.wait_for_timeout(300)
        modal = page.locator("#consultationModal")
        assert "active" in (modal.get_attribute("class") or "")
        
        # Escape closes modal
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        assert "active" not in (modal.get_attribute("class") or "")

        # Test active navigation indicator switching
        nav_links = page.locator(".nav-link")
        assert "active" in (nav_links.nth(0).get_attribute("class") or "")
        nav_links.nth(1).click() # Click Product
        page.wait_for_timeout(100)
        assert "active" in (nav_links.nth(1).get_attribute("class") or "")
        assert "active" not in (nav_links.nth(0).get_attribute("class") or "")

        # 2. Mobile test at 390x844
        mobile_page = browser.new_page(viewport={"width": 390, "height": 844})
        mobile_page.goto(live_server)

        # 16. Desktop nav hidden on mobile
        assert not mobile_page.locator(".nav-pill").is_visible()
        assert not mobile_page.locator(".sign-in-btn").is_visible()

        # 17. Burger visible on mobile
        burger = mobile_page.locator("#burgerBtn")
        assert burger.is_visible()
        assert burger.get_attribute("aria-expanded") == "false"

        # 18. Burger opens menu
        burger.click()
        mobile_page.wait_for_timeout(300)
        assert burger.get_attribute("aria-expanded") == "true"
        assert mobile_page.locator("body.menu-open").count() == 1
        menu = mobile_page.locator("#mobileMenu")
        assert menu.is_visible()

        # 19. Escape closes menu
        mobile_page.keyboard.press("Escape")
        mobile_page.wait_for_timeout(300)
        assert burger.get_attribute("aria-expanded") == "false"
        assert not menu.is_visible()

        # 20. Overlay click closes menu
        burger.click()
        mobile_page.wait_for_timeout(300)
        assert menu.is_visible()
        mobile_page.locator("#mobileOverlay").click(position={"x": 10, "y": 10})
        mobile_page.wait_for_timeout(300)
        assert not menu.is_visible()

        # 21. Link click closes menu
        burger.click()
        mobile_page.wait_for_timeout(300)
        assert menu.is_visible()
        mobile_page.locator("#mobileMenu a").first.click()
        mobile_page.wait_for_timeout(300)
        assert not menu.is_visible()

        # 26. Check no horizontal overflow
        scroll_width = mobile_page.evaluate("document.documentElement.scrollWidth")
        client_width = mobile_page.evaluate("document.documentElement.clientWidth")
        assert scroll_width <= client_width + 1, f"Overflow detected: scrollWidth={scroll_width}, clientWidth={client_width}"

        # 34. Responsive Matrix Test
        viewports = [
            (1440, 900),
            (1280, 800),
            (1024, 768),
            (768, 1024),
            (390, 844),
            (375, 812),
            (360, 800)
        ]
        for w, h in viewports:
            vp_page = browser.new_page(viewport={"width": w, "height": h})
            vp_page.goto(live_server)
            vp_page.wait_for_timeout(200)

            sw = vp_page.evaluate("document.documentElement.scrollWidth")
            cw = vp_page.evaluate("document.documentElement.clientWidth")
            assert sw <= cw + 1, f"Horizontal scroll detected at {w}x{h}: sw={sw}, cw={cw}"

            sh = vp_page.evaluate("document.documentElement.scrollHeight")
            ch = vp_page.evaluate("document.documentElement.clientHeight")
            assert sh <= ch + 1, f"Vertical page scroll detected at {w}x{h}: sh={sh}, ch={ch}"

            # Ensure primary elements visible
            assert vp_page.locator(".site-header").is_visible(), f"Header not visible at {w}x{h}"
            assert vp_page.locator(".headline").is_visible(), f"Headline not visible at {w}x{h}"
            assert vp_page.locator(".cta-button").is_visible(), f"CTA not visible at {w}x{h}"
            assert vp_page.locator("#statsSection").is_visible(), f"Stats not visible at {w}x{h}"
            vp_page.close()

        # 24. Height-specific responsiveness at <=700px height
        height_tests = [(1024, 600), (800, 600)]
        for w, h in height_tests:
            h_page = browser.new_page(viewport={"width": w, "height": h})
            h_page.goto(live_server)
            h_page.wait_for_timeout(200)
            h_sw = h_page.evaluate("document.documentElement.scrollWidth")
            h_cw = h_page.evaluate("document.documentElement.clientWidth")
            assert h_sw <= h_cw + 1, f"Horizontal overflow at {w}x{h}"
            h_sh = h_page.evaluate("document.documentElement.scrollHeight")
            h_ch = h_page.evaluate("document.documentElement.clientHeight")
            assert h_sh <= h_ch + 1, f"Vertical scroll at {w}x{h}"
            assert h_page.locator(".site-header").is_visible()
            assert h_page.locator(".headline").is_visible()
            assert h_page.locator(".cta-button").is_visible()
            assert h_page.locator("#statsSection").is_visible()
            h_page.close()

        # 25. Reduced-motion test
        rm_page = browser.new_page(
            viewport={"width": 1440, "height": 900},
            extra_http_headers={"Sec-CH-Prefers-Reduced-Motion": "reduce"}
        )
        rm_page.emulate_media(reduced_motion="reduce")
        rm_page.goto(live_server)
        assert rm_page.locator(".headline").is_visible()
        # Ensure stat values are immediately rendered without waiting
        rm_stats = rm_page.locator(".stat-value").all_inner_texts()
        assert "120" in rm_stats[0]
        assert "99.99" in rm_stats[1]
        assert "24" in rm_stats[2]
        assert "2.4" in rm_stats[3]
        rm_page.close()

        assert len(console_errors) == 0, f"Console errors detected: {console_errors}"

        page.close()
        mobile_page.close()
        browser.close()

        print("\n[SUCCESS] All Playwright and responsive criteria passed perfectly!")

if __name__ == "__main__":
    pytest.main(["-s", __file__])
