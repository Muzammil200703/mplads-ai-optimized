"""One-by-one browser enrichment pilot (no search API required).

Uses the locally installed Chrome browser through Playwright, saves each vendor
immediately, and can resume from an existing JSONL output file. This collects
public business contact candidates only; it does not claim that a result is
verified unless the vendor and geographic context are present in the source
page text.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)")
SKIP_HOSTS = {"google.com", "www.google.com", "bing.com", "www.bing.com", "youtube.com", "www.youtube.com"}


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def query_for(item: dict) -> str:
    state = item.get("states", [""])[0] if item.get("states") else ""
    constituency = item.get("constituencies", [""])[0] if item.get("constituencies") else ""
    # Keep the first pass broad enough to find an official organization page;
    # constituency is used for validation after the page is found.
    parts = [item["display_name"]]
    if state:
        parts.append(state)
    return " ".join(parts + ["contact"])


def search_page(page, query: str) -> list[dict]:
    results = []
    # Include common public business-directory terms so the search can surface
    # third-party GST/MSME/company listings in addition to official websites.
    queries = [query, query.replace(" contact", " GST contact"), query.replace(" contact", " Udyam company contact")]
    for search_query in queries:
        search_urls = [
            "https://www.bing.com/search?q=" + quote_plus(search_query),
            "https://www.google.com/search?gbv=1&q=" + quote_plus(search_query),
        ]
        found_for_query = []
        for url in search_urls:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2500)
            except PlaywrightTimeoutError:
                pass
            try:
                body_text = page.locator("body").inner_text(timeout=5000).casefold()
            except Exception:
                body_text = ""
            if any(marker in body_text for marker in ("unusual traffic", "verify you are human", "captcha", "are you a robot")):
                print("CAPTCHA or human verification detected in the browser.", flush=True)
                input("Solve it manually in the visible Chrome window, then press Enter here to continue: ")
                try:
                    page.reload(wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2500)
                except PlaywrightTimeoutError:
                    pass
            anchors = page.locator("a").all()
            for anchor in anchors:
                try:
                    href = anchor.get_attribute("href") or ""
                    text = " ".join((anchor.inner_text(timeout=1000) or "").split())
                except Exception:
                    continue
                # Bing wraps result targets in /ck/a?...&u=a1<base64url>.
                if "bing.com/ck/a" in href and "u=" in href:
                    encoded = parse_qs(urlparse(href).query).get("u", [""])[0]
                    if encoded.startswith("a1"):
                        try:
                            padding = "=" * (-len(encoded[2:]) % 4)
                            href = base64.urlsafe_b64decode(encoded[2:] + padding).decode("utf-8", "ignore")
                        except Exception:
                            continue
                parsed = urlparse(href)
                if parsed.scheme not in ("http", "https") or not text:
                    continue
                if parsed.netloc.casefold() in SKIP_HOSTS or "google.com" in parsed.netloc.casefold() or "bing.com" in parsed.netloc.casefold():
                    continue
                if any(result["url"] == href for result in results + found_for_query):
                    continue
                found_for_query.append({"url": href, "title": text[:300]})
                if len(found_for_query) >= 5:
                    break
            if found_for_query:
                break
        results.extend(found_for_query)
        if len(results) >= 8:
            return results[:8]
    return results


def extract_page_contact(context, result: dict) -> dict:
    page = context.new_page()
    try:
        page.goto(result["url"], wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(400)
        text = page.locator("body").inner_text(timeout=5000)
        result["page_title"] = page.title()[:300]
        result["emails"] = sorted(set(EMAIL.findall(text)))[:10]
        result["phones"] = sorted(set(PHONE.findall(text)))[:10]
        result["page_text_excerpt"] = " ".join(text.split())[:1000]
    except Exception as exc:
        result["page_error"] = str(exc)
    finally:
        page.close()
    return result


def classify(item: dict, results: list[dict]) -> str:
    vendor = norm(item["display_name"])
    tokens = [token for token in vendor.split() if len(token) > 2]
    state = norm(item.get("states", [""])[0] if item.get("states") else "")
    constituency = norm(item.get("constituencies", [""])[0] if item.get("constituencies") else "")
    combined = norm(" ".join((r.get("title", "") + " " + r.get("page_text_excerpt", "")) for r in results))
    ratio = sum(token in combined for token in tokens) / len(tokens) if tokens else 0
    state_match = bool(state and state in combined)
    constituency_match = bool(constituency and constituency in combined)
    if ratio >= 0.8 and state_match and constituency_match:
        return "verified_candidate"
    if ratio >= 0.8 and (state_match or constituency_match):
        return "probable"
    if results:
        return "ambiguous"
    return "not_found"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--headed", action="store_true", help="Use visible Chrome instead of headless mode.")
    args = parser.parse_args()

    candidates = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    candidates = candidates[:args.limit]
    completed = {}
    if args.output.exists():
        for line in args.output.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                completed[item.get("normalized_name")] = item
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed, executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        context = browser.new_context(locale="en-IN")
        page = context.new_page()
        try:
            with args.output.open("a", encoding="utf-8") as handle:
                for index, item in enumerate(candidates, start=1):
                    if item.get("normalized_name") in completed:
                        continue
                    query = query_for(item)
                    try:
                        results = search_page(page, query)
                        # Inspect several result pages so third-party registries
                        # are not missed when an official page ranks first.
                        detailed = [extract_page_contact(context, result) for result in results[:5]]
                    except Exception as exc:
                        # Network resets and browser-tab failures should not
                        # lose the batch. Save the error and recreate the tab.
                        results = []
                        detailed = []
                        item["browser_search_error"] = str(exc)
                        try:
                            page.close()
                        except Exception:
                            pass
                        page = context.new_page()
                    item["browser_search"] = {
                        "query": query,
                        "results": detailed,
                        "emails": sorted({email for result in detailed for email in result.get("emails", [])}),
                        "phones": sorted({phone for result in detailed for phone in result.get("phones", [])}),
                    }
                    item["browser_search"]["match_status"] = classify(item, detailed)
                    handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
                    handle.flush()
                    if index % 25 == 0:
                        print(f"processed {index}/{len(candidates)}", flush=True)
                    time.sleep(max(0.0, args.delay))
        finally:
            context.close()
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
