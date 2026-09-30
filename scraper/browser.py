"""Shared headless-browser fetch for the Playwright scrapers (Indeed, LinkedIn, Naukri).

Playwright is optional: it is imported lazily and every caller gets ``None`` (and a
logged warning) when it is missing, when the URL isn't allowlisted, or when robots.txt
disallows the page.
"""
from __future__ import annotations

from loguru import logger

from scraper import net

PAGE_TIMEOUT_MS = 30_000
POLITE_WAIT_MS = 2_000


def select_text(node, *selectors: str) -> str:
    """First non-empty text among CSS ``selectors`` under a BS4 node (None-safe, no ``?.``)."""
    for sel in selectors:
        el = node.select_one(sel)
        if el is not None:
            text = el.get_text(" ", strip=True)
            if text:
                return text
    return ""


def select_attr(node, attr: str, *selectors: str) -> str:
    for sel in selectors:
        el = node.select_one(sel)
        if el is not None and el.get(attr):
            return str(el.get(attr)).strip()
    return ""


async def fetch_rendered_html(url: str, source: str, wait_selector: str | None = None) -> str | None:
    """Render ``url`` in headless Chromium and return the page HTML, or ``None``."""
    try:
        net.check_allowed(url)
    except net.FetchBlocked as exc:
        logger.warning("{} skipped: {}", source, exc)
        return None
    try:
        from playwright.async_api import async_playwright  # lazy optional import
    except ImportError:
        logger.warning("{} skipped: Playwright is not installed "
                       "(pip install playwright && playwright install chromium)", source)
        return None

    await net.limiter_for(url).await_turn()
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(user_agent=net.BROWSER_HEADERS["User-Agent"])
                page = await context.new_page()
                await page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
                if wait_selector:
                    try:
                        await page.wait_for_selector(wait_selector, timeout=10_000)
                    except Exception:
                        logger.debug("{}: selector {} not found (layout change or block page)",
                                     source, wait_selector)
                await page.wait_for_timeout(POLITE_WAIT_MS)  # polite wait
                return await page.content()
            finally:
                await browser.close()
    except Exception as exc:  # browser missing, navigation timeout, etc.
        logger.warning("{} browser fetch failed: {}", source, type(exc).__name__)
        return None
