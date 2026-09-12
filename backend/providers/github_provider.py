"""
GitHub Dataset Data Provider
============================

Supplementary data source: Vonter/india-mplads-works GitHub dataset.

This provides recommended works data (MP name, work description,
constituency, state, allocation amount, status).

Note: This dataset does NOT include expenditure, completion percentage,
or sanctioned amount at the project level. It supplements the primary
CSV-uploaded dataset.

When an official MPLADS API becomes available, it should be added
as a separate provider — not replace this one.
"""

import csv
import io
import logging
import urllib.request
import urllib.error
from typing import Dict, Any

from providers.base import DataProvider, SyncResult
from providers.normalizer import (
    normalize_string,
    normalize_state,
    parse_amount,
)
from providers.storage import (
    upsert_recommended_works_batch,
    record_sync,
)
from database import SessionLocal

logger = logging.getLogger("mplads.providers.github")

# Vonter/india-mplads-works dataset
GITHUB_CSV_URL = (
    "https://raw.githubusercontent.com/Vonter/india-mplads-works"
    "/main/csv/MPLADS.csv"
)
GITHUB_TIMEOUT = 30  # seconds
MAX_RECORDS = 200000  # Safety limit


class GithubDatasetProvider(DataProvider):
    """Data provider for the Vonter GitHub MPLADS dataset."""

    @property
    def name(self) -> str:
        return "github"

    @property
    def display_name(self) -> str:
        return "GitHub MPLADS Dataset"

    @property
    def description(self) -> str:
        return (
            "Supplementary dataset from Vonter/india-mplads-works on GitHub. "
            "Provides recommended works data (MP name, work, constituency, "
            "state, allocation). Does not include expenditure or completion data."
        )

    def capabilities(self) -> Dict[str, bool]:
        return {
            "projects": False,
            "recommended_works": True,
            "expenditure": False,
            "completion": False,
            "risk_scores": False,
            "mp_summaries": False,
        }

    def is_available(self) -> bool:
        """Check if the GitHub dataset URL is reachable."""
        try:
            req = urllib.request.Request(
                GITHUB_CSV_URL,
                method="HEAD",
                headers={"User-Agent": "MPLADS-AI-HealthCheck/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    def sync(self, **kwargs) -> SyncResult:
        """
        Fetch and upsert the GitHub MPLADS dataset.

        This fetches the full CSV from GitHub and upserts
        recommended works into the database.
        """
        result = SyncResult(source=self.name)

        try:
            # Fetch CSV from GitHub
            logger.info(f"Fetching MPLADS data from GitHub: {GITHUB_CSV_URL}")
            req = urllib.request.Request(
                GITHUB_CSV_URL,
                headers={"User-Agent": "MPLADS-AI-Sync/1.0"},
            )
            with urllib.request.urlopen(req, timeout=GITHUB_TIMEOUT) as response:
                csv_content = response.read().decode("utf-8")

            # Parse CSV (semicolon-delimited)
            reader = csv.DictReader(io.StringIO(csv_content), delimiter=";")
            rows = list(reader)
            result.records_fetched = len(rows)

            if not rows:
                result.mark_failed("GitHub dataset is empty")
                return result

            # Normalize rows into canonical recommended work format
            normalized = []
            for row in rows[:MAX_RECORDS]:
                work = self._normalize_work_row(row)
                if work:
                    normalized.append(work)

            # Upsert into database
            db = SessionLocal()
            try:
                counts = upsert_recommended_works_batch(db, normalized)
                result.records_inserted = counts["inserted"]
                result.records_unchanged = counts["unchanged"]
                result.records_failed = counts["failed"]
                result.source_updated_at = "2024-03-04"

                # Record sync
                record_sync(
                    db,
                    source=self.name,
                    status=result.status,
                    records_fetched=result.records_fetched,
                    records_inserted=result.records_inserted,
                    records_unchanged=result.records_unchanged,
                    records_failed=result.records_failed,
                    source_updated_at=result.source_updated_at,
                    details={"url": GITHUB_CSV_URL, "delimiter": ";"},
                )
            finally:
                db.close()

        except urllib.error.URLError as e:
            logger.error(f"GitHub sync failed (network): {e}")
            result.mark_failed(f"Network error: {str(e)}")
        except Exception as e:
            logger.error(f"GitHub sync failed: {e}")
            result.mark_failed(str(e))

        return result

    def _normalize_work_row(self, row: Dict) -> Dict[str, Any]:
        """Normalize a GitHub CSV row into canonical recommended work format."""
        try:
            work = normalize_string(row.get("WORK", ""))
            if not work:
                return {}

            return {
                "work_description": work,
                "category": normalize_string(row.get("CATEGORY", "")) or "",
                "mp_name": normalize_string(row.get("MP NAME", "")) or "",
                "constituency": normalize_string(
                    row.get("CONSTITUENCY", "")
                ) or "",
                "state": normalize_state(
                    normalize_string(row.get("STATE", "")) or ""
                ),
                "house": normalize_string(row.get("HOUSE", "")) or "",
                "recommended_amount": parse_amount(
                    row.get("ALLOCATION AMOUNT", "")
                ) or 0.0,
                "recommendation_date": "",
                "has_images": False,
                "ida": normalize_string(row.get("IDA", "")) or "",
            }
        except Exception as e:
            logger.warning(f"Failed to normalize GitHub row: {e}")
            return {}
