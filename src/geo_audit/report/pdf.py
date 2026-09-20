"""PDF through the browser's own print pipeline.

Print-to-PDF rather than a separate PDF renderer, so the print stylesheet in
report.css is the thing that decides page breaks. Two renderers would mean two
sets of layout bugs and a printed report that does not match the HTML anyone
reviewed.

Playwright is optional. Without it the HTML is still written and the caller
says so; the HTML is the guaranteed artifact and the PDF is the convenience.
"""

from __future__ import annotations

from pathlib import Path


def available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def write_pdf(html_path: Path, pdf_path: Path, timeout: float = 60.0) -> str | None:
    """Render `html_path` to `pdf_path`. Returns a reason on failure, else None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "the browser extra is not installed"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--disable-dev-shm-usage"])
            try:
                page = browser.new_page()
                page.goto(html_path.resolve().as_uri(), wait_until="load", timeout=timeout * 1000)
                page.emulate_media(media="print")
                page.pdf(
                    path=str(pdf_path),
                    format="A4",
                    print_background=True,
                    prefer_css_page_size=True,
                    display_header_footer=True,
                    header_template="<div></div>",
                    footer_template=(
                        '<div style="font-size:8pt;color:#5A6472;width:100%;'
                        'padding:0 16mm;text-align:right">'
                        '<span class="pageNumber"></span> / <span class="totalPages"></span>'
                        "</div>"
                    ),
                    margin={"top": "18mm", "right": "16mm", "bottom": "20mm", "left": "16mm"},
                )
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001 - the PDF is never worth failing the run
        return f"the browser failed to render it ({type(exc).__name__})"
    return None
