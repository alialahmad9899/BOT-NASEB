"""Centralized authorization helpers."""

from __future__ import annotations


def parse_admin_user_ids(raw: str) -> set[int]:
    """Parse comma-separated Telegram user IDs, ignoring malformed values."""
    ids: set[int] = set()
    for value in raw.split(","):
        candidate = value.strip()
        if candidate and candidate.lstrip("-").isdigit():
            ids.add(int(candidate))
    return ids


def is_admin(user_id: int, admin_user_ids: set[int] | frozenset[int]) -> bool:
    """Return whether the Telegram user ID has administrative privileges."""
    return user_id in admin_user_ids
