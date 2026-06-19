from __future__ import annotations

import logging
from pathlib import Path
from typing import TypedDict

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from src.config import settings


logger = logging.getLogger(__name__)


class SessionCheckResult(TypedDict):
    valid: bool
    current_url: str
    title: str
    reason: str


def _resolve_storage_state_path() -> Path:
    path = Path(settings.playwright_storage_state)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path


def launch_chromium(playwright: Playwright, *, storage_state: str | Path | None = None) -> tuple[Browser, BrowserContext]:
    browser = playwright.chromium.launch(headless=False)

    context_kwargs: dict[str, str] = {}
    if storage_state is not None:
        context_kwargs["storage_state"] = str(storage_state)

    context = browser.new_context(**context_kwargs)
    return browser, context


def open_moodle_for_manual_login() -> Path:
    storage_state_path = _resolve_storage_state_path()
    storage_state_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser, context = launch_chromium(playwright)

        try:
            page = context.new_page()
            logger.info("Opening Moodle home page: %s", settings.moodle_home_url)
            page.goto(settings.moodle_home_url, wait_until="domcontentloaded")

            input(
                "\nBrowser opened for manual login.\n"
                "Log into Moodle manually in the browser window.\n"
                "Do not type your password into the code or terminal.\n"
                "After the Moodle dashboard loads, return here and press Enter to save the session.\n"
            )

            context.storage_state(path=str(storage_state_path))
            logger.info("Saved Playwright storage state to %s", storage_state_path)
        finally:
            context.close()
            browser.close()

    return storage_state_path


def _page_looks_logged_in(page: Page) -> tuple[bool, str]:
    current_url = page.url.lower()
    title = page.title().lower()
    body_text = page.locator("body").inner_text(timeout=5000).lower()

    if "login" in current_url:
        return False, "Current URL still looks like a login page."

    login_indicators = [
        "log in",
        "login",
        "sign in",
        "forgotten your username",
        "forgotten your password",
    ]
    if any(indicator in title for indicator in login_indicators):
        return False, "Page title suggests login is still required."

    if any(indicator in body_text for indicator in login_indicators):
        dashboard_indicators = ["dashboard", "course overview", "my courses", "timeline", "calendar"]
        if not any(indicator in body_text for indicator in dashboard_indicators):
            return False, "Page body strongly suggests login is still required."

    success_indicators = [
        "dashboard",
        "course overview",
        "my courses",
        "timeline",
        "recently accessed courses",
    ]
    if any(indicator in current_url for indicator in ["/my/", "/my"]) or any(
        indicator in body_text for indicator in success_indicators
    ):
        return True, "Dashboard-like content is present and the page does not look like a login form."

    return False, "Saved session loaded, but the page does not clearly look authenticated yet."


def open_moodle_with_saved_session() -> SessionCheckResult:
    storage_state_path = _resolve_storage_state_path()
    if not storage_state_path.exists():
        return {
            "valid": False,
            "current_url": "",
            "title": "",
            "reason": f"Saved session file not found at {storage_state_path}.",
        }

    with sync_playwright() as playwright:
        browser, context = launch_chromium(playwright, storage_state=storage_state_path)

        try:
            page = context.new_page()
            logger.info("Opening Moodle dashboard with saved session: %s", settings.moodle_dashboard_url)
            page.goto(settings.moodle_dashboard_url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=10000)

            valid, reason = _page_looks_logged_in(page)
            title = page.title()

            return {
                "valid": valid,
                "current_url": page.url,
                "title": title,
                "reason": reason,
            }
        finally:
            context.close()
            browser.close()
