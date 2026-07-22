from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass


DEFAULT_PAGES = [
    "/console",
    "/stage?session_name=default",
    "/messenger?session_name=default",
    "/admin",
    "/admin/sessions",
    "/admin/characters",
    "/admin/models",
    "/admin/voice-models",
    "/admin/live2d",
    "/admin/channels",
    "/admin/openwebui",
    "/admin/deployment",
    "/admin/guide",
    "/admin/structure",
]

DEFAULT_VIEWPORTS = [
    "360x800",
    "390x844",
    "430x932",
    "768x1024",
    "1280x900",
]


@dataclass(frozen=True, slots=True)
class Viewport:
    width: int
    height: int

    @classmethod
    def parse(cls, value: str) -> "Viewport":
        width, separator, height = value.lower().partition("x")
        if not separator:
            raise argparse.ArgumentTypeError(f"invalid viewport: {value}")
        try:
            return cls(width=int(width), height=int(height))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid viewport: {value}") from exc

    @property
    def label(self) -> str:
        return f"{self.width}x{self.height}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run EchoBot browser smoke checks with Playwright.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--page", "--pages", action="append", dest="pages")
    parser.add_argument(
        "--viewport",
        "--viewports",
        action="append",
        type=Viewport.parse,
        default=None,
        help="Viewport in WIDTHxHEIGHT form. Can be passed multiple times.",
    )
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is not installed. Install it with: "
            "python -m pip install playwright && python -m playwright install chromium",
            file=sys.stderr,
        )
        return 2

    pages = args.pages or DEFAULT_PAGES
    viewports = args.viewport or [Viewport.parse(item) for item in DEFAULT_VIEWPORTS]
    failures: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        try:
            for viewport in viewports:
                context = browser.new_context(
                    viewport={"width": viewport.width, "height": viewport.height},
                    device_scale_factor=1,
                )
                try:
                    for page_path in pages:
                        failures.extend(
                            _check_page(
                                context,
                                base_url=args.base_url.rstrip("/"),
                                page_path=page_path,
                                viewport=viewport,
                            )
                        )
                finally:
                    context.close()
        finally:
            browser.close()

    if failures:
        print("Browser smoke failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Browser smoke passed.")
    return 0


def _check_page(context, *, base_url: str, page_path: str, viewport: Viewport) -> list[str]:
    failures: list[str] = []
    page = context.new_page()
    console_errors: list[str] = []
    uncaught_errors: list[str] = []
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: uncaught_errors.append(str(error)))
    url = f"{base_url}{page_path}"
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
        if response is None or response.status >= 400:
            status = response.status if response is not None else "no response"
            failures.append(f"{viewport.label} {page_path}: HTTP {status}")
            return failures
        page.wait_for_selector("body", timeout=5000)
        body_text = page.locator("body").inner_text(timeout=5000).strip()
        if not body_text:
            failures.append(f"{viewport.label} {page_path}: empty body text")
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - window.innerWidth"
        )
        if overflow > 2:
            failures.append(
                f"{viewport.label} {page_path}: horizontal overflow {overflow}px"
            )
        reported_page_errors = page.evaluate(
            """() => Array.from(document.querySelectorAll('[data-page-error]'))
                .map((node) => node.textContent || '')
                .filter(Boolean)"""
        )
        for page_error in reported_page_errors:
            failures.append(f"{viewport.label} {page_path}: reported error: {page_error}")
        for uncaught_error in uncaught_errors:
            failures.append(
                f"{viewport.label} {page_path}: page error: {uncaught_error}"
            )
        for console_error in console_errors:
            failures.append(
                f"{viewport.label} {page_path}: console error: {console_error}"
            )
    except Exception as exc:
        failures.append(f"{viewport.label} {page_path}: {exc}")
    finally:
        page.close()
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
