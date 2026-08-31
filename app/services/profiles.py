"""Profile domain helpers, validation, and safe presentation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.ai import ProfileExtraction


@dataclass(frozen=True)
class ProfileDraft:
    public_data: dict[str, Any] = field(default_factory=dict)
    private_contact_data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProfileValidation:
    missing_fields: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.missing_fields and not self.errors


def validate_profile_extraction(
    extraction: ProfileExtraction, private_contact_data: dict[str, Any]
) -> ProfileValidation:
    missing: list[str] = []
    if extraction.gender not in {"male", "female"}:
        missing.append("gender")
    if extraction.age is None or not 18 <= extraction.age <= 100:
        missing.append("age")
    if not extraction.province:
        missing.append("province")
    has_contact = any(
        str(private_contact_data.get(key) or "").strip()
        for key in ("phone", "telegram_username", "whatsapp")
    )
    if not has_contact:
        missing.append("contact")
    errors: list[str] = []
    if extraction.age is not None and extraction.age < 18:
        errors.append("العمر يجب أن يكون 18 سنة أو أكثر")
    return ProfileValidation(tuple(missing), tuple(errors))


def extraction_to_draft(extraction: ProfileExtraction) -> ProfileDraft:
    public = extraction.model_dump()
    private = {
        "phone": public.pop("phone", None),
        "telegram_username": public.pop("telegram_username", None),
        "whatsapp": public.pop("whatsapp", None),
    }
    return ProfileDraft(public_data=public, private_contact_data=private)


def apply_text_edits(draft: ProfileDraft, text: str) -> ProfileDraft:
    public = dict(draft.public_data)
    private = dict(draft.private_contact_data)
    aliases = {
        "النوع": "gender", "الجنس": "gender", "الاسم": "name", "العمر": "age",
        "المحافظة": "province", "السكن": "city", "المدينة": "city",
        "الحالة": "marital_status", "الحالة الاجتماعية": "marital_status",
        "المهنة": "occupation", "العمل": "occupation", "الطول": "height", "الوزن": "weight",
        "المواصفات": "description", "المطلوب": "partner_requirements",
        "مواصفات الشريك المطلوب": "partner_requirements", "الهاتف": "phone",
        "رقم الهاتف": "phone", "الواتساب": "whatsapp", "تلغرام": "telegram_username",
        "telegram": "telegram_username", "whatsapp": "whatsapp",
    }
    for line in text.splitlines():
        if "=" not in line:
            continue
        raw_key, raw_value = [part.strip() for part in line.split("=", 1)]
        key = aliases.get(raw_key.lower(), raw_key)
        value: Any = raw_value
        if key == "gender":
            value = normalize_gender(raw_value)
        elif key in {"age"}:
            try:
                value = int(normalize_digits(raw_value))
            except ValueError:
                continue
        elif key in {"height", "weight"}:
            try:
                value = float(normalize_digits(raw_value))
            except ValueError:
                continue
        if key in {"phone", "telegram_username", "whatsapp"}:
            private[key] = value
        else:
            public[key] = value
    return ProfileDraft(public_data=public, private_contact_data=private)


def normalize_digits(value: str) -> str:
    table = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    return value.translate(table)


def normalize_gender(value: str) -> str:
    v = value.strip().lower()
    if any(token in v for token in ("أنثى", "انثى", "بنت", "عروس", "female")):
        return "female"
    if any(token in v for token in ("ذكر", "شاب", "عريس", "male")):
        return "male"
    return value.strip()


def _gender_label(gender: str | None) -> str:
    return "👩" if gender == "female" else "👨" if gender == "male" else "👤"


def format_client_profile(profile: dict) -> str:
    lines = [
        "💗 عرض زواج",
        "",
        f"📌 رقم الطلب: {profile.get('request_number', '—')}",
        f"{_gender_label(profile.get('gender'))} العمر: {profile.get('age', '—')}",
        f"📍 السكن: {profile.get('province', '—')}" + (f" - {profile['city']}" if profile.get("city") else ""),
    ]
    if profile.get("marital_status"):
        lines.append(f"💍 الحالة الاجتماعية: {profile['marital_status']}")
    if profile.get("occupation"):
        lines.append(f"💼 العمل: {profile['occupation']}")
    if profile.get("height"):
        lines.append(f"📏 الطول: {profile['height']:g}")
    if profile.get("weight"):
        lines.append(f"⚖️ الوزن: {profile['weight']:g}")
    if profile.get("description"):
        lines.extend(["", f"💗 المواصفات:\n{profile['description']}"])
    if profile.get("partner_requirements"):
        lines.extend(["", f"💙 مواصفات الشريك المطلوب:\n{profile['partner_requirements']}"])
    lines.extend(["", "🔒 معلومات التواصل محفوظة لدى الصفحة."])
    return "\n".join(lines)


def format_admin_profile(profile: dict) -> str:
    text = format_client_profile(profile).replace(
        "🔒 معلومات التواصل محفوظة لدى الصفحة.",
        "🔐 معلومات التواصل:",
    )
    contact_lines = []
    if profile.get("phone"):
        contact_lines.append(f"📱 الهاتف: {profile['phone']}")
    if profile.get("whatsapp"):
        contact_lines.append(f"🟢 واتساب: {profile['whatsapp']}")
    if profile.get("telegram_username"):
        contact_lines.append(f"✈️ Telegram: @{str(profile['telegram_username']).lstrip('@')}")
    if profile.get("status"):
        contact_lines.append(f"📊 الحالة: {profile['status']}")
    return text + ("\n" + "\n".join(contact_lines) if contact_lines else "")


def format_draft_preview(draft: ProfileDraft) -> str:
    public = draft.public_data
    private = draft.private_contact_data
    lines = [
        "📋 معاينة الإعلان",
        "",
        f"{_gender_label(public.get('gender'))} الاسم: {public.get('name') or '—'}",
        f"🎂 العمر: {public.get('age') or '—'}",
        f"📍 المحافظة: {public.get('province') or '—'}",
        f"🏙️ المدينة: {public.get('city') or '—'}",
        f"💍 الحالة الاجتماعية: {public.get('marital_status') or '—'}",
        f"💼 العمل: {public.get('occupation') or '—'}",
        f"📏 الطول: {public.get('height') if public.get('height') is not None else '—'}",
        f"⚖️ الوزن: {public.get('weight') if public.get('weight') is not None else '—'}",
    ]
    if public.get("description"):
        lines.extend(["", f"💗 المواصفات:\n{public['description']}"])
    if public.get("partner_requirements"):
        lines.extend(["", f"💙 المطلوب:\n{public['partner_requirements']}"])
    if private.get("phone"):
        masked = str(private["phone"])
        lines.append(f"\n🔐 رقم الهاتف: {masked[:3] + '****' + masked[-2:] if len(masked) >= 5 else '********'}")
    elif private.get("telegram_username") or private.get("whatsapp"):
        lines.append("\n🔐 وسيلة التواصل: موجودة")
    else:
        lines.append("\n🔐 وسيلة التواصل: غير موجودة")
    return "\n".join(lines)
