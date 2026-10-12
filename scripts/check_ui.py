"""Isolated browser QA against a local VRIOSCU development server.

Usage: python scripts/check_ui.py --base-url http://127.0.0.1:5001
Requires optional playwright dependency and an installed Chromium browser.
Never connects to an existing browser profile or a public website.
"""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["/", "/product", "/features", "/how-it-works", "/reports", "/documentation", "/use-cases",
         "/download", "/public-beta", "/contact", "/privacy", "/login", "/register"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--visual-only", action="store_true", help="Refresh representative desktop/mobile screenshots")
    args = parser.parse_args()
    assert urlparse(args.base_url).hostname in ("localhost", "127.0.0.1"), "QA is limited to a local development server"
    output = ROOT / "tmp/redesign"
    output.mkdir(parents=True, exist_ok=True)
    headless = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright/chromium_headless_shell-1179/chrome-win/headless_shell.exe"
    executable = args.executable or (headless if headless.is_file() else None)
    results, errors, failed = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=str(executable) if executable else None)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(args.base_url + "/") else route.abort())
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.on("response", lambda response: failed.append([response.status, response.url]) if response.status >= 400 else None)
        page.goto(args.base_url + "/", wait_until="networkidle")
        assert page.locator("[data-consent-banner]").count() == 0
        links = set()
        for width in ([1440, 390] if args.visual_only else [1440, 1024, 768, 390, 320]):
            page.set_viewport_size({"width": width, "height": 1000})
            for path in (["/", "/reports", "/download", "/contact", "/login"] if args.visual_only else PAGES):
                response = page.goto(args.base_url + path, wait_until="networkidle")
                assert response.status == 200, (path, response.status)
                page.locator("img").evaluate_all("imgs => imgs.forEach(i => { if(i.hasAttribute('src')) i.loading='eager'; })")
                page.locator(".site-footer").scroll_into_view_if_needed()
                page.wait_for_function("() => Array.from(document.images).filter(i => i.currentSrc).every(i => i.complete)")
                broken = page.locator("img").evaluate_all("images => images.filter(i => i.currentSrc && !i.naturalWidth).map(i => i.src)")
                assert not broken, (path, broken)
                size = page.evaluate("({viewport:innerWidth,document:document.documentElement.scrollWidth})")
                assert size["document"] <= size["viewport"], (width, path, size)
                assert page.locator("h1").count() == 1, path
                links.update(page.locator("a[href]").evaluate_all("links => links.map(a => a.getAttribute('href')).filter(h => h.startsWith('/') || h.startsWith('#'))"))
                results.append({"width": width, "path": path, "status": response.status, "overflow": False})
                if width in (1440, 390) and path in ("/", "/reports", "/download", "/contact", "/login"):
                    page.evaluate("scrollTo({top:0,behavior:'instant'})")
                    name = path.strip("/") or "home"
                    page.screenshot(path=str(output / f"{name}-{width}.png"))
                    if path == "/":
                        page.screenshot(path=str(output / f"home-{width}-full.png"), full_page=True)
                        if args.visual_only:
                            for section in ("launch-interest", "story-intro", "report-section", "intelligence-section", "client-outcome"):
                                page.locator("." + section).screenshot(path=str(output / f"{section}-{width}.png"))
        if args.visual_only:
            browser.close()
            print("Refreshed ten representative screenshots and two full homepage captures.")
            return
        # Keyboard tabs and workflow playback.
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.goto(args.base_url + "/", wait_until="networkidle")
        page.get_by_role("tab", name="Validate").focus()
        page.keyboard.press("ArrowRight")
        assert page.get_by_role("tab", name="Capture").get_attribute("aria-selected") == "true"
        assert page.locator("#panel-capture").is_visible()
        page.keyboard.press("End")
        assert page.locator("#panel-document").is_visible()
        page.get_by_role("tab", name="Analyze").click()
        assert page.locator("#panel-analyze").is_visible()
        page.get_by_role("button", name="Play walkthrough").click()
        assert page.locator("#panel-validate").is_visible()
        page.get_by_role("button", name="Pause walkthrough").click()
        page.emulate_media(reduced_motion="reduce")
        page.get_by_role("button", name="Play walkthrough").click()
        assert page.locator("#panel-document").is_visible()
        # Report lightbox, focus restoration, keyboard close.
        page.goto(args.base_url + "/reports", wait_until="networkidle")
        opener = page.locator("[data-report-page]").first
        opener.click()
        assert page.locator("dialog").is_visible()
        page.locator("[data-lightbox-image]").wait_for()
        page.screenshot(path=str(output / "report-lightbox.png"))
        page.keyboard.press("Escape")
        assert not page.locator("dialog").is_visible()
        assert opener.evaluate("e => e === document.activeElement")
        # Mobile navigation.
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(args.base_url + "/", wait_until="networkidle")
        toggle = page.get_by_role("button", name="Menu")
        toggle.click()
        assert toggle.get_attribute("aria-expanded") == "true"
        page.screenshot(path=str(output / "mobile-menu.png"))
        page.keyboard.press("Escape")
        assert toggle.get_attribute("aria-expanded") == "false"
        page.goto(args.base_url + "/download", wait_until="networkidle")
        assert page.get_by_role("button", name="Download for Windows").is_disabled()
        assert page.locator('a[href="/download/latest"]').count() == 0
        # Full public link and anchor inventory, without generating account mutations.
        for href in sorted(links):
            if href.startswith("#"):
                continue
            parsed = urlparse(href)
            response = context.request.get(args.base_url + parsed.path, max_redirects=0)
            assert response.status in (200, 301, 302, 303), (href, response.status)
            if parsed.fragment:
                page.goto(args.base_url + href, wait_until="domcontentloaded")
                assert page.locator('[id="' + parsed.fragment + '"]').count(), href
        # Progressive enhancement: report links and full navigation remain available without JS.
        nojs = browser.new_context(java_script_enabled=False, viewport={"width":390,"height":844})
        fallback = nojs.new_page()
        fallback.goto(args.base_url + "/reports")
        assert fallback.locator("#site-nav").is_visible()
        assert urlparse(fallback.locator("[data-report-page]").first.get_attribute("href")).path.endswith("-large.webp")
        nojs.close()
        browser.close()
    assert not errors, errors
    assert not failed, failed
    report = {"pages_and_widths":results,"interactions":"passed","console_errors":errors,"failed_responses":failed,"links_checked":len(links)}
    (output / "ui-results.json").write_text(json.dumps(report,indent=2), encoding="utf-8")
    print(f"PASS: {len(results)} page/viewport checks, {len(links)} links, workflow tabs, reduced motion, report lightbox, mobile navigation, no-JS fallback. No console errors or failed assets.")


if __name__ == "__main__":
    main()
