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

    marital = (extraction.marital_status or "").strip()
    non_single_statuses = {"متزوج", "متزوجة", "مطلق", "مطلقة", "أرمل", "أرملة"}
    if marital in non_single_statuses and extraction.children_count is None:
        missing.append("children_count")

    errors: list[str] = []
    if extraction.age is not None and extraction.age < 18:
        errors.append("العمر يجب أن يكون 18 سنة أو أكثر")
    if extraction.children_count is not None and extraction.children_count < 0:
        errors.append("عدد الأولاد لا يمكن أن يكون رقماً سالباً")
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
        "عدد الأولاد": "children_count", "الأولاد": "children_count", "الاولاد": "children_count",
        "المهنة": "occupation", "العمل": "occupation", "التعليم": "education",
        "المستوى التعليمي": "education", "الدراسة": "education", "الجنسية": "nationality", "الديانة": "religion", "الدين": "religion",
        "الشكل": "appearance", "المظهر": "appearance", "الطول": "height", "الوزن": "weight",
        "المواصفات": "description", "المواصفات الشخصية": "description", "المطلوب": "partner_requirements",
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
        elif key == "children_count":
            digits = normalize_digits(raw_value)
            try:
                value = int(digits)
            except ValueError:
                continue
        elif key == "age":
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
    if any(token in v for token in ("أنثى", "انثى", "بنت", "عروس", "صبية", "female")):
        return "female"
    if any(token in v for token in ("ذكر", "شاب", "عريس", "رجل", "male")):
        return "male"
    return value.strip()


def _gender_label(gender: str | None) -> str:
    return "👩" if gender == "female" else "👨" if gender == "male" else "👤"


def _location_label(profile: dict) -> str:
    province = str(profile.get("province") or "—").strip()
    city = str(profile.get("city") or "").strip()
    if not city or city == province:
        return province
    return f"{province} - {city}"


def _children_label(value: Any) -> str:
    if value is None:
        return "—"
    try:
        count = int(value)
    except (TypeError, ValueError):
        return str(value)
    if count == 0:
        return "لا يوجد"
    if count == 1:
        return "ولد واحد"
    if count == 2:
        return "ولدان"
    if count in {3, 4, 5, 6, 7, 8, 9, 10}:
        return f"{count} أولاد"
    return str(count)


def _format_contact_secret(profile: dict) -> str:
    contact_lines = []
    if profile.get("phone"):
        contact_lines.append(f"📱 الهاتف: {profile['phone']}")
    if profile.get("whatsapp"):
        contact_lines.append(f"🟢 واتساب: {profile['whatsapp']}")
    if profile.get("telegram_username"):
        contact_lines.append(f"✈️ Telegram: @{str(profile['telegram_username']).lstrip('@')}")
    return "\n".join(contact_lines)


def format_client_profile(profile: dict) -> str:
    lines = [
        f"💍 طلب زواج (رقم الطلب: {profile.get('request_number', '—')})",
        "",
        f"{_gender_label(profile.get('gender'))} الاسم: {profile.get('name') or '—'}",
        f"🎂 العمر: {profile.get('age', '—')} سنة",
        f"📍 الإقامة: سوريا - {_location_label(profile)}",
    ]
    if profile.get("occupation"):
        lines.append(f"💼 العمل: {profile['occupation']}")
    if profile.get("education"):
        lines.append(f"📚 المستوى التعليمي: {profile['education']}")
    if profile.get("marital_status"):
        lines.append(f"💍 الحالة الاجتماعية: {profile['marital_status']}")
    if profile.get("marital_status") in {"متزوج", "متزوجة", "مطلق", "مطلقة", "أرمل", "أرملة"}:
        lines.append(f"👶 عدد الأولاد: {_children_label(profile.get('children_count'))}")
    if profile.get("nationality") and profile.get("religion"):
        lines.append(f"🪪 الجنسية والديانة: {profile['nationality']}، {profile['religion']}")
    elif profile.get("nationality"):
        lines.append(f"🪪 الجنسية: {profile['nationality']}")
    elif profile.get("religion"):
        lines.append(f"🕌 الديانة: {profile['religion']}")

    personal_lines: list[str] = []
    if profile.get("height") is not None:
        personal_lines.append(f"📏 الطول: {profile['height']:g} سم")
    if profile.get("weight") is not None:
        personal_lines.append(f"⚖️ الوزن: {profile['weight']:g} كغم")
    if profile.get("appearance"):
        personal_lines.append(f"👤 الشكل: {profile['appearance']}")
    if personal_lines:
        lines.extend(["", "💗 المواصفات الشخصية:", *personal_lines])
    elif profile.get("description"):
        lines.extend(["", f"💗 المواصفات الشخصية:\n{profile['description']}"])
    if profile.get("description") and personal_lines:
        lines.append(f"📝 تفاصيل: {profile['description']}")
    if profile.get("partner_requirements"):
        lines.extend(["", f"💙 مواصفات الشريك المطلوب:\n{profile['partner_requirements']}"])
    lines.extend(["", "🔒 معلومات التواصل محفوظة لدى الصفحة."])
    return "\n".join(lines)


def format_admin_profile(profile: dict) -> str:
    text = format_client_profile(profile).replace(
        "🔒 معلومات التواصل محفوظة لدى الصفحة.",
        "🔐 معلومات التواصل:",
    )
    contact_lines = _format_contact_secret(profile)
    if profile.get("status"):
        contact_lines = (contact_lines + "\n" if contact_lines else "") + f"📊 الحالة: {profile['status']}"
    return text + ("\n" + contact_lines if contact_lines else "")


def format_draft_preview(draft: ProfileDraft) -> str:
    public = draft.public_data
    private = draft.private_contact_data
    lines = [
        "📋 معاينة عرض الزواج",
        "",
        f"{_gender_label(public.get('gender'))} الاسم: {public.get('name') or '—'}",
        f"🎂 العمر: {public.get('age') or '—'} سنة",
        f"📍 الإقامة: سوريا - {_location_label(public)}",
        f"💼 العمل: {public.get('occupation') or '—'}",
        f"📚 المستوى التعليمي: {public.get('education') or '—'}",
        f"💍 الحالة الاجتماعية: {public.get('marital_status') or '—'}",
    ]
    if public.get("marital_status") in {"متزوج", "متزوجة", "مطلق", "مطلقة", "أرمل", "أرملة"}:
        lines.append(f"👶 عدد الأولاد: {_children_label(public.get('children_count'))}")
    if public.get("nationality") and public.get("religion"):
        lines.append(f"🪪 الجنسية والديانة: {public['nationality']}، {public['religion']}")
    elif public.get("nationality"):
        lines.append(f"🪪 الجنسية: {public['nationality']}")
    elif public.get("religion"):
        lines.append(f"🕌 الديانة: {public['religion']}")
    if public.get("height") is not None:
        lines.append(f"📏 الطول: {public['height']:g} سم")
    if public.get("weight") is not None:
        lines.append(f"⚖️ الوزن: {public['weight']:g} كغم")
    if public.get("appearance"):
        lines.append(f"👤 الشكل: {public['appearance']}")
    if public.get("description"):
        lines.extend(["", f"💗 المواصفات الشخصية:\n{public['description']}"])
    if public.get("partner_requirements"):
        lines.extend(["", f"💙 مواصفات الشريك المطلوب:\n{public['partner_requirements']}"])
    if private.get("phone"):
        masked = str(private["phone"])
        lines.append(f"\n🔐 رقم الهاتف: {masked[:3] + '****' + masked[-2:] if len(masked) >= 5 else '********'}")
    elif private.get("telegram_username") or private.get("whatsapp"):
        lines.append("\n🔐 وسيلة التواصل: موجودة")
    else:
        lines.append("\n🔐 وسيلة التواصل: غير موجودة")
    return "\n".join(lines)
