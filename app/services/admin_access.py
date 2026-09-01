"""Role-aware administrative access while preserving legacy ADMIN_USER_IDS."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.services.permissions import parse_admin_user_ids


class AdminRole(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    VIEWER = "viewer"


@dataclass(frozen=True)
class AdminAccess:
    owner_ids: frozenset[int]
    manager_ids: frozenset[int]
    viewer_ids: frozenset[int]
    legacy_ids: frozenset[int]

    def role_for(self, user_id: int) -> str | None:
        if user_id in self.owner_ids:
            return AdminRole.OWNER.value
        if user_id in self.manager_ids:
            return AdminRole.MANAGER.value
        if user_id in self.viewer_ids:
            return AdminRole.VIEWER.value
        if user_id in self.legacy_ids:
            return AdminRole.OWNER.value
        return None

    def allowed(self, user_id: int, roles: set[str] | None = None) -> bool:
        role = self.role_for(user_id)
        return role is not None and (roles is None or role in roles)


def build_admin_access(legacy_raw: str, owner_raw: str, manager_raw: str, viewer_raw: str) -> AdminAccess:
    legacy = frozenset(parse_admin_user_ids(legacy_raw))
    owner = frozenset(parse_admin_user_ids(owner_raw))
    manager = frozenset(parse_admin_user_ids(manager_raw))
    viewer = frozenset(parse_admin_user_ids(viewer_raw))
    return AdminAccess(owner, manager, viewer, legacy)
