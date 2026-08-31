"""Google Gemini integration with validated structured output."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AIExtractionError(RuntimeError):
    """Raised when configured Gemini extraction cannot be completed."""


class ProfileExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    gender: str | None = Field(default=None, description="male or female")
    name: str | None = None
    age: int | None = None
    province: str | None = None
    city: str | None = None
    marital_status: str | None = None
    occupation: str | None = None
    height: float | None = None
    weight: float | None = None
    description: str | None = None
    partner_requirements: str | None = None
    phone: str | None = None
    telegram_username: str | None = None
    whatsapp: str | None = None
    photo_file_id: str | None = None


class SearchFilterExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    gender: str | None = Field(default=None, description="male or female")
    province: str | None = None
    city: str | None = None
    age_min: int | None = None
    age_max: int | None = None
    marital_status: str | None = None
    occupation: str | None = None


PROFILE_SCHEMA_INSTRUCTIONS = """
أنت مسؤول عن تحويل إعلان زواج سوري خام إلى بيانات منظمة قابلة للحفظ.

قواعد صارمة:
- استخرج المعلومات الموجودة فعلياً في النص فقط، ولا تخترع أي قيمة.
- إذا كانت القيمة غير موجودة أو غير مؤكدة، أعدها null.
- الاسم هو اسم الشخص نفسه فقط. إذا وردت صيغة مثل «اسمي آية» أو «الاسم: آية» فالقيمة تكون «آية» فقط، وليس العبارة كاملة.
- العمر يجب فهمه من صيغ سورية شائعة مثل «عمري 25»، «عمري: 25»، «العمر 25»، «25 سنة».
- المحافظة تعني محافظة سورية محددة مثل دمشق أو حلب أو ريف دمشق. كلمة «سوريا» وحدها لا تعني محافظة ولا يجوز تحويلها إلى محافظة.
- المدينة تستخرج فقط إذا ذُكرت بوضوح.
- لا تستنتج جنس صاحب الإعلان من مواصفات الشريك. مثلاً «بدي شب» تعني أن الشريك المطلوب ذكر، ولا تثبت أن صاحب الإعلان أنثى.
- افهم الأخطاء الإملائية واللهجة السورية الشائعة بحذر، لكن لا تحوّل الكلام غير الواضح إلى حقيقة.
- «بدي شب...»، «بدي شاب...»، «بدها شاب...»، «مواصفات الشريك...» تعني مواصفات الشريك المطلوب وتوضع في partner_requirements.
- الهاتف وTelegram وWhatsApp بيانات سرية وتُنقل فقط إلى الحقول الخاصة بها.
- لا تضع أرقام التواصل داخل description أو partner_requirements إذا كان الرقم مجرد وسيلة تواصل.
- النص الأصلي هو المصدر الوحيد للحقيقة.
"""


def _remove_private_contact_values(value: str | None) -> str | None:
    """Remove phone/contact fragments from free-text fields to prevent privacy leaks."""
    if not value:
        return None
    text = value.strip()
    phone_pattern = r"(?:\+?963\s?)?(?:0?9|09)[0-9xX][0-9xX -]{5,}"
    text = re.sub(rf"(?:رقمي|رقم(?:ي)?\s*الهاتف|الهاتف|الموبايل|المحمول)\s*[:=-]?\s*{phone_pattern}", "", text, flags=re.I)
    text = re.sub(phone_pattern, "", text)
    text = re.sub(r"(?:واتساب|واتس|whatsapp|telegram|تلغرام|تيليجرام)\s*[:=@]?\s*[@A-Za-z0-9_+\- ]+", "", text, flags=re.I)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" -:،,") or None


def _normalize_name(value: str | None) -> str | None:
    if not value:
        return None
    name = value.strip()
    lowered = name.lower()
    generic_fragments = (
        "بنت من", "شاب من", "عروس من", "عريس من", "فتاة من", "رجل من", "امرأة من",
    )
    if any(fragment in lowered for fragment in generic_fragments):
        return None
    if name in {"بنت", "شاب", "عروس", "عريس", "فتاة", "رجل", "امرأة"}:
        return None
    return name


def merge_private_contacts(
    ai_extraction: ProfileExtraction, deterministic_extraction: ProfileExtraction
) -> ProfileExtraction:
    """Merge only facts explicitly found in raw text, with deterministic contacts taking priority."""
    updates: dict[str, Any] = {
        "phone": deterministic_extraction.phone,
        "telegram_username": deterministic_extraction.telegram_username,
        "whatsapp": deterministic_extraction.whatsapp,
    }
    public_fields = (
        "gender", "name", "age", "province", "city", "marital_status", "occupation",
        "height", "weight", "description", "partner_requirements",
    )
    for field_name in public_fields:
        ai_value = getattr(ai_extraction, field_name)
        deterministic_value = getattr(deterministic_extraction, field_name)
        if ai_value is None and deterministic_value is not None:
            updates[field_name] = deterministic_value
    return ai_extraction.model_copy(update=updates)


def normalize_profile_extraction(extraction: ProfileExtraction) -> ProfileExtraction:
    from app.services.profiles import normalize_digits, normalize_gender

    updates = {
        "gender": normalize_gender(extraction.gender) if extraction.gender else None,
        "name": _normalize_name(extraction.name),
        "province": extraction.province.strip() if extraction.province else None,
        "city": extraction.city.strip() if extraction.city else None,
        "marital_status": extraction.marital_status.strip() if extraction.marital_status else None,
        "occupation": extraction.occupation.strip() if extraction.occupation else None,
        "description": _remove_private_contact_values(extraction.description),
        "partner_requirements": _remove_private_contact_values(extraction.partner_requirements),
        "phone": normalize_digits(extraction.phone.strip()) if extraction.phone else None,
        "telegram_username": extraction.telegram_username.strip().lstrip("@") if extraction.telegram_username else None,
        "whatsapp": normalize_digits(extraction.whatsapp.strip()) if extraction.whatsapp else None,
    }
    return extraction.model_copy(update=updates)


class AIService:
    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash-lite") -> None:
        self._api_key = api_key.strip() if api_key else None
        self.model = model
        self._client: Any | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if not self._api_key:
            raise RuntimeError("AI_API_KEY is not configured")
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise RuntimeError("google-genai package is not installed") from exc
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def extract_profile_sync(self, raw_text: str) -> ProfileExtraction:
        client = self._get_client()
        from google.genai import types

        response = client.models.generate_content(
            model=self.model,
            contents=f"{PROFILE_SCHEMA_INSTRUCTIONS}\n\nالنص الخام:\n{raw_text}",
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=ProfileExtraction,
            ),
        )
        return ProfileExtraction.model_validate_json(response.text)

    async def extract_profile(self, raw_text: str) -> ProfileExtraction:
        return await asyncio.to_thread(self.extract_profile_sync, raw_text)

    @staticmethod
    async def resolve_profile_extraction(
        ai_service: "AIService",
        raw_text: str,
        deterministic_extraction: ProfileExtraction,
    ) -> ProfileExtraction:
        """Use configured Gemini as the primary parser; never silently fallback on AI failure."""
        if not ai_service.is_configured:
            raise AIExtractionError("Gemini is not configured")
        try:
            ai_extraction = await ai_service.extract_profile(raw_text)
        except Exception as exc:
            raise AIExtractionError(f"Gemini extraction failed: {type(exc).__name__}") from exc

        return normalize_profile_extraction(
            merge_private_contacts(ai_extraction, deterministic_extraction)
        )

    def parse_search_filters_sync(self, raw_text: str) -> SearchFilterExtraction:
        client = self._get_client()
        from google.genai import types

        prompt = """
استخرج فلاتر البحث فقط من طلب المستخدم العربي. لا تخترع أي فلتر غير مذكور.
الجنس male/female، المحافظة، المدينة، الحد الأدنى والأقصى للعمر، الحالة الاجتماعية، المهنة.
"""
        response = client.models.generate_content(
            model=self.model,
            contents=f"{prompt}\n\nطلب المستخدم:\n{raw_text}",
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=SearchFilterExtraction,
            ),
        )
        return SearchFilterExtraction.model_validate_json(response.text)

    async def parse_search_filters(self, raw_text: str) -> SearchFilterExtraction:
        return await asyncio.to_thread(self.parse_search_filters_sync, raw_text)


def basic_profile_extraction(raw_text: str, photo_file_id: str | None = None) -> ProfileExtraction:
    """Conservative local extraction for explicit-fact supplement and privacy validation."""
    from app.services.profiles import normalize_digits

    normalized = normalize_digits(raw_text.replace("،", " ")).strip()
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    joined = " ".join(lines)

    gender = None
    if any(token in joined for token in ("أنثى", "انثى", "بنت", "عروس")):
        gender = "female"
    elif any(token in joined for token in ("ذكر", "شاب", "عريس")):
        gender = "male"

    age = None
    age_patterns = (
        r"(?:عمري|عمري أنا|عمرها|عمره|العمر|عمر)\s*[:=-]?\s*(\d{2})",
        r"(?<!\d)(\d{2})(?:\s*)(?:سنة|سنين|عام)",
    )
    for pattern in age_patterns:
        match = re.search(pattern, normalized)
        if not match:
            continue
        candidate = int(match.group(1))
        if 18 <= candidate <= 100:
            age = candidate
            break

    province_names = (
        "ريف دمشق", "دمشق", "حلب", "حمص", "حماة", "اللاذقية", "طرطوس", "إدلب",
        "الرقة", "دير الزور", "الحسكة", "درعا", "السويداء", "القنيطرة",
    )
    province = next((item for item in province_names if item in joined), None)

    phone = None
    phone_match = re.search(r"(?:\+?963\s?)?(?:0?9|09)[0-9xX][0-9xX -]{5,}", normalized)
    if phone_match:
        phone = phone_match.group(0).strip()

    telegram_username = None
    telegram_match = re.search(r"(?:telegram|تلغرام|تيليجرام)\s*[:=@]?\s*@?([A-Za-z0-9_]{3,})", normalized, re.I)
    if telegram_match:
        telegram_username = telegram_match.group(1)

    whatsapp = None
    whatsapp_match = re.search(r"(?:whatsapp|واتساب|واتس)\s*[:=@]?\s*([+0-9][+0-9 xX-]{6,})", normalized, re.I)
    if whatsapp_match:
        whatsapp = whatsapp_match.group(1).strip()

    marital_status = None
    for value in ("عزباء", "عازبة", "عازب", "متزوجة", "متزوج", "مطلقة", "مطلق", "أرملة", "أرمل"):
        if value in joined:
            marital_status = value
            break

    height = None
    height_match = re.search(r"(?:طول|الطول)\s*[:=-]?\s*(\d{2,3})(?:\s*سم)?", normalized)
    if height_match:
        height = float(height_match.group(1))

    weight = None
    weight_match = re.search(r"(?:وزن|الوزن)\s*[:=-]?\s*(\d{2,3})(?:\s*كغ|\s*كجم)?", normalized)
    if weight_match:
        weight = float(weight_match.group(1))

    occupation = None
    for marker in ("مدرسة", "مدرس", "مهندس", "طبيب", "ممرض", "موظف", "موظفة", "محامي", "محامية", "تاجر", "متعهد", "ربة منزل"):
        if marker in joined:
            occupation = marker
            break
    occupation_match = re.search(r"(?:المهنة|المهنه|العمل|الوظيفة)\s*[:=-]?\s*([^،,\n]+)", normalized)
    if occupation_match:
        occupation = occupation_match.group(1).strip()

    name = None
    explicit_name_match = re.search(r"(?:اسمي|الاسم)\s*[:=-]?\s*([^\n،,]+)", normalized)
    if explicit_name_match:
        candidate = explicit_name_match.group(1).strip()
        candidate = re.split(r"\s+(?:عمري|من|ساكن|ساكنة)\b", candidate, maxsplit=1)[0].strip()
        if candidate:
            name = candidate

    known = set(province_names) | {
        "أنثى", "انثى", "بنت", "عروس", "ذكر", "شاب", "عريس", "عزباء", "عازبة",
        "عازب", "متزوجة", "متزوج", "مطلقة", "مطلق", "أرملة", "أرمل", "مدرسة",
        "مدرس", "مهندس", "طبيب", "ممرض", "موظف", "موظفة", "محامي", "محامية",
        "تاجر", "متعهد", "ربة منزل",
    }
    if name is None:
        province_index_for_name = next((i for i, line in enumerate(lines) if province and province in line), len(lines))
        for line in lines[:province_index_for_name]:
            if re.fullmatch(r"[0-9+\- xX]+", line):
                continue
            if line == province or line in known:
                continue
            if "سنة" in line or "عام" in line or "عمر" in line or "طول" in line or "وزن" in line:
                continue
            if re.search(r"(?:الهاتف|الواتساب|واتساب|telegram|تلغرام|تيليجرام|رقمي)", line, re.I):
                continue
            if any(token in line for token in ("بنت", "شاب", "عروس", "عريس", "فتاة", "رجل", "امرأة")):
                continue
            if len(line) <= 60 and not any(token in line for token in ("بدها", "بدي", "المواصفات", "المطلوب", "يرغب", "تفضل")):
                name = line
                break

    city = None
    if province:
        province_index = next((i for i, line in enumerate(lines) if province in line), -1)
        if province_index >= 0:
            for line in lines[province_index + 1:province_index + 3]:
                if line and line not in known and line != name and len(line) <= 40 and not re.search(r"\d", line):
                    city = line
                    break

    description = None
    requirement = None
    desc_markers = ("المواصفات", "صفاتها", "صفاته", "الوصف")
    req_markers = ("المطلوب", "مواصفات الشريك", "بدها شاب", "بدي شاب", "بدي شب", "بده شاب", "بدي بنت", "بده بنت", "بده شابة")
    for line in lines:
        if any(marker in line for marker in desc_markers):
            description = line.split(":", 1)[1].strip() if ":" in line else line
        if any(marker in line for marker in req_markers):
            requirement = line.split(":", 1)[1].strip() if ":" in line else line
    if requirement is None:
        requirement_match = re.search(r"((?:بدي|بدها|بده)\s+(?:شب|شاب|بنت|شابة)\b.+)", normalized, re.I)
        if requirement_match:
            requirement = requirement_match.group(1).strip()

    return ProfileExtraction(
        gender=gender,
        name=name,
        age=age,
        province=province,
        city=city,
        marital_status=marital_status,
        occupation=occupation,
        height=height,
        weight=weight,
        description=_remove_private_contact_values(description),
        partner_requirements=_remove_private_contact_values(requirement),
        phone=phone,
        telegram_username=telegram_username,
        whatsapp=whatsapp,
        photo_file_id=photo_file_id,
    )
