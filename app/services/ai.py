"""AI integration boundary.

Phase 1 intentionally contains no provider-specific API calls or parsing logic.
"""

from __future__ import annotations


class AIService:
    """Minimal provider-neutral AI service scaffold for later phases."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key.strip() if api_key else None

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def extract_profile(self, raw_text: str):
        """Reserve the profile extraction interface for Phase 3."""
        raise NotImplementedError("AI profile parsing is intentionally out of scope for Phase 1")
