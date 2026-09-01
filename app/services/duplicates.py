"""Conservative duplicate detection for marriage profiles."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Profile, ProfileContact


@dataclass(frozen=True)
class DuplicateMatch:
    request_number: int
    score: int
    reasons: tuple[str, ...]
    name: str | None
    age: int
    residence: str


def _sim(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def find_profile_duplicates(session: Session, candidate, limit: int = 5) -> list[DuplicateMatch]:
    public = candidate.public_data
    private = candidate.private_contact_data
    candidate_name = public.get("name")
    candidate_age = public.get("age")
    candidate_residence = public.get("residence")
    candidate_contacts = {str(private.get(k)).strip() for k in ("phone", "whatsapp") if private.get(k)}
    rows = session.scalars(select(Profile).order_by(Profile.id.desc()).limit(500)).all()
    matches: list[DuplicateMatch] = []
    for profile in rows:
        contact = session.get(ProfileContact, profile.id)
        reasons: list[str] = []
        score = 0
        existing_contacts = {str(getattr(contact, k)).strip() for k in ("phone", "whatsapp") if contact and getattr(contact, k)}
        if candidate_contacts & existing_contacts:
            score += 100
            reasons.append("رقم التواصل مطابق")
        if candidate_age is not None and profile.age == int(candidate_age):
            score += 20
            reasons.append("العمر مطابق")
        if candidate_residence and profile.residence and profile.residence.strip().lower() == str(candidate_residence).strip().lower():
            score += 20
            reasons.append("مكان السكن مطابق")
        name_similarity = _sim(candidate_name, profile.name)
        if name_similarity >= 0.92:
            score += 45
            reasons.append("الاسم متشابه جداً")
        elif name_similarity >= 0.78:
            score += 25
            reasons.append("الاسم متشابه")
        if score >= 45:
            matches.append(DuplicateMatch(int(profile.request_number), min(100, score), tuple(reasons), profile.name, profile.age, profile.residence))
    matches.sort(key=lambda item: (-item.score, item.request_number))
    return matches[: max(1, min(limit, 10))]
