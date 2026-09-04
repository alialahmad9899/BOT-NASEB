"""Marriage-profile normalization, formatting, and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


NON_SINGLE_STATUSES = {"مطلقة", "مطلق", "أرملة", "أرمل", "متزوجة", "متزوج", "منفصلة", "منفصل"}


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


def format_publishable_draft_preview(draft: "ProfileDraft", request_number: int | None = None) -> str:
    public = dict(draft.public_data)
    public["request_number"] = request_number
    return format_marriage_post(public)


def format_admin_draft_contact(draft: "ProfileDraft") -> str:
    secret = _contact_secret(draft.private_contact_data)
    return f"🔐 بيانات التواصل للأدمن فقط:\n{secret}" if secret else "🔐 بيانات التواصل للأدمن فقط:\nغير موجودة"


def format_draft_preview(draft: "ProfileDraft", request_number: int | None = None) -> str:
    return format_publishable_draft_preview(draft, request_number) + "\n\n" + format_admin_draft_contact(draft)


@dataclass(frozen=True)
class ProfileDraft:
    public_data: dict
    private_contact_data: dict


def extraction_to_draft(extraction: Any) -> ProfileDraft:
    public = {
        "gender": normalize_gender(extraction.gender) if extraction.gender else None,
        "name": extraction.name,
        "age": extraction.age,
        "residence": extraction.residence,
        "marital_status": extraction.marital_status,
        "children_count": extraction.children_count,
        "occupation": extraction.occupation,
        "education": extraction.education,
        "height": extraction.height,
        "weight": extraction.weight,
        "appearance": extraction.appearance,
        "partner_requirements": extraction.partner_requirements,
        "photo_file_id": extraction.photo_file_id,
    }
    private = {
        "phone": extraction.phone,
        "telegram_username": extraction.telegram_username,
        "whatsapp": extraction.whatsapp,
    }
    return ProfileDraft(public_data=public, private_contact_data=private)


def apply_text_edits(draft: ProfileDraft, text: str) -> ProfileDraft:
    public = dict(draft.public_data)
    private = dict(draft.private_contact_data)
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        if not value:
            continue
        mapping = {
            "النوع": "gender", "الاسم": "name", "العمر": "age", "مكان السكن": "residence",
            "الحالة الاجتماعية": "marital_status", "عدد الأولاد": "children_count", "العمل": "occupation",
            "التعليم": "education", "المستوى التعليمي": "education", "الطول": "height", "الوزن": "weight",
            "الشكل": "appearance", "المطلوب": "partner_requirements", "مواصفات الشريك المطلوب": "partner_requirements",
            "رقم الهاتف": "phone", "الهاتف": "phone", "واتساب": "whatsapp", "Telegram": "telegram_username",
        }
        target = mapping.get(key, mapping.get(key.strip().lower()))
        if not target:
            continue
        if target in {"age", "children_count"}:
            try: value = int(normalize_digits(value))
            except ValueError: continue
        elif target in {"height", "weight"}:
            try: value = float(normalize_digits(value))
            except ValueError: continue
        elif target == "gender":
            value = normalize_gender(value)
        if target in {"phone", "whatsapp", "telegram_username"}:
            private[target] = value
        else:
            public[target] = value
    return ProfileDraft(public, private)


@dataclass(frozen=True)
class ProfileValidation:
    missing_fields: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        # Missing values are warnings only. Invalid values remain blocking errors.
        return not self.errors


def validate_profile_extraction(extraction: Any, private_contact_data: dict) -> ProfileValidation:
    missing = []
    gender = extraction.gender.strip().lower() if isinstance(extraction.gender, str) else extraction.gender
    if not gender: missing.append("gender")
    elif gender not in {"male", "female"}: errors_gender = "نوع الإعلان يجب أن يكون عريساً أو عروساً (male/female)."
    else: errors_gender = None
    if extraction.age is None: missing.append("age")
    if not extraction.residence: missing.append("residence")
    if not (private_contact_data.get("phone") or private_contact_data.get("telegram_username") or private_contact_data.get("whatsapp")): missing.append("contact")
    if extraction.marital_status in NON_SINGLE_STATUSES and extraction.children_count is None: missing.append("children_count")
    errors = []
    if errors_gender: errors.append(errors_gender)
    if extraction.age is not None and not 18 <= extraction.age <= 100: errors.append("العمر يجب أن يكون بين 18 و100 سنة.")
    if extraction.children_count is not None and extraction.children_count < 0: errors.append("عدد الأولاد لا يمكن أن يكون سالباً.")
    return ProfileValidation(tuple(missing), tuple(errors))
