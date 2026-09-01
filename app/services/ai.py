"""Gemini integration for structured marriage-profile extraction and natural-language search."""

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
    residence: str | None = None
    marital_status: str | None = None
    children_count: int | None = Field(default=None, description="Explicit child count, including 0")
    occupation: str | None = None
    education: str | None = None
    height: float | None = None
    weight: float | None = None
    appearance: str | None = None
    partner_requirements: str | None = None
    phone: str | None = None
    telegram_username: str | None = None
    whatsapp: str | None = None
    photo_file_id: str | None = None


class SearchFilterExtraction(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gender: str | None = Field(default=None, description="male or female")
    residence: str | None = None
    age_min: int | None = None
    age_max: int | None = None
    marital_status: str | None = None
    occupation: str | None = None
    education: str | None = None
    children_min: int | None = None
    children_max: int | None = None


PROFILE_SCHEMA_INSTRUCTIONS = """
حوّل النص الخام لإعلان زواج إلى JSON منظم لنظام «لقاء ونصيب».
النص قد يكون عامياً سورياً، مختصراً، غير مرتب، أو يحوي أخطاء إملائية.
افهم المعنى من السياق، ولا تعتمد على مطابقة كلمات حرفية فقط.

ممنوع اختراع أي معلومة. إذا لم توجد المعلومة بوضوح = null.

الحقول:
- gender: جنس صاحب الإعلان فقط.
- name: اسم الشخص فقط، بدون «اسمي» أو أي كلام حوله.
- age: عمر صاحب الإعلان.
- residence: مكان السكن في حقل واحد فقط. افهم «من دمشق»، «ساكن بحمص»، «ساكنة بريف حماة»، «مقيم في جرمانا»، «عايش بحلب»، «من ريف حلب» وغيرها حسب السياق. لا تفصل محافظة ومدينة.
- marital_status: الحالة الاجتماعية، مع تصحيح الأخطاء البسيطة مثل مطلقه/متزوجه/ارمله.
- children_count: العدد الصريح للأولاد. «ماعندي ولاد» = 0، «عندي ولدين» = 2. لا تخترع العدد.
- occupation: العمل أو الوضع المهني/الدراسي الحالي مثل «ربة منزل» أو «طالبة طب».
- education: الشهادة أو المستوى التعليمي إذا ذُكر بوضوح مثل «بكالوريا».
- height / weight: الأرقام فقط.
- appearance: الشكل الخارجي فقط مثل «سمراء جذابة ومحجبة».
- partner_requirements: كل شروط الشريك المطلوب، ويمكن أن تتضمن العمر والطول والسكن والدين والجنسية والتدخين والصفات وغيرها. رتّبها بوضوح ولا تخترع.
- phone / telegram_username / whatsapp: بيانات التواصل السرية فقط.

لا توجد حقول للجنسية أو الديانة أو «المواصفات الشخصية». إذا ذُكرت جنسية أو ديانة تخص الشريك المطلوب، احتفظ بها داخل partner_requirements. صفات صاحب الإعلان الشخصية غير المطلوبة في الـSchema لا تحفظ كحقل مستقل.
"""

SEARCH_FILTER_INSTRUCTIONS = """
أنت محلل طلب بحث طبيعي لبوت زواج سوري. افهم كلام المستخدم من السياق، بما فيه العامية والأخطاء، وحوّله إلى JSON مطابق للـSchema فقط.

- لا تخترع أي فلتر غير موجود أو مفهوم بوضوح.
- «بنت/صبية/فتاة/عروس» = female، و«شب/شاب/رجل/عريس» = male.
- residence هو الموقع الوحيد. افهم «من»، «ساكن»، «ساكنة»، «مقيم»، «مقيمة»، «عايش»، «عايشة»، «بـ»، «بمنطقة» وغيرها دون الحاجة لقائمة كلمات ثابتة.
- افهم «شام/الشام» كدمشق عند استخدامها للسكن.
- افهم جميع الصيغ الشائعة للعمر: عمره، عمرها، عمرا، سنه، سنها، بعمر، بين 20 و39، بين ال20 وال39، من 20 لـ39، من ال20 لل39، 20-39، 20 إلى 39.
- «حوالي 30» و«قرابة 30» = 30 فقط.
- الحالة الاجتماعية والتعليم والعمل وعدد الأولاد تُفهم حسب المعنى.
- «بدون ولاد» أو «ما عندها ولاد» أو «ما عنده أولاد» = children_min=0 وchildren_max=0.
- أعد JSON فقط.
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
    if name in {"بنت", "شاب", "عروس", "عريس", "فتاة", "رجل", "امرأة"}:
        return None
    if any(fragment in lowered for fragment in ("بنت من", "شاب من", "عروس من", "عريس من", "فتاة من", "رجل من", "امرأة من")):
        return None
    return name


def _normalize_marital_status(value: str | None) -> str | None:
    if not value:
        return None
    mapping = {
        "عزبا": "عزباء", "عزبى": "عزباء", "عزبة": "عزباء", "عازبة": "عزباء", "عزباء": "عزباء",
        "اعزب": "عازب", "أعزب": "عازب", "عازب": "عازب",
        "مطلقة": "مطلقة", "مطلقه": "مطلقة", "مطلق": "مطلق",
        "أرملة": "أرملة", "ارملة": "أرملة", "أرمل": "أرمل", "ارمل": "أرمل",
        "متزوجة": "متزوجة", "متزوجه": "متزوجة", "متزوج": "متزوج",
        "منفصلة": "منفصلة", "منفصله": "منفصلة", "منفصل": "منفصل",
    }
    return mapping.get(value.strip().lower(), value.strip())


def _normalize_residence(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value.strip())
    text = re.sub(r"^(?:سوريا|سورية)\s*[-–:]\s*", "", text, flags=re.I)
    return text or None


def merge_private_contacts(ai_extraction: ProfileExtraction, deterministic_extraction: ProfileExtraction) -> ProfileExtraction:
    updates: dict[str, Any] = {
        "phone": deterministic_extraction.phone,
        "telegram_username": deterministic_extraction.telegram_username,
        "whatsapp": deterministic_extraction.whatsapp,
    }
    for field_name in ("gender", "name", "age", "residence", "marital_status", "children_count", "occupation", "education", "height", "weight", "appearance", "partner_requirements"):
        ai_value = getattr(ai_extraction, field_name)
        deterministic_value = getattr(deterministic_extraction, field_name)
        if ai_value is None and deterministic_value is not None:
            updates[field_name] = deterministic_value
    return ai_extraction.model_copy(update=updates)


def normalize_profile_extraction(extraction: ProfileExtraction) -> ProfileExtraction:
    from app.services.profiles import normalize_digits, normalize_gender
    children_count = extraction.children_count if extraction.children_count is None or extraction.children_count >= 0 else None
    updates = {
        "gender": normalize_gender(extraction.gender) if extraction.gender else None,
        "name": _normalize_name(extraction.name),
        "residence": _normalize_residence(extraction.residence),
        "marital_status": _normalize_marital_status(extraction.marital_status),
        "children_count": children_count,
        "occupation": extraction.occupation.strip() if extraction.occupation else None,
        "education": extraction.education.strip() if extraction.education else None,
        "height": extraction.height,
        "weight": extraction.weight,
        "appearance": _remove_private_contact_values(extraction.appearance),
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
            from google import genai
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def extract_profile_sync(self, raw_text: str) -> ProfileExtraction:
        from google.genai import types
        response = self._get_client().models.generate_content(
            model=self.model,
            contents=f"{PROFILE_SCHEMA_INSTRUCTIONS}\n\nالنص الخام:\n{raw_text}",
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=ProfileExtraction,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini returned an empty response")
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
        from google.genai import types
        response = self._get_client().models.generate_content(
            model=self.model,
            contents=f"{SEARCH_FILTER_INSTRUCTIONS}\n\nطلب البحث:\n{raw_text}",
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=SearchFilterExtraction,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini returned an empty response")
        return SearchFilterExtraction.model_validate_json(response.text)

    async def parse_search_filters(self, raw_text: str) -> SearchFilterExtraction:
        return await asyncio.to_thread(self.parse_search_filters_sync, raw_text)


def basic_profile_extraction(raw_text: str, photo_file_id: str | None = None) -> ProfileExtraction:
    """Conservative local supplement used only for explicit facts and privacy protection."""
    from app.services.profiles import normalize_digits

    normalized = normalize_digits(raw_text.replace("،", " ")).strip()
    lower = normalized.lower()
    gender = "female" if re.search(r"بنت|صبية|فتاة|عروس|أنثى|انثى", lower) else "male" if re.search(r"شب|شاب|رجل|عريس|ذكر", lower) else None

    age = None
    for pattern in (r"(?:عمري|عمرها|عمره|عمرا|العمر|عمر|بعمر|سنها|سنه)\s*[:=-]?\s*(\d{1,3})", r"(?<!\d)(\d{2,3})\s*(?:سنة|سنين|عام)\b"):
        match = re.search(pattern, normalized, re.I)
        if match and 18 <= int(match.group(1)) <= 100:
            age = int(match.group(1))
            break

    residence = None
    patterns = (
        r"(?:من|ساكن(?:ة)?|مقيم(?:ة)?|عايش(?:ة)?)\s+(?:في\s+|ب(?:ـ)?\s*)?([^,\n]+?)(?=\s+(?:عمري|عمرها|عمره|العمر|سنة|سن|مطلق|متزوج|عزب|أرمل|أرملة|بدها|بدي|بده|رقمي|رقم)\b|$)",
        r"(?:بنت|شاب|صبية|عروس|عريس)\s+(?:من\s+)?(ريف\s+(?:دمشق|حلب|حمص|حماة|إدلب)|دمشق|حلب|حمص|حماة|اللاذقية|طرطوس|إدلب|الرقة|دير الزور|الحسكة|درعا|السويداء|القنيطرة|جرمانا)",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, re.I)
        if match:
            candidate = match.group(1).strip(" -–:،")
            if 1 <= len(candidate) <= 100:
                residence = _normalize_residence(candidate)
                break

    children_count = 0 if re.search(r"(?:ما\s*عندي|ماعندي|ما\s*عندها|ماعندها|ما\s*عنده|ماعنده|بدون)\s+(?:ولاد|أولاد|اولاد|أطفال|اطفال)", lower) else None
    if children_count is None:
        for phrase, count in {"ولد واحد": 1, "طفل واحد": 1, "ولدين": 2, "طفلين": 2, "ثلاثة أولاد": 3, "ثلاث اولاد": 3}.items():
            if phrase in lower:
                children_count = count
                break
        if children_count is None:
            match = re.search(r"(?:عندي|عندها|عنده|لديها|لديه)\s*(\d{1,2})\s*(?:ولاد|أولاد|اولاد|أطفال|اطفال)", lower)
            if match:
                children_count = int(match.group(1))

    marital_status = None
    for value in ("عزباء", "عازبة", "عزبا", "عزب", "أعزب", "اعزب", "عازب", "مطلقة", "مطلقه", "مطلق", "أرملة", "ارملة", "أرمل", "ارمل", "متزوجة", "متزوجه", "متزوج", "منفصلة", "منفصله", "منفصل"):
        if value in lower:
            marital_status = _normalize_marital_status(value)
            break

    occupation = None
    for marker in ("ربة منزل", "طالبة طب", "طالب طب", "طالبة", "طالب", "مدرسة", "مدرس", "مهندس", "طبيب", "ممرض", "موظف", "موظفة", "محامي", "محامية", "تاجر", "متعهد"):
        if marker in normalized:
            occupation = marker
            break

    education = None
    for marker in ("بكالوريا", "بكالوريوس", "ليسانس", "ماجستير", "دكتوراه", "جامعي", "جامعة", "ثانوي"):
        if marker in normalized:
            education = marker
            break

    height = None
    match = re.search(r"(?:طول|الطول)\s*[:=-]?\s*(\d{2,3})(?:\s*سم)?", normalized)
    if match:
        height = float(match.group(1))
    weight = None
    match = re.search(r"(?:وزن|الوزن)\s*[:=-]?\s*(\d{2,3})(?:\s*كغ|\s*كجم)?", normalized)
    if match:
        weight = float(match.group(1))

    name = None
    match = re.search(r"(?:اسمي|الاسم)\s*[:=-]?\s*([^\n،,]+)", normalized)
    if match:
        candidate = re.split(r"\s+(?:عمري|من|ساكن|ساكنة|مقيم|مقيمة)\b", match.group(1).strip(), maxsplit=1)[0].strip()
        name = _normalize_name(candidate)

    phone_match = re.search(r"(?:\+?963\s?)?(?:0?9|09)[0-9xX][0-9xX -]{5,}", normalized)
    phone = phone_match.group(0).strip() if phone_match else None
    tg_match = re.search(r"(?:telegram|تلغرام|تيليجرام)\s*[:=@]?\s*@?([A-Za-z0-9_]{3,})", normalized, re.I)
    telegram_username = tg_match.group(1) if tg_match else None
    wa_match = re.search(r"(?:whatsapp|واتساب|واتس)\s*[:=@]?\s*([+0-9][+0-9 xX-]{6,})", normalized, re.I)
    whatsapp = wa_match.group(1).strip() if wa_match else None

    appearance = None
    if any(token in lower for token in ("سمراء", "بيضاء", "حنطية", "محجبة", "منقبة", "شقراء", "جذابة", "جميلة", "وسيم")):
        tokens = [token for token in ("سمراء", "بيضاء", "حنطية", "محجبة", "منقبة", "شقراء", "جذابة", "جميلة", "وسيم") if token in lower]
        appearance = "، ".join(dict.fromkeys(tokens))

    req_match = re.search(r"((?:بدي|بدها|بده)\s+(?:شب|شاب|بنت|شابة|عروس|عريس)\b.+)", normalized, re.I)
    partner_requirements = _remove_private_contact_values(req_match.group(1)) if req_match else None

    return ProfileExtraction(
        gender=gender,
        name=name,
        age=age,
        residence=residence,
        marital_status=marital_status,
        children_count=children_count,
        occupation=occupation,
        education=education,
        height=height,
        weight=weight,
        appearance=appearance,
        partner_requirements=partner_requirements,
        phone=phone,
        telegram_username=telegram_username,
        whatsapp=whatsapp,
        photo_file_id=photo_file_id,
    )
