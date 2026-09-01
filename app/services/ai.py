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
    children_count: int | None = Field(default=None, description="Number of children when explicitly stated")
    occupation: str | None = None
    education: str | None = None
    nationality: str | None = None
    religion: str | None = None
    height: float | None = None
    weight: float | None = None
    appearance: str | None = None
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
    education: str | None = None
    children_min: int | None = None
    children_max: int | None = None


PROFILE_SCHEMA_INSTRUCTIONS = """
أنت مسؤول عن تحويل إعلان زواج سوري خام إلى بيانات منظمة دقيقة وقابلة للحفظ والنشر.

استخرج المعلومات الموجودة فعلياً في النص فقط، ولا تخترع أي قيمة. إذا كانت غير موجودة أو غير مؤكدة = null.
افهم العامية السورية والأخطاء الإملائية البسيطة مع المحافظة على معنى النص.

الحقول:
- gender: جنس صاحب الإعلان فقط. لا تستنتجه من مواصفات الشريك.
- name: اسم الشخص نفسه فقط، مثل «اسمي آية» -> «آية».
- age: عمر صاحب الإعلان.
- province: المحافظة السورية. «سوريا» وحدها ليست محافظة.
- city: المدينة إذا ذُكرت بوضوح. إذا كان النص «دمشق» فقط، فالمحافظة دمشق والمدينة دمشق لأن اسم المدينة مطابق للمحافظة. إذا كان «ريف حماة» فالمحافظة حماة والمدينة/الموقع «ريف حماة».
- marital_status: عزباء، عازبة، عزب، متزوجة، متزوج، مطلقة، مطلق، أرملة، أرمل، مع تطبيع الصياغة.
- children_count: عدد الأولاد فقط إذا ذكر العدد أو نفي وجود الأولاد صراحةً. «ماعندي ولاد» = 0. «عندي ولدين» = 2. لا تستنتج العدد.
- occupation: العمل/المهنة أو الحالة الدراسية العملية مثل «ربة منزل»، «طالبة طب».
- education: المستوى التعليمي أو الدراسة إذا ذُكر، مثل «شهادة بكالوريا» أو «دراسة الطب».
- nationality: الجنسية إذا ذُكرت.
- religion: الديانة إذا ذُكرت.
- height/weight: أرقام الطول والوزن فقط.
- appearance: الشكل الخارجي والصفات المرتبطة بالمظهر مثل «سمراء جذابة، محجبة».
- description: المواصفات الشخصية والهوايات والطباع فقط، مثل «تحب الغناء وصوتها حلو».
- partner_requirements: كل مواصفات الشريك المطلوب، مثل العمر، الطول، التدخين، الدين، الجدية، الصفات، وغيرها، بعد ترتيبها دون اختراع.
- phone/telegram_username/whatsapp: بيانات سرية فقط.

أمثلة:
«اسمي منا من حلب بدرس طب بغني وصوتي حلو عمري 30 سنة مطلقة ماعندي ولاد بدي شب يكون طويل وما بدخن ورقمي 093..."
=> name=منا, province=حلب, city=حلب, age=30, marital_status=مطلقة, children_count=0, occupation=طالبة طب, description=تهتم بالغناء وصوتها جميل, partner_requirements=شاب طويل وغير مدخن, phone=...

مهم: لا تضع رقم الهاتف داخل description أو partner_requirements.
"""

SEARCH_FILTER_INSTRUCTIONS = """
أنت محلل طلبات بحث لبوت «لقاء ونصيب» السوري.
حوّل الكلام الطبيعي والعامي إلى فلاتر بحث حقيقية فقط.

قواعد:
- لا تخترع أي فلتر غير موجود بالنص.
- «بنت، صبية، فتاة، عروس» = female.
- «شب، شاب، رجل، عريس» = male.
- «شام، الشام» في السكن = دمشق.
- «دمشق» أو «بنت دمشق» = province=دمشق، وليس city=دمشق، إلا إذا ذُكرت المدينة صراحة أو «دمشق - جرمانا».
- افهم «عمرا، عمرها، عمره، بالعمر، بعمر، سنها، سنه».
- افهم «بين 20 و39»، «بين ال20 وال39»، «من 20 لـ39»، «من ال20 لل39»، «20-39»، «20 إلى 39».
- «حوالي 30» أو «قرابة 30» = 30 بالضبط، بدون اختراع نطاق.
- الحالة الاجتماعية تطبّع إلى المعاني الصحيحة.
- education/occupation تستخرج فقط عند ذكرها بوضوح.
- children_min/max تستخرج إذا ذكر المستخدم عدد الأولاد المطلوب مثل «ما عندها ولاد» أو «بدي بدون أولاد» أو «عندها ولد واحد».
- أعد JSON مطابقاً للـSchema فقط.
"""


def _remove_private_contact_values(value: str | None) -> str | None:
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
    generic_fragments = ("بنت من", "شاب من", "عروس من", "عريس من", "فتاة من", "رجل من", "امرأة من")
    if any(fragment in lowered for fragment in generic_fragments):
        return None
    if name in {"بنت", "شاب", "عروس", "عريس", "فتاة", "رجل", "امرأة"}:
        return None
    return name


def _normalize_marital_status(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    mapping = {
        "عزبا": "عزباء", "عزبى": "عزباء", "عزبة": "عزباء", "عزباء": "عزباء", "عازبة": "عزباء",
        "اعزب": "عازب", "أعزب": "عازب", "عازب": "عازب",
        "مطلقة": "مطلقة", "مطلقه": "مطلقة", "مطلق": "مطلق",
        "أرملة": "أرملة", "ارملة": "أرملة", "أرمل": "أرمل",
        "متزوجة": "متزوجة", "متزوجه": "متزوجة", "متزوج": "متزوج",
    }
    return mapping.get(v, value.strip())


def merge_private_contacts(ai_extraction: ProfileExtraction, deterministic_extraction: ProfileExtraction) -> ProfileExtraction:
    updates: dict[str, Any] = {
        "phone": deterministic_extraction.phone,
        "telegram_username": deterministic_extraction.telegram_username,
        "whatsapp": deterministic_extraction.whatsapp,
    }
    public_fields = (
        "gender", "name", "age", "province", "city", "marital_status", "children_count",
        "occupation", "education", "nationality", "religion", "height", "weight",
        "appearance", "description", "partner_requirements",
    )
    for field_name in public_fields:
        ai_value = getattr(ai_extraction, field_name)
        deterministic_value = getattr(deterministic_extraction, field_name)
        if ai_value is None and deterministic_value is not None:
            updates[field_name] = deterministic_value
    return ai_extraction.model_copy(update=updates)


def normalize_profile_extraction(extraction: ProfileExtraction) -> ProfileExtraction:
    from app.services.profiles import normalize_digits, normalize_gender

    province = extraction.province.strip() if extraction.province else None
    city = extraction.city.strip() if extraction.city else None
    if city is None and province and province in {
        "دمشق", "حلب", "حمص", "حماة", "اللاذقية", "طرطوس", "إدلب", "الرقة", "دير الزور", "الحسكة", "درعا", "السويداء", "القنيطرة",
    }:
        city = province

    children_count = extraction.children_count
    if children_count is not None and children_count < 0:
        children_count = None

    updates = {
        "gender": normalize_gender(extraction.gender) if extraction.gender else None,
        "name": _normalize_name(extraction.name),
        "province": province,
        "city": city,
        "marital_status": _normalize_marital_status(extraction.marital_status),
        "children_count": children_count,
        "occupation": extraction.occupation.strip() if extraction.occupation else None,
        "education": extraction.education.strip() if extraction.education else None,
        "nationality": extraction.nationality.strip() if extraction.nationality else None,
        "religion": extraction.religion.strip() if extraction.religion else None,
        "appearance": _remove_private_contact_values(extraction.appearance),
        "description": _remove_private_contact_values(extraction.description),
        "partner_requirements": _remove_private_contact_values(extraction.partner_requirements),
        "phone": normalize_digits(extraction.phone.strip()) if extraction.phone else None,
        "telegram_username": extraction.telegram_username.strip().lstrip("@") if extraction.telegram_username else None,
        "whatsapp": normalize_digits(extraction.whatsapp.strip()) if extraction.whatsapp else None,
    }
    return extraction.model_copy(update=updates)


class AIService:
    def __init__(self, api_key: str | None = None, model: str = "gemini-3.5-flash-lite") -> None:
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
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        return ProfileExtraction.model_validate_json(response.text)

    async def extract_profile(self, raw_text: str) -> ProfileExtraction:
        return await asyncio.to_thread(self.extract_profile_sync, raw_text)

    @staticmethod
    async def resolve_profile_extraction(ai_service: "AIService", raw_text: str, deterministic_extraction: ProfileExtraction) -> ProfileExtraction:
        if not ai_service.is_configured:
            raise AIExtractionError("Gemini is not configured")
        try:
            ai_extraction = await ai_service.extract_profile(raw_text)
        except Exception as exc:
            raise AIExtractionError(f"Gemini extraction failed: {type(exc).__name__}") from exc
        return normalize_profile_extraction(merge_private_contacts(ai_extraction, deterministic_extraction))

    def parse_search_filters_sync(self, raw_text: str) -> SearchFilterExtraction:
        client = self._get_client()
        from google.genai import types
        response = client.models.generate_content(
            model=self.model,
            contents=f"{SEARCH_FILTER_INSTRUCTIONS}\n\nطلب المستخدم:\n{raw_text}",
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=SearchFilterExtraction,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        return SearchFilterExtraction.model_validate_json(response.text)

    async def parse_search_filters(self, raw_text: str) -> SearchFilterExtraction:
        return await asyncio.to_thread(self.parse_search_filters_sync, raw_text)


def basic_profile_extraction(raw_text: str, photo_file_id: str | None = None) -> ProfileExtraction:
    """Conservative local extraction for explicit facts and privacy validation."""
    from app.services.profiles import normalize_digits

    normalized = normalize_digits(raw_text.replace("،", " ")).strip()
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    joined = " ".join(lines)

    gender = None
    if any(token in joined for token in ("أنثى", "انثى", "بنت", "عروس", "صبية", "فتاة")):
        gender = "female"
    elif any(token in joined for token in ("ذكر", "شاب", "عريس", "رجل")):
        gender = "male"

    age = None
    for pattern in (
        r"(?:عمري|عمري أنا|عمرها|عمره|عمرا|العمر|عمر|بعمر|سنها|سنه)\s*[:=-]?\s*(\d{1,3})",
        r"(?<!\d)(\d{2,3})(?:\s*)(?:سنة|سنين|عام)",
    ):
        match = re.search(pattern, normalized)
        if match and 18 <= int(match.group(1)) <= 100:
            age = int(match.group(1))
            break

    province_names = (
        "ريف دمشق", "دمشق", "حلب", "حمص", "حماة", "اللاذقية", "طرطوس", "إدلب", "الرقة", "دير الزور", "الحسكة", "درعا", "السويداء", "القنيطرة",
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
    for value in ("عزباء", "عازبة", "عزب", "عازب", "متزوجة", "متزوج", "مطلقة", "مطلقه", "مطلق", "أرملة", "ارملة", "أرمل", "ارمل"):
        if value in joined:
            marital_status = value
            break

    children_count = None
    if re.search(r"(?:ما?عندي|ليس عندي|بدون)\s+(?:اولاد|أولاد|ولاد|أطفال|اطفال)", normalized):
        children_count = 0
    else:
        child_match = re.search(r"(?:عندي|لدي|عندو|عندها|عنده)\s+(?:عدد\s+)?(\d{1,2})\s+(?:اولاد|أولاد|ولاد|أطفال|اطفال|ابناء|أبناء)", normalized)
        if child_match:
            children_count = int(child_match.group(1))

    height = None
    height_match = re.search(r"(?:طول|الطول)\s*[:=-]?\s*(\d{2,3})(?:\s*سم)?", normalized)
    if height_match:
        height = float(height_match.group(1))

    weight = None
    weight_match = re.search(r"(?:وزن|الوزن)\s*[:=-]?\s*(\d{2,3})(?:\s*كغ|\s*كجم)?", normalized)
    if weight_match:
        weight = float(weight_match.group(1))

    occupation = None
    for marker in ("ربة منزل", "طالب طب", "طالبة طب", "مدرسة", "مدرس", "مهندس", "طبيب", "ممرض", "موظف", "موظفة", "محامي", "محامية", "تاجر", "متعهد"):
        if marker in joined:
            occupation = marker
            break

    education = None
    education_match = re.search(r"(?:المستوى التعليمي|التعليم|الدراسة|دارسة|بدرس)\s*[:=-]?\s*([^،,\n]+)", normalized)
    if education_match:
        education = education_match.group(1).strip()

    nationality = None
    nationality_match = re.search(r"(?:الجنسية)\s*[:=-]?\s*([^،,\n]+)", normalized)
    if nationality_match:
        nationality = nationality_match.group(1).strip()

    religion = None
    religion_match = re.search(r"(?:الديانة|الدين)\s*[:=-]?\s*([^،,\n]+)", normalized)
    if religion_match:
        religion = religion_match.group(1).strip()

    name = None
    explicit_name_match = re.search(r"(?:اسمي|الاسم)\s*[:=-]?\s*([^\n،,]+)", normalized)
    if explicit_name_match:
        candidate = explicit_name_match.group(1).strip()
        candidate = re.split(r"\s+(?:عمري|من|ساكن|ساكنة|بدرس|درست|مطلقة|عزباء|عازبة|متزوجة|متزوج)\b", candidate, maxsplit=1)[0].strip()
        if candidate:
            name = candidate

    known = set(province_names) | {
        "أنثى", "انثى", "بنت", "عروس", "صبية", "فتاة", "ذكر", "شاب", "عريس", "رجل",
        "عزباء", "عازبة", "عزب", "عازب", "متزوجة", "متزوج", "مطلقة", "مطلقه", "مطلق", "أرملة", "ارملة", "أرمل", "ارمل",
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
    if city is None and province and province in {"دمشق", "حلب", "حمص", "حماة", "اللاذقية", "طرطوس", "إدلب", "الرقة", "دير الزور", "الحسكة", "درعا", "السويداء", "القنيطرة"}:
        city = province

    appearance = None
    appearance_match = re.search(r"(?:الشكل|المظهر|المظهر الخارجي)\s*[:=-]?\s*([^\n]+)", normalized)
    if appearance_match:
        appearance = appearance_match.group(1).strip()

    description = None
    requirement = None
    desc_markers = ("المواصفات الشخصية", "المواصفات", "صفاتها", "صفاته", "الوصف")
    req_markers = ("المطلوب", "مواصفات الشريك", "بدها شاب", "بدي شاب", "بدي شب", "بده شاب", "بدي بنت", "بده بنت", "بده شابة", "بدي عريس", "بدي عروس")
    for line in lines:
        if any(marker in line for marker in desc_markers):
            description = line.split(":", 1)[1].strip() if ":" in line else line
        if any(marker in line for marker in req_markers):
            requirement = line.split(":", 1)[1].strip() if ":" in line else line
    if requirement is None:
        requirement_match = re.search(r"((?:بدي|بدها|بده)\s+(?:شب|شاب|بنت|شابة|عروس|عريس)\b.+)", normalized, re.I)
        if requirement_match:
            requirement = requirement_match.group(1).strip()

    return ProfileExtraction(
        gender=gender,
        name=name,
        age=age,
        province=province,
        city=city,
        marital_status=marital_status,
        children_count=children_count,
        occupation=occupation,
        education=education,
        nationality=nationality,
        religion=religion,
        height=height,
        weight=weight,
        appearance=_remove_private_contact_values(appearance),
        description=_remove_private_contact_values(description),
        partner_requirements=_remove_private_contact_values(requirement),
        phone=phone,
        telegram_username=telegram_username,
        whatsapp=whatsapp,
        photo_file_id=photo_file_id,
    )
