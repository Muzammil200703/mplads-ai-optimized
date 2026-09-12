"""
MPLADS Data Providers
====================

Source-agnostic data ingestion architecture.

To add a new data source (e.g., an official MPLADS API):
1. Create a new file in this directory (e.g., mplads_api_provider.py)
2. Implement the DataProvider base class
3. Register it in the PROVIDER_REGISTRY below

The rest of the application (sync.py, main.py, frontend) does not
need to change when a new provider is added.
"""

from providers.base import DataProvider
from providers.registry import (
    get_provider,
    list_providers,
    register_provider,
    get_active_provider,
)
from providers.csv_provider import CsvUploadProvider
from providers.github_provider import GithubDatasetProvider

# ─── Register built-in providers ───────────────────────────────
register_provider("csv_upload", CsvUploadProvider)
register_provider("github", GithubDatasetProvider)

__all__ = [
    "DataProvider",
    "get_provider",
    "list_providers",
    "register_provider",
    "get_active_provider",
]
