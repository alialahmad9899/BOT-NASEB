"""Profile validation, draft handling, and public/admin presentation."""

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


NON_SINGLE_STATUSES = {"متزوج", "متزوجة", "مطلق", "مطلقة", "أرمل", "أرملة", "منفصل", "منفصلة"}


def validate_profile_extraction(extraction: ProfileExtraction, private_contact_data: dict[str, Any]) -> ProfileValidation:
    missing: list[str] = []
    if extraction.gender not in {"male", "female"}:
        missing.append("gender")
    if extraction.age is None or not 18 <= extraction.age <= 100:
        missing.append("age")
    if not extraction.residence:
        missing.append("residence")
    if not any(str(private_contact_data.get(key) or "").strip() for key in ("phone", "telegram_username", "whatsapp")):
        missing.append("contact")
    if (extraction.marital_status or "").strip() in NON_SINGLE_STATUSES and extraction.children_count is None:
        missing.append("children_count")
    errors: list[str] = []
    if extraction.children_count is not None and extraction.children_count < 0:
        errors.append("عدد الأولاد لا يمكن أن يكون سالباً")
    return ProfileValidation(tuple(dict.fromkeys(missing)), tuple(errors))


def extraction_to_draft(extraction: ProfileExtraction) -> ProfileDraft:
    public = extraction.model_dump()
    private = {key: public.pop(key, None) for key in ("phone", "telegram_username", "whatsapp")}
    return ProfileDraft(public_data=public, private_contact_data=private)


def apply_text_edits(draft: ProfileDraft, text: str) -> ProfileDraft:
    public = dict(draft.public_data)
    private = dict(draft.private_contact_data)
    aliases = {
        "النوع": "gender", "الجنس": "gender", "الاسم": "name", "العمر": "age",
        "السكن": "residence", "مكان السكن": "residence", "الإقامة": "residence", "مكان الإقامة": "residence",
        "الحالة": "marital_status", "الحالة الاجتماعية": "marital_status",
        "عدد الأولاد": "children_count", "الأولاد": "children_count", "الاولاد": "children_count",
        "المهنة": "occupation", "العمل": "occupation", "التعليم": "education", "الدراسة": "education",
        "المستوى التعليمي": "education", "الشكل": "appearance", "المظهر": "appearance",
        "الطول": "height", "الوزن": "weight", "المطلوب": "partner_requirements",
        "مواصفات الشريك المطلوب": "partner_requirements", "الهاتف": "phone", "رقم الهاتف": "phone",
        "الواتساب": "whatsapp", "واتساب": "whatsapp", "تلغرام": "telegram_username", "telegram": "telegram_username",
    }
    for line in text.splitlines():
        if "=" not in line:
            continue
        raw_key, raw_value = [part.strip() for part in line.split("=", 1)]
        key = aliases.get(raw_key.lower(), raw_key)
        value: Any = raw_value
        if key == "gender": value = normalize_gender(raw_value)
        elif key == "children_count":
            try: value = int(normalize_digits(raw_value))
            except ValueError: continue
        elif key == "age":
            try: value = int(normalize_digits(raw_value))
            except ValueError: continue
        elif key in {"height", "weight"}:
            try: value = float(normalize_digits(raw_value))
            except ValueError: continue
        if key in {"phone", "whatsapp", "telegram_username"}: private[key] = value
        else: public[key] = value
    return ProfileDraft(public_data=public, private_contact_data=private)


def normalize_digits(value: str) -> str:
    return value.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))


def normalize_gender(value: str) -> str:
    value = value.strip().lower()
    if any(token in value for token in ("أنثى", "انثى", "بنت", "صبية", "عروس", "female")): return "female"
    if any(token in value for token in ("ذكر", "شاب", "شب", "عريس", "رجل", "male")): return "male"
    return value


def _gender_label(gender: str | None) -> str:
    return "👩" if gender == "female" else "👨" if gender == "male" else "👤"


def children_label(value: Any) -> str:
    if value is None: return "—"
    count = int(value)
    if count == 0: return "لا يوجد"
    if count == 1: return "ولد واحد"
    if count == 2: return "ولدان"
    return f"{count} أولاد"


def status_label(status: str | None) -> str:
    return {"active": "متاح", "reserved": "محجوز", "inactive": "معطّل"}.get(status or "", status or "غير محدد")


def mask_phone(phone: str | None) -> str:
    if not phone: return ""
    digits = normalize_digits(str(phone)).strip()
    if len(digits) <= 4: return "••••"
    return f"{digits[:2]}{'•' * max(1, len(digits) - 4)}{digits[-2:]}"


def _contact_secret(profile: dict) -> str:
    lines: list[str] = []
    if profile.get("phone"): lines.append(f"📱 الهاتف: {profile['phone']}")
    if profile.get("whatsapp"): lines.append(f"🟢 واتساب: {profile['whatsapp']}")
    if profile.get("telegram_username"): lines.append(f"✈️ Telegram: @{str(profile['telegram_username']).lstrip('@')}")
    return "\n".join(lines)


def _partner_requirements_text(value: Any) -> str:
    if value is None: return "—"
    text = str(value).strip()
    return text or "—"


def format_marriage_post(profile: dict) -> str:
    request_number = profile.get("request_number") or "سيُحدد عند الحفظ"
    lines = [
        f"💍 طلب زواج (رقم الطلب: {request_number})",
        "",
        f"الاسم: {profile.get('name') or '—'} {_gender_label(profile.get('gender'))}",
        "",
        f"العمر: {profile.get('age') or '—'} سنة 🎂",
        "",
        f"الإقامة: سوريا - {profile.get('residence') or '—'} 📍",
    ]
    if profile.get("occupation"): lines.extend(["", f"العمل: {profile['occupation']} 💼"])
    if profile.get("education"): lines.extend(["", f"المستوى التعليمي: {profile['education']} 📚"])
    if profile.get("marital_status"): lines.extend(["", f"الحالة الاجتماعية: {profile['marital_status']} 💍"])
    if profile.get("marital_status") in NON_SINGLE_STATUSES:
        lines.extend(["", f"عدد الأولاد: {children_label(profile.get('children_count'))} 👶"])
    lines.extend([
        "", "المواصفات الشخصية: 💗", "",
        f"الطول: {profile['height']:g} سم" if profile.get("height") is not None else "الطول: —",
        f"الوزن: {profile['weight']:g} كغم" if profile.get("weight") is not None else "الوزن: —",
        f"الشكل: {profile['appearance']}" if profile.get("appearance") else "الشكل: —",
        "", "مواصفات الشريك المطلوب: 💙", "", _partner_requirements_text(profile.get("partner_requirements")), "",
        f"للتواصل: يُرجى المراسلة عبر الرسائل الخاصة لصفحتنا مع ذكر رقم الطلب ({request_number})",
    ])
    if profile.get("status") == "reserved": lines.extend(["", "🔒 تم حجز هذا العرض حالياً."])
    elif profile.get("status") == "inactive": lines.extend(["", "⛔ هذا العرض غير متاح حالياً."])
    return "\n".join(lines)


def format_client_profile(profile: dict, masked_phone: str | None = None) -> str:
    text = format_marriage_post(profile)
    text += "\n\n🔒 معلومات التواصل محفوظة لدى الصفحة."
    if masked_phone: text += f"\n📱 رقم التواصل: {masked_phone}"
    return text


def format_admin_profile(profile: dict) -> str:
    text = format_marriage_post(profile)
    secret = _contact_secret(profile)
    text += f"\n\n🔐 معلومات التواصل للأدمن فقط:\n{secret}" if secret else "\n\n🔐 لا توجد وسيلة تواصل محفوظة."
    text += f"\n📊 حالة العرض: {status_label(profile.get('status'))}"
    return text


def format_draft_preview(draft: ProfileDraft, request_number: int | None = None) -> str:
    public = dict(draft.public_data)
    private = draft.private_contact_data
    public["request_number"] = request_number
    text = format_marriage_post(public)
    secret = _contact_secret({**public, **private})
    if secret: text += f"\n\n🔐 بيانات التواصل للأدمن فقط:\n{secret}"
    else: text += "\n\n🔐 بيانات التواصل للأدمن فقط:\nغير موجودة"
    return text
