"""
MPLADS Data Synchronization — Orchestrator
==========================================

Thin orchestration layer that delegates to data providers.
This is the public API consumed by main.py.

The actual data fetching, normalization, and storage logic
lives in the providers/ package. This module:
1. Routes sync requests to the correct provider
2. Manages the freshness cache
3. Provides convenience functions for the API layer

Adding a new data source requires NO changes to this file —
just register the new provider in providers/__init__.py.
"""

import time
import logging
from typing import Dict, Any, List, Optional

# Import providers to trigger registration
import providers  # noqa: F401 — registers built-in providers

from providers.registry import get_provider, list_providers
from providers.base import SyncResult
from providers.storage import get_last_sync, get_sync_history
from database import SessionLocal
from models import Project

logger = logging.getLogger("mplads.sync")


# ============================================================
# FRESHNESS CACHE
# ============================================================

_sync_status_cache: Dict[str, Any] = {}
_sync_status_cache_ttl: float = 0
SYNC_CACHE_TTL = 60  # seconds


def _get_cached_sync_status() -> Optional[Dict[str, Any]]:
    """Get cached sync status if still valid."""
    if _sync_status_cache and time.time() < _sync_status_cache_ttl:
        return _sync_status_cache
    return None


def _set_cached_sync_status(status: Dict[str, Any]):
    """Cache sync status."""
    global _sync_status_cache, _sync_status_cache_ttl
    _sync_status_cache = status
    _sync_status_cache_ttl = time.time() + SYNC_CACHE_TTL


def invalidate_freshness_cache():
    """Invalidate the freshness cache (called after sync operations)."""
    global _sync_status_cache, _sync_status_cache_ttl
    _sync_status_cache = {}
    _sync_status_cache_ttl = 0


# ============================================================
# PUBLIC API — Used by main.py
# ============================================================


def sync_from_csv_upload(
    csv_content: str,
    filename: str = "upload.csv",
    delimiter: str = ",",
) -> Dict[str, Any]:
    """
    Sync projects from an uploaded CSV file.
    Delegates to the CSV upload provider.
    """
    provider = get_provider("csv_upload")
    result: SyncResult = provider.sync(
        csv_content=csv_content,
        filename=filename,
        delimiter=delimiter,
    )
    invalidate_freshness_cache()
    return result.to_dict()


def sync_from_github() -> Dict[str, Any]:
    """
    Sync from the GitHub MPLADS dataset.
    Delegates to the GitHub dataset provider.
    """
    provider = get_provider("github")
    result: SyncResult = provider.sync()
    invalidate_freshness_cache()
    return result.to_dict()


def sync_from_source(source: str, **kwargs) -> Dict[str, Any]:
    """
    Generic sync from any registered provider.
    This is the main entry point for adding new sources.
    """
    provider = get_provider(source)
    result: SyncResult = provider.sync(**kwargs)
    invalidate_freshness_cache()
    return result.to_dict()


def get_data_freshness() -> Dict[str, Any]:
    """
    Get current data freshness information.
    Returns status, last sync time, and source information.
    """
    cached = _get_cached_sync_status()
    if cached:
        return cached

    db = SessionLocal()
    try:
        last_sync = get_last_sync(db)
        project_count = db.query(Project).count()

        status = {
            "connected": True,
            "project_count": project_count,
            "last_sync": last_sync,
            "source_status": "connected" if project_count > 0 else "no_data",
            "message": "",
        }

        if last_sync:
            synced_at = last_sync.get("synced_at", "")
            source = last_sync.get("source", "unknown")
            try:
                from datetime import datetime, timezone

                sync_dt = datetime.fromisoformat(
                    synced_at.replace("Z", "+00:00")
                )
                now = datetime.now(timezone.utc)
                hours_ago = (now - sync_dt).total_seconds() / 3600

                if hours_ago < 24:
                    status["freshness"] = "fresh"
                    status["message"] = (
                        f"Data synchronized {int(hours_ago)}h ago from {source}"
                    )
                elif hours_ago < 168:
                    status["freshness"] = "stale"
                    status["message"] = (
                        f"Data synchronized {int(hours_ago / 24)}d ago from {source}"
                    )
                else:
                    status["freshness"] = "outdated"
                    status["message"] = (
                        f"Data last synchronized {int(hours_ago / 24)} days ago"
                    )
            except (ValueError, TypeError):
                status["freshness"] = "unknown"
                status["message"] = f"Last sync from {source}"
        else:
            status["freshness"] = "initial"
            status["message"] = "Initial dataset loaded"

        _set_cached_sync_status(status)
        return status

    finally:
        db.close()


def get_available_providers() -> List[Dict[str, Any]]:
    """List all registered data providers."""
    return list_providers()


# Re-export for backward compatibility
__all__ = [
    "sync_from_csv_upload",
    "sync_from_github",
    "sync_from_source",
    "get_data_freshness",
    "get_sync_history",
    "get_available_providers",
    "invalidate_freshness_cache",
]
