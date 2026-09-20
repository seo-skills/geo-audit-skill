"""Optional Playwright rendering.

Playwright is an extra, never a hard dependency: a tool that cannot run
without a 300 MB browser download is a tool most people never run. When it is
absent the signals that need it are null and `completeness` says so. There is
no second scoring path and no silent substitution.
"""

from __future__ import annotations

from geo_audit.lib.extract import extract
from geo_audit.lib.headers import USER_AGENT


def available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def rendered_content_chars(url: str, timeout: float = 30.0) -> int | None:
    """Characters of extractable content after JavaScript runs, or None.

    None means "not measured" for every reason: the extra is missing, the
    browser binary was never downloaded, or the render failed. The caller
    turns that into a null signal, never into a zero.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--disable-dev-shm-usage"])
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
                html = page.content()
            finally:
                browser.close()
    except Exception:
        return None

    return extract(html, url).content_chars
