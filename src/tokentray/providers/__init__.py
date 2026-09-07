"""Quota providers and the registry that builds them from config."""

from __future__ import annotations

from ..core.cache import Cache
from ..core.config import Config
from .base import BaseProvider, ProviderError, SchemaError
from .claude import ClaudeProvider
from .codex import CodexProvider

PROVIDER_CLASSES: tuple[type[BaseProvider], ...] = (ClaudeProvider, CodexProvider)

__all__ = [
    "BaseProvider",
    "ClaudeProvider",
    "CodexProvider",
    "ProviderError",
    "SchemaError",
    "build_providers",
]


def build_providers(config: Config, cache: Cache | None = None) -> list[BaseProvider]:
    """Instantiate every provider the user has not switched off."""
    cache = cache or Cache()
    providers = [cls(config, cache) for cls in PROVIDER_CLASSES]
    return [p for p in providers if p.enabled]
