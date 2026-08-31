"""Google Gemini integration with validated structured output."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
استخرج البيانات من النص السوري العامي دون اختلاق أي معلومة.
القيم غير الموجودة يجب أن تبقى null. الجنس يجب أن يكون male أو female إذا كان واضحاً.
الهاتف وTelegram وWhatsApp بيانات سرية وتُنقل فقط إلى الحقول الخاصة بها.
لا تحوّل المواصفات غير الواضحة إلى أرقام أو حقائق.
"""


def merge_private_contacts(
    ai_extraction: ProfileExtraction, deterministic_extraction: ProfileExtraction
) -> ProfileExtraction:
    """Keep only contact values explicitly recovered by deterministic parsing.

    AI is never trusted as the source of private contact facts. If deterministic
    extraction cannot find a contact value in the raw text, the corresponding
    AI-provided value is discarded rather than persisted.
    """
    return ai_extraction.model_copy(
        update={
            "phone": deterministic_extraction.phone,
            "telegram_username": deterministic_extraction.telegram_username,
            "whatsapp": deterministic_extraction.whatsapp,
        }
    )


def normalize_profile_extraction(extraction: ProfileExtraction) -> ProfileExtraction:
    from app.services.profiles import normalize_digits, normalize_gender

    updates = {
        "gender": normalize_gender(extraction.gender) if extraction.gender else None,
        "name": extraction.name.strip() if extraction.name else None,
        "province": extraction.province.strip() if extraction.province else None,
        "city": extraction.city.strip() if extraction.city else None,
        "marital_status": extraction.marital_status.strip() if extraction.marital_status else None,
        "occupation": extraction.occupation.strip() if extraction.occupation else None,
        "description": extraction.description.strip() if extraction.description else None,
        "partner_requirements": extraction.partner_requirements.strip() if extraction.partner_requirements else None,
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
    """Conservative local fallback for environments where AI is unavailable.

    It extracts only values explicitly present in the raw text; unknown fields remain null.
    """
    import re

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
    age_match = re.search(r"(?<!\d)(\d{2})(?:\s*)(?:سنة|سنين|عام|عمر)", normalized)
    if age_match:
        candidate = int(age_match.group(1))
        if 18 <= candidate <= 100:
            age = candidate

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

    known = set(province_names) | {
        "أنثى", "انثى", "بنت", "عروس", "ذكر", "شاب", "عريس", "عزباء", "عازبة",
        "عازب", "متزوجة", "متزوج", "مطلقة", "مطلق", "أرملة", "أرمل", "مدرسة",
        "مدرس", "مهندس", "طبيب", "ممرض", "موظف", "موظفة", "محامي", "محامية",
        "تاجر", "متعهد", "ربة منزل",
    }
    name = None
    province_index_for_name = next((i for i, line in enumerate(lines) if province and province in line), len(lines))
    for line in lines[:province_index_for_name]:
        if re.fullmatch(r"[0-9+\- xX]+", line):
            continue
        if line == province or line in known:
            continue
        if "سنة" in line or "عام" in line or "عمر" in line or "طول" in line or "وزن" in line:
            continue
        if re.search(r"(?:الهاتف|الواتساب|واتساب|telegram|تلغرام|تيليجرام)", line, re.I):
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
    req_markers = ("المطلوب", "مواصفات الشريك", "بدها شاب", "بدي بنت", "بده بنت", "بده شابة")
    for line in lines:
        if any(marker in line for marker in desc_markers):
            description = line.split(":", 1)[1].strip() if ":" in line else line
        if any(marker in line for marker in req_markers):
            requirement = line.split(":", 1)[1].strip() if ":" in line else line

    return ProfileExtraction(
        gender=gender, name=name, age=age, province=province, city=city,
        marital_status=marital_status, occupation=occupation, height=height, weight=weight,
        description=description, partner_requirements=requirement, phone=phone,
        telegram_username=telegram_username, whatsapp=whatsapp, photo_file_id=photo_file_id,
    )
