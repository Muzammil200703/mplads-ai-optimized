"""Build a reviewable vendor-enrichment queue from the MPLADS dataset.

The default mode is local-only: it reads the existing ``expenditures`` and
``projects`` tables and writes one JSON object per conservatively-normalized
vendor.  No vendor name is sent to the internet unless an explicit provider
adapter is supplied by the caller.

Example:
    python vendor_enrichment.py --output vendor_candidates.jsonl

An external provider can be connected through a small JSON HTTP adapter:
    python vendor_enrichment.py \
      --search-url-template "https://approved.example/search?q={q}" \
      --output vendor_enrichment.jsonl

The provider response is retained under ``provider_response`` for review; the
script never turns a search result into a legal, registration, or debarment
claim. Provider terms, authentication, rate limits, and permitted fields must
be reviewed before use.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from database import SessionLocal
import models


def normalize_vendor_name(value: Any) -> str:
    """Normalize only case, whitespace, and basic punctuation."""
    value = str(value or "").strip().casefold()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def fetch_json(url: str, timeout: int = 20) -> Any:
    request = Request(url, headers={"User-Agent": "MPLADS-Vendor-Enrichment/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class DuckDuckGoResultParser(HTMLParser):
    """Extract result titles, URLs, and snippets from the HTML result page."""

    def __init__(self):
        super().__init__()
        self.results = []
        self._current = None
        self._capture = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._current = {"title": "", "url": attrs.get("href", ""), "snippet": ""}
            self._capture = "title"
        elif self._current and tag == "a" and "result__snippet" in classes:
            self._capture = "snippet"
        elif self._current and tag == "a" and "result__url" in classes:
            self._capture = "url"

    def handle_data(self, data):
        if self._current and self._capture:
            self._current[self._capture] += data

    def handle_endtag(self, tag):
        if not self._current:
            return
        if tag == "a" and self._capture == "snippet":
            self._capture = None
        elif tag == "a" and self._capture == "title":
            self._capture = None
            self.results.append(self._current)
            self._current = None


def fetch_public_search(query: str, timeout: int = 20) -> list[dict[str, str]]:
    """Fetch public search result metadata; no login or CAPTCHA bypass."""
    from urllib.parse import quote_plus

    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
    request = Request(url, headers={"User-Agent": "MPLADS-Vendor-Enrichment/1.0"})
    with urlopen(request, timeout=timeout) as response:
        parser = DuckDuckGoResultParser()
        parser.feed(response.read().decode("utf-8", errors="replace"))
        results = parser.results[:8]
    if results:
        return results

    # Some networks return an empty DDG result page. Use Google’s public
    # result page as a fallback, without login, CAPTCHA bypass, or form submit.
    import html
    import re
    google_url = "https://www.google.com/search?q=" + quote_plus(query)
    google_request = Request(google_url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(google_request, timeout=timeout) as response:
        page = response.read().decode("utf-8", errors="replace")
    google_results = []
    pattern = re.compile(r'<a[^>]+href="(https?://[^"?]+|/url\\?q=([^&"]+))"[^>]*>.*?<h3[^>]*>(.*?)</h3>', re.I | re.S)
    for match in pattern.finditer(page):
        target = match.group(1)
        if target.startswith("/url?q="):
            target = match.group(2)
        title = re.sub(r"<[^>]+>", " ", html.unescape(match.group(3)))
        target = html.unescape(target)
        if target and not any(item["url"] == target for item in google_results):
            google_results.append({"title": " ".join(title.split()), "url": target, "snippet": ""})
    return google_results[:8]


def search_candidates(candidates: list[dict[str, Any]], delay: float) -> None:
    """Add conservative public-search candidates to each vendor record."""
    email_pattern = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
    phone_pattern = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)")
    for index, item in enumerate(candidates, start=1):
        state = item["states"][0] if item["states"] else ""
        constituency = item["constituencies"][0] if item["constituencies"] else ""
        query_parts = [f'"{item["display_name"]}"']
        if state:
            query_parts.append(f'"{state}"')
        if constituency and constituency.lower() != "sitting rajya sabha":
            query_parts.append(f'"{constituency}"')
        query = " ".join(query_parts + ["contact"])
        record = {"query": query, "results": [], "emails": [], "phones": [], "match_status": "not_found"}
        try:
            results = fetch_public_search(query)
            record["results"] = results
            text = " ".join((result.get("title", "") + " " + result.get("snippet", "")) for result in results)
            vendor_tokens = [token for token in normalize_vendor_name(item["display_name"]).split() if len(token) > 2]
            vendor_hits = sum(1 for token in vendor_tokens if token in normalize_vendor_name(text))
            state_match = bool(state and normalize_vendor_name(state) in normalize_vendor_name(text))
            constituency_match = bool(constituency and normalize_vendor_name(constituency) in normalize_vendor_name(text))
            record["emails"] = sorted(set(email_pattern.findall(text)))
            record["phones"] = sorted(set(phone_pattern.findall(text)))
            record["vendor_token_ratio"] = round(vendor_hits / len(vendor_tokens), 2) if vendor_tokens else 0
            record["state_match"] = state_match
            record["constituency_match"] = constituency_match
            if record["vendor_token_ratio"] >= 0.8 and state_match and constituency_match:
                record["match_status"] = "verified_candidate"
            elif record["vendor_token_ratio"] >= 0.8 and (state_match or constituency_match):
                record["match_status"] = "probable"
            elif results:
                record["match_status"] = "ambiguous"
        except Exception as exc:
            record["match_status"] = "search_error"
            record["error"] = str(exc)
        item["public_search"] = record
        if index % 25 == 0:
            print(f"searched {index}/{len(candidates)}", flush=True)
        if index < len(candidates):
            time.sleep(max(0.0, delay))


def collect_candidates(db) -> list[dict[str, Any]]:
    """Aggregate vendor-linked expenditure context without fuzzy matching."""
    grouped: dict[str, dict[str, Any]] = {}
    project_index: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for project_id, project_name, constituency, state in db.query(
        models.Project.id,
        models.Project.project_name,
        models.Project.constituency,
        models.Project.state,
    ).yield_per(5000):
        project_index[(
            normalize_vendor_name(project_name),
            normalize_vendor_name(constituency),
            normalize_vendor_name(state),
        )].append(project_id)

    rows = db.query(
        models.Expenditure.vendor,
        models.Expenditure.expenditure_amount,
        models.Expenditure.state,
        models.Expenditure.constituency,
        models.Expenditure.work_description,
    ).yield_per(5000)

    for row in rows:
        raw_name = str(row.vendor or "").strip()
        key = normalize_vendor_name(raw_name)
        if not key:
            continue
        item = grouped.setdefault(key, {
            "normalized_name": key,
            "raw_names": set(),
            "record_count": 0,
            "total_expenditure": 0.0,
            "states": set(),
            "constituencies": set(),
            "work_descriptions": set(),
            "project_ids": set(),
        })
        item["raw_names"].add(raw_name)
        item["record_count"] += 1
        item["total_expenditure"] += float(row.expenditure_amount or 0)
        if row.state:
            item["states"].add(str(row.state).strip())
        if row.constituency:
            item["constituencies"].add(str(row.constituency).strip())
        if row.work_description:
            item["work_descriptions"].add(str(row.work_description).strip())
        item["project_ids"].update(project_index.get((
            normalize_vendor_name(row.work_description),
            normalize_vendor_name(row.constituency),
            normalize_vendor_name(row.state),
        ), []))

    candidates = []
    for item in grouped.values():
        raw_names = sorted(item.pop("raw_names"))
        item["display_name"] = raw_names[0]
        item["raw_names"] = raw_names
        item["project_ids"] = sorted(item["project_ids"])
        item["project_count"] = len(item["project_ids"])
        item["total_expenditure"] = round(item["total_expenditure"], 2)
        for field in ("states", "constituencies", "work_descriptions"):
            item[field] = sorted(item[field])
        candidates.append(item)
    return sorted(candidates, key=lambda item: item["total_expenditure"], reverse=True)


def enrich(candidates: list[dict[str, Any]], url_template: str | None, delay: float) -> None:
    """Optionally query one caller-approved JSON endpoint per vendor."""
    if not url_template:
        return
    for index, item in enumerate(candidates):
        url = url_template.format(q=quote_plus(item["display_name"]))
        try:
            item["provider_response"] = fetch_json(url)
            item["provider_status"] = "received"
        except Exception as exc:  # retain the candidate for retry/review
            item["provider_status"] = "error"
            item["provider_error"] = str(exc)
        if index + 1 < len(candidates):
            time.sleep(max(0.0, delay))


def write_jsonl(path: Path, candidates: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract and optionally enrich MPLADS vendor names.")
    parser.add_argument("--output", type=Path, default=Path("vendor_candidates.jsonl"))
    parser.add_argument("--search-url-template", help="Approved JSON endpoint containing {q}; omitted means local-only.")
    parser.add_argument("--public-search", action="store_true", help="Search a public engine with vendor/state/constituency context.")
    parser.add_argument("--max-vendors", type=int, default=0, help="Limit public-search mode for a pilot run; 0 means all vendors.")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between external requests.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        candidates = collect_candidates(db)
    finally:
        db.close()

    enrich(candidates, args.search_url_template, args.delay)
    if args.public_search:
        search_candidates(candidates[:args.max_vendors] if args.max_vendors else candidates, args.delay)
    write_jsonl(args.output, candidates)
    print(json.dumps({
        "output": str(args.output),
        "vendors": len(candidates),
        "external_lookup": bool(args.search_url_template),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
