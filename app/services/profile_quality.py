"""Deterministic profile completeness and quality checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QualityReport:
    score: int
    missing_fields: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.score >= 75 and not self.missing_fields


def score_profile(data: Any) -> QualityReport:
    public = getattr(data, "public_data", data)
    private = getattr(data, "private_contact_data", {})
    score = 0
    missing: list[str] = []
    warnings: list[str] = []

    required = [("gender", "النوع", 15), ("name", "الاسم", 10), ("age", "العمر", 15), ("residence", "مكان السكن", 15)]
    for key, label, points in required:
        if public.get(key) not in (None, ""):
            score += points
        else:
            missing.append(label)

    if any(private.get(key) for key in ("phone", "whatsapp", "telegram_username")):
        score += 15
    else:
        missing.append("وسيلة تواصل")

    if public.get("photo_file_id"):
        score += 10
    else:
        warnings.append("لا توجد صورة مرتبطة بالإعلان")

    if public.get("marital_status"):
        score += 5
    else:
        warnings.append("الحالة الاجتماعية غير مذكورة")

    if public.get("occupation") or public.get("education"):
        score += 5
    else:
        warnings.append("العمل والتعليم غير مذكورين")

    if public.get("appearance"):
        score += 5
    else:
        warnings.append("الوصف الشخصي مختصر")

    if public.get("partner_requirements"):
        score += 10
    else:
        warnings.append("مواصفات الشريك المطلوب غير موجودة")

    if public.get("marital_status") in {"مطلقة", "مطلق", "أرملة", "أرمل", "متزوجة", "متزوج", "منفصلة", "منفصل"} and public.get("children_count") is None:
        missing.append("عدد الأولاد")
        warnings.append("الحالة الاجتماعية تتطلب عدد الأولاد")

    if score >= 90 and not missing:
        warnings.append("الإعلان مكتمل وممتاز للنشر")
    elif score >= 75 and not missing:
        warnings.append("الإعلان جاهز مع بعض الملاحظات الاختيارية")
    return QualityReport(score=min(100, score), missing_fields=tuple(dict.fromkeys(missing)), warnings=tuple(dict.fromkeys(warnings)))
