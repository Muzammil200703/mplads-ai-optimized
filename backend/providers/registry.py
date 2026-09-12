"""
Provider Registry
=================

Manages available data providers and allows dynamic registration.
This is the single entry point for discovering and using providers.
"""

import logging
from typing import Dict, Type, Optional, List

from providers.base import DataProvider

logger = logging.getLogger("mplads.providers")

# ─── Registry ──────────────────────────────────────────────────

_PROVIDER_REGISTRY: Dict[str, Type[DataProvider]] = {}
_ACTIVE_PROVIDER: Optional[str] = None


def register_provider(name: str, provider_class: Type[DataProvider]):
    """Register a data provider class."""
    _PROVIDER_REGISTRY[name] = provider_class
    logger.info(f"Registered data provider: {name}")


def get_provider(name: str, **settings) -> DataProvider:
    """
    Get an instance of a registered provider.

    Raises KeyError if the provider is not registered.
    """
    if name not in _PROVIDER_REGISTRY:
        available = list(_PROVIDER_REGISTRY.keys())
        raise KeyError(
            f"Unknown provider '{name}'. Available: {available}"
        )
    provider = _PROVIDER_REGISTRY[name]()
    if settings:
        provider.configure(**settings)
    return provider


def list_providers() -> List[Dict[str, str]]:
    """List all registered providers with their metadata."""
    result = []
    for name, cls in _PROVIDER_REGISTRY.items():
        try:
            instance = cls()
            result.append({
                "name": instance.name,
                "display_name": instance.display_name,
                "description": instance.description,
                "available": instance.is_available(),
                "capabilities": instance.capabilities(),
            })
        except Exception as e:
            logger.warning(f"Failed to instantiate provider {name}: {e}")
            result.append({
                "name": name,
                "display_name": name,
                "description": f"Error: {str(e)}",
                "available": False,
                "capabilities": {},
            })
    return result


def set_active_provider(name: str):
    """Set the default active provider for sync operations."""
    if name not in _PROVIDER_REGISTRY:
        raise KeyError(f"Unknown provider: {name}")
    global _ACTIVE_PROVIDER
    _ACTIVE_PROVIDER = name
    logger.info(f"Active provider set to: {name}")


def get_active_provider_name() -> str:
    """Get the name of the currently active provider."""
    return _ACTIVE_PROVIDER or "csv_upload"


def get_active_provider(**settings) -> DataProvider:
    """Get an instance of the currently active provider."""
    return get_provider(get_active_provider_name(), **settings)
