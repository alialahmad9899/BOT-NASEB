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


def parse_search_text(text: str) -> ProfileFilters:
    normalized = normalize_digits(text).strip().lower()
    gender = None
    marital = None
    province = next((p for p in PROVINCES if p.lower() in normalized), None)
    if re.search(r"(?:بنت|عروس|انثى|أنثى|فتاة)", normalized):
        gender = "female"
    elif re.search(r"(?:شاب|عريس|ذكر|رجل)", normalized):
        gender = "male"
    if any(word in normalized for word in ("عزباء", "عازبة")):
        marital = "عزباء"
    elif "عازب" in normalized:
        marital = "عازب"
    elif "مطلقة" in normalized or "مطلق" in normalized:
        marital = "مطلقة" if "مطلقة" in normalized else "مطلق"
    age_min = age_max = None
    m = re.search(r"(?:من|بين)\s*(\d{2})\s*(?:الى|إلى|و|ل|حتى|-)+\s*(\d{2})", normalized)
    if m:
        age_min, age_max = sorted((int(m.group(1)), int(m.group(2))))
    else:
        range_match = re.search(r"(\d{2})\s*[-–]\s*(\d{2})", normalized)
        if range_match:
            age_min, age_max = sorted((int(range_match.group(1)), int(range_match.group(2))))
        else:
            single = re.search(r"(?:عمر|العمر)\s*(\d{2})", normalized)
            if single:
                age_min = age_max = int(single.group(1))
            elif normalized.isdigit() and 18 <= int(normalized) <= 100:
                age_min = age_max = int(normalized)
    city = None
    hyphen_city = re.search(r"(?:ريف دمشق|دمشق|حلب|حمص|حماة|اللاذقية|طرطوس|إدلب|الرقة|دير الزور|الحسكة|درعا|السويداء|القنيطرة)\s*[-–/]\s*([\u0600-\u06ff]{3,30})", normalized)
    if hyphen_city:
        city = hyphen_city.group(1).strip()
    city_match = re.search(r"(?:مدينة|ساكن(?:ة)?|سكن(?:ي)?|من|بـ|ب)\s+([\u0600-\u06ff]{3,30})", normalized)
    if city_match:
        candidate = city_match.group(1).strip(" ،,")
        if not city and candidate not in {p.lower() for p in PROVINCES} and candidate not in {p.lower().split()[0] for p in PROVINCES}:
            city = candidate
    occupation = None
    for marker in ("مدرسة", "مدرس", "مهندس", "طبيب", "ممرض", "موظف", "موظفة", "محامي", "محامية", "تاجر", "متعهد", "ربة منزل"):
        if marker in normalized:
            occupation = marker
            break
    return ProfileFilters(gender=gender, province=province, city=city, age_min=age_min, age_max=age_max, marital_status=marital, occupation=occupation)


def _mentions_target_age(text: str, age: int) -> bool:
    normalized = normalize_digits(text).lower()
    value = str(age)
    if re.search(rf"(?:^|\s)عمري\s*[:=]?\s*{re.escape(value)}(?:\s|$)", normalized):
        return False
    if re.search(
        rf"(?:عمر|العمر|بعمر|عمرها|عمره)\s*[:=]?\s*{re.escape(value)}(?:\s|$)",
        normalized,
    ):
        return True
    for match in re.finditer(
        r"(?:بين|من)\s*(\d{2})\s*(?:و|الى|إلى|ل|حتى|[-–])\s*(\d{2})",
        normalized,
    ):
        if value in {match.group(1), match.group(2)}:
            return True
    return False


def filters_from_ai(extraction: SearchFilterExtraction, raw_text: str | None = None) -> ProfileFilters:
    source = normalize_digits(raw_text or "").lower()

    gender = extraction.gender if extraction.gender in {"male", "female"} else None
    if source and gender == "female" and not re.search(r"بنت|عروس|انثى|أنثى|فتاة", source):
        gender = None
    if source and gender == "male" and not re.search(r"شاب|عريس|ذكر|رجل", source):
        gender = None

    province = extraction.province.strip() if extraction.province else None
    if province and province.lower() not in {item.lower() for item in PROVINCES}:
        province = None
    if source and province and province.lower() not in source:
        province = None

    city = extraction.city.strip() if extraction.city else None
    if source and city and city.lower() not in source:
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

    marital = extraction.marital_status.strip() if extraction.marital_status else None
    if source and marital and marital.lower() not in source:
        marital = None
    occupation = extraction.occupation.strip() if extraction.occupation else None
    if source and occupation and occupation.lower() not in source:
        occupation = None

    return ProfileFilters(
        gender=gender,
        province=province,
        city=city,
        age_min=age_min,
        age_max=age_max,
        marital_status=marital,
        occupation=occupation,
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
    )
