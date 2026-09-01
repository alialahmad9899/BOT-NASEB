"""Search parsing and filter normalization."""

from __future__ import annotations

import re
from dataclasses import replace

from app.database.repositories import ProfileFilters
from app.services.ai import SearchFilterExtraction
from app.services.profiles import normalize_digits

PROVINCES = [
    "ريف دمشق", "دمشق", "حلب", "حمص", "حماة", "اللاذقية", "طرطوس", "إدلب",
    "الرقة", "دير الزور", "الحسكة", "درعا", "السويداء", "القنيطرة",
]

PROVINCE_ALIASES = {
    "شام": "دمشق", "الشام": "دمشق", "دمشق": "دمشق", "حلب": "حلب", "حمص": "حمص",
    "حماة": "حماة", "اللاذقية": "اللاذقية", "طرطوس": "طرطوس", "ادلب": "إدلب", "إدلب": "إدلب",
    "الرقة": "الرقة", "دير الزور": "دير الزور", "الحسكة": "الحسكة", "درعا": "درعا",
    "السويداء": "السويداء", "القنيطرة": "القنيطرة", "ريف دمشق": "ريف دمشق",
}

MARITAL_ALIASES = {
    "عزباء": "عزباء", "عازبة": "عزباء", "عزبا": "عزباء", "عزبة": "عزباء", "عزبى": "عزباء",
    "عزب": "عزب", "أعزب": "أعزب", "اعزب": "أعزب", "عازب": "أعزب",
    "مطلقة": "مطلقة", "مطلقه": "مطلقة", "مطلق": "مطلق",
    "أرملة": "أرملة", "ارملة": "أرملة", "أرمل": "أرمل", "ارمل": "أرمل",
    "متزوجة": "متزوجة", "متزوجه": "متزوجة", "متزوج": "متزوج",
}


def _canonical_province(value: str | None) -> str | None:
    if not value:
        return None
    return PROVINCE_ALIASES.get(normalize_digits(value).strip().lower())


def _canonical_marital(value: str | None) -> str | None:
    if not value:
        return None
    return MARITAL_ALIASES.get(normalize_digits(value).strip().lower(), value.strip())


def _province_mentioned(text: str, province: str) -> bool:
    return any(alias in text for alias, canonical in PROVINCE_ALIASES.items() if canonical == province)


def _explicit_city_reference(text: str) -> bool:
    return bool(
        re.search(r"(?:مدينة|المدينة|ساكن(?:ة)?|سكن(?:ي)?)\s+", text)
        or re.search(
            r"(?:ريف دمشق|دمشق|حلب|حمص|حماة|اللاذقية|طرطوس|إدلب|الرقة|دير الزور|الحسكة|درعا|السويداء|القنيطرة)\s*[-–/]\s*",
            text,
        )
    )


def _extract_age_range(text: str) -> tuple[int, int] | None:
    match = re.search(
        r"(?:من|بين)\s*(?:ال)?\s*(\d{1,3})\s*(?:الى|إلى|و|ل(?:ـ)?|حتى|-|–|لـ)\s*(?:ال)?\s*(\d{1,3})",
        text,
    )
    if match:
        values = tuple(sorted((int(match.group(1)), int(match.group(2)))))
        if 18 <= values[0] <= 100 and 18 <= values[1] <= 100:
            return values
    match = re.search(r"(?:ال)?\s*(\d{2,3})\s*[-–]\s*(?:ال)?\s*(\d{2,3})", text)
    if match:
        values = tuple(sorted((int(match.group(1)), int(match.group(2)))))
        if 18 <= values[0] <= 100 and 18 <= values[1] <= 100:
            return values
    return None


def _extract_single_age(text: str) -> int | None:
    match = re.search(r"(?:عمر|العمر|عمرا|عمرها|عمره|بعمر|سنها|سنه)\s*[:=-]?\s*(?:ال)?\s*(\d{1,3})", text)
    if match:
        value = int(match.group(1))
        if 18 <= value <= 100:
            return value
    if text.isdigit() and 18 <= int(text) <= 100:
        return int(text)
    return None


def _extract_children_filter(text: str) -> tuple[int | None, int | None]:
    normalized = text.lower()
    if re.search(r"(?:بدون|ما عندها|ماعندها|ما عنده|ماعنده|ما فيها|مابيها)\s+(?:ولاد|اولاد|أولاد|أطفال|اطفال)", normalized):
        return 0, 0
    match = re.search(r"(?:ولد واحد|طفل واحد)", normalized)
    if match:
        return 1, 1
    match = re.search(r"(?:ولدين|طفلين)", normalized)
    if match:
        return 2, 2
    match = re.search(r"(?:عندها|عنده|عندو|عندي|لديها|لديه)\s*(\d{1,2})\s*(?:ولاد|اولاد|أولاد|أطفال|اطفال)", normalized)
    if match:
        count = int(match.group(1))
        return count, count
    return None, None


def _extract_education(text: str) -> str | None:
    for marker in ("بكالوريا", "بكالوريوس", "ليسانس", "جامعة", "جامعي", "ثانوي", "إعدادي", "اعدادي", "دكتوراه", "ماجستير"):
        if marker in text:
            return marker
    return None


def parse_search_text(text: str) -> ProfileFilters:
    normalized = normalize_digits(text).strip().lower()
    gender = None
    if re.search(r"(?:بنت|صبية|عروس|انثى|أنثى|فتاة)", normalized):
        gender = "female"
    elif re.search(r"(?:شاب|شب|عريس|ذكر|رجل)", normalized):
        gender = "male"

    province = next((p for p in PROVINCES if _province_mentioned(normalized, p)), None)
    if not province:
        for alias, canonical in PROVINCE_ALIASES.items():
            if alias in normalized:
                province = canonical
                break

    marital = None
    for raw, canonical in MARITAL_ALIASES.items():
        if raw in normalized:
            marital = canonical
            break

    age_min = age_max = None
    age_range = _extract_age_range(normalized)
    if age_range:
        age_min, age_max = age_range
    else:
        single_age = _extract_single_age(normalized)
        if single_age is not None:
            age_min = age_max = single_age

    city = None
    hyphen_city = re.search(
        r"(?:ريف دمشق|دمشق|حلب|حمص|حماة|اللاذقية|طرطوس|إدلب|الرقة|دير الزور|الحسكة|درعا|السويداء|القنيطرة)\s*[-–/]\s*([\u0600-\u06ff]{3,30})",
        normalized,
    )
    if hyphen_city:
        city = hyphen_city.group(1).strip()
    city_match = re.search(r"(?:مدينة|ساكن(?:ة)?|سكن(?:ي)?)\s+([\u0600-\u06ff]{3,30})", normalized)
    if city_match:
        city = city_match.group(1).strip(" ،,")

    if city and province and city == province and not _explicit_city_reference(normalized):
        city = None

    children_min, children_max = _extract_children_filter(normalized)
    education = _extract_education(normalized)
    occupation = None
    for marker in ("ربة منزل", "طالبة", "طالب", "مدرسة", "مدرس", "مهندس", "طبيب", "ممرض", "موظف", "موظفة", "محامي", "محامية", "تاجر", "متعهد"):
        if marker in normalized:
            occupation = marker
            break

    return ProfileFilters(
        gender=gender,
        province=province,
        city=city,
        age_min=age_min,
        age_max=age_max,
        marital_status=marital,
        occupation=occupation,
        education=education,
        children_min=children_min,
        children_max=children_max,
    )


def _mentions_target_age(text: str, age: int) -> bool:
    normalized = normalize_digits(text).lower()
    value = str(age)
    if re.search(rf"(?:^|\s)عمري\s*[:=]?\s*{re.escape(value)}(?:\s|$)", normalized):
        return False
    if re.search(rf"(?:عمر|العمر|عمرا|عمرها|عمره|بعمر|سنها|سنه)\s*[:=]?\s*(?:ال)?\s*{re.escape(value)}(?:\s|$)", normalized):
        return True
    for match in re.finditer(r"(?:بين|من)\s*(?:ال)?\s*(\d{1,3})\s*(?:و|الى|إلى|ل(?:ـ)?|حتى|[-–]|لـ)\s*(?:ال)?\s*(\d{1,3})", normalized):
        if value in {match.group(1), match.group(2)}:
            return True
    return False


def filters_from_ai(extraction: SearchFilterExtraction, raw_text: str | None = None) -> ProfileFilters:
    source = normalize_digits(raw_text or "").lower()

    gender = extraction.gender if extraction.gender in {"male", "female"} else None
    if source and gender == "female" and not re.search(r"بنت|صبية|عروس|انثى|أنثى|فتاة", source):
        gender = None
    if source and gender == "male" and not re.search(r"شاب|شب|عريس|ذكر|رجل", source):
        gender = None

    province = _canonical_province(extraction.province)
    if source and province and not _province_mentioned(source, province):
        province = None
    city = extraction.city.strip() if extraction.city else None
    if source and city and city.lower() not in source:
        city = None
    if city and province and city.lower() == province.lower() and not _explicit_city_reference(source):
        city = None

    age_min = extraction.age_min if extraction.age_min and 18 <= extraction.age_min <= 100 else None
    age_max = extraction.age_max if extraction.age_max and 18 <= extraction.age_max <= 100 else None
    if source:
        if age_min is not None and not _mentions_target_age(source, age_min):
            age_min = None
        if age_max is not None and not _mentions_target_age(source, age_max):
            age_max = None
    if age_min is not None and age_max is not None:
        age_min, age_max = sorted((age_min, age_max))

    marital = _canonical_marital(extraction.marital_status)
    if source and marital and marital.lower() not in source:
        marital = None

    occupation = extraction.occupation.strip() if extraction.occupation else None
    if source and occupation and occupation.lower() not in source:
        occupation = None

    education = extraction.education.strip() if extraction.education else None
    if source and education and education.lower() not in source:
        education = None

    children_min = extraction.children_min if extraction.children_min is not None and 0 <= extraction.children_min <= 50 else None
    children_max = extraction.children_max if extraction.children_max is not None and 0 <= extraction.children_max <= 50 else None
    if source:
        local_min, local_max = _extract_children_filter(source)
        if children_min is not None and local_min is None:
            children_min = None
        if children_max is not None and local_max is None:
            children_max = None
        if local_min is not None:
            children_min = local_min if children_min is None else max(children_min, local_min)
        if local_max is not None:
            children_max = local_max if children_max is None else min(children_max, local_max)

    return ProfileFilters(
        gender=gender,
        province=province,
        city=city,
        age_min=age_min,
        age_max=age_max,
        marital_status=marital,
        occupation=occupation,
        education=education,
        children_min=children_min,
        children_max=children_max,
    )


def merge_filters(base: ProfileFilters, ai_filters: ProfileFilters) -> ProfileFilters:
    return replace(
        base,
        gender=ai_filters.gender or base.gender,
        province=ai_filters.province or base.province,
        city=ai_filters.city or base.city,
        age_min=ai_filters.age_min if ai_filters.age_min is not None else base.age_min,
        age_max=ai_filters.age_max if ai_filters.age_max is not None else base.age_max,
        marital_status=ai_filters.marital_status or base.marital_status,
        occupation=ai_filters.occupation or base.occupation,
        education=ai_filters.education or base.education,
        children_min=ai_filters.children_min if ai_filters.children_min is not None else base.children_min,
        children_max=ai_filters.children_max if ai_filters.children_max is not None else base.children_max,
    )
