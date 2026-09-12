"""
CSV Upload Data Provider
========================

The primary data source: manual CSV upload.
This is the current main way data enters the system.

When an official MPLADS API becomes available, it can be added
as a new provider alongside this one — the CSV provider
remains as fallback.
"""

import csv
import io
import logging
from typing import Dict, Any

from providers.base import DataProvider, SyncResult
from providers.normalizer import (
    normalize_string,
    normalize_state,
    parse_amount,
    parse_percentage,
    parse_int,
    detect_column_mapping,
)
from providers.storage import (
    upsert_projects_batch,
    record_sync,
)
from database import SessionLocal

logger = logging.getLogger("mplads.providers.csv")


class CsvUploadProvider(DataProvider):
    """Data provider for CSV file uploads."""

    @property
    def name(self) -> str:
        return "csv_upload"

    @property
    def display_name(self) -> str:
        return "CSV Upload"

    @property
    def description(self) -> str:
        return (
            "Manual CSV file upload. Accepts any CSV with flexible "
            "column auto-detection. This is the primary/fallback data source."
        )

    def capabilities(self) -> Dict[str, bool]:
        return {
            "projects": True,
            "recommended_works": False,
            "expenditure": True,
            "completion": True,
            "risk_scores": False,
            "mp_summaries": False,
        }

    def sync(
        self,
        csv_content: str = "",
        filename: str = "upload.csv",
        delimiter: str = ",",
        **kwargs,
    ) -> SyncResult:
        """
        Sync projects from an uploaded CSV file.

        Expected CSV columns (flexible auto-mapping):
        - id, project_name, state, district, constituency
        - project_type, sanctioned_amount, expenditure
        - completion_percentage, status, fy
        """
        result = SyncResult(source=self.name)
        result.details = {"filename": filename}

        try:
            # Parse CSV
            reader = csv.DictReader(io.StringIO(csv_content), delimiter=delimiter)
            rows = list(reader)
            result.records_fetched = len(rows)

            if not rows:
                result.mark_failed("CSV file is empty or has no data rows")
                return result

            # Detect column mapping
            headers = list(rows[0].keys())
            col_map = detect_column_mapping(headers)
            result.details["columns"] = headers

            if not col_map.get("project_name"):
                result.mark_failed(
                    f"Could not detect project name column. "
                    f"Found headers: {headers}"
                )
                return result

            # Normalize all rows into canonical format
            normalized_rows = []
            for row in rows:
                normalized = self._normalize_row(row, col_map)
                if normalized:
                    normalized_rows.append(normalized)

            # Upsert into database
            db = SessionLocal()
            try:
                counts = upsert_projects_batch(db, normalized_rows)
                result.records_inserted = counts["inserted"]
                result.records_updated = counts["updated"]
                result.records_unchanged = counts["unchanged"]
                result.records_failed = counts["failed"]

                # Record sync event
                record_sync(
                    db,
                    source=self.name,
                    status=result.status,
                    records_fetched=result.records_fetched,
                    records_inserted=result.records_inserted,
                    records_updated=result.records_updated,
                    records_unchanged=result.records_unchanged,
                    records_failed=result.records_failed,
                    details=result.details,
                )
            finally:
                db.close()

        except Exception as e:
            logger.error(f"CSV upload sync failed: {e}")
            result.mark_failed(str(e))

        return result

    def _normalize_row(self, row: Dict, col_map: Dict) -> Dict[str, Any]:
        """Normalize a CSV row into canonical project format."""
        try:
            project_name = normalize_string(
                row.get(col_map.get("project_name", ""), "")
            )
            if not project_name:
                return {}

            return {
                "id": parse_int(row.get(col_map.get("id", ""), "")),
                "project_name": project_name,
                "state": normalize_state(
                    normalize_string(row.get(col_map.get("state", ""), "")) or ""
                ),
                "district": normalize_string(
                    row.get(col_map.get("district", ""), "")
                ) or "",
                "constituency": normalize_string(
                    row.get(col_map.get("constituency", ""), "")
                ) or "",
                "project_type": normalize_string(
                    row.get(col_map.get("project_type", ""), "")
                ) or "",
                "sanctioned_amount": parse_amount(
                    row.get(col_map.get("sanctioned_amount", ""), "")
                ) or 0.0,
                "expenditure": parse_amount(
                    row.get(col_map.get("expenditure", ""), "")
                ) or 0.0,
                "completion_percentage": parse_percentage(
                    row.get(col_map.get("completion_percentage", ""), "")
                ) or 0.0,
                "status": normalize_string(
                    row.get(col_map.get("status", ""), "")
                ) or "",
                "fy": normalize_string(
                    row.get(col_map.get("fy", ""), "")
                ) or "",
            }
        except Exception as e:
            logger.warning(f"Failed to normalize row: {e}")
            return {}
