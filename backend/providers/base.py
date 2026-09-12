"""
Abstract base class for data providers.

Every data source — CSV upload, GitHub dataset, official API —
must implement this interface. This ensures the rest of the
application is source-agnostic.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class SyncResult:
    """Standardized result returned by every provider's sync() method."""

    def __init__(self, source: str):
        self.source = source
        self.status = "success"
        self.records_fetched = 0
        self.records_inserted = 0
        self.records_updated = 0
        self.records_unchanged = 0
        self.records_failed = 0
        self.source_updated_at: Optional[str] = None
        self.errors: List[str] = []
        self.details: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "records_fetched": self.records_fetched,
            "records_inserted": self.records_inserted,
            "records_updated": self.records_updated,
            "records_unchanged": self.records_unchanged,
            "records_failed": self.records_failed,
            "source_updated_at": self.source_updated_at,
            "errors": self.errors,
            "details": self.details,
        }

    def mark_failed(self, error: str):
        self.status = "failed"
        self.errors.append(error)


class DataProvider(ABC):
    """
    Abstract base class for all data providers.

    Subclasses must implement:
    - name: unique identifier string
    - display_name: human-readable name
    - description: what this provider does
    - sync(): fetch data and upsert into the database
    - is_available(): whether this provider can currently operate

    Optional overrides:
    - configure(): accept provider-specific settings
    - capabilities(): what fields this provider can supply
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier (e.g., 'csv_upload', 'github', 'mplads_api')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g., 'CSV Upload', 'GitHub Dataset')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """What this provider does and what data it supplies."""
        ...

    @abstractmethod
    def sync(self, **kwargs) -> SyncResult:
        """
        Fetch data from this source and upsert into the database.

        Returns a SyncResult with counts of inserted/updated/failed records.
        Must NOT wipe existing data on failure — the previous dataset
        must remain as fallback.
        """
        ...

    def is_available(self) -> bool:
        """Whether this provider can currently operate (e.g., network reachable)."""
        return True

    def capabilities(self) -> Dict[str, bool]:
        """
        What data fields this provider can supply.
        Used to determine if a provider can replace/supplement
        the current dataset.

        Example:
        {
            "projects": True,        # Can supply full project records
            "expenditure": True,     # Can supply expenditure data
            "completion": True,      # Can supply completion percentages
            "risk_scores": False,    # Cannot supply risk scores
            "mp_summaries": False,   # Cannot supply MP summaries
        }
        """
        return {
            "projects": False,
            "recommended_works": False,
            "expenditure": False,
            "completion": False,
            "risk_scores": False,
            "mp_summaries": False,
        }

    def configure(self, **settings):
        """
        Accept provider-specific configuration.
        Override in subclasses that need configuration
        (e.g., API keys, URLs, rate limits).
        """
        pass
