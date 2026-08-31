"""Domain types that keep public data separate from private contact data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProfileDraft:
    """Preliminary shape for future profile intake, without a final DB schema."""

    public_data: dict[str, Any] = field(default_factory=dict)
    private_contact_data: dict[str, Any] = field(default_factory=dict)
