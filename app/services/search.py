"""Natural-language search parsing with Gemini-backed filters and DB-safe normalization."""

from __future__ import annotations

import re
from dataclasses import replace

from app.database.repositories import ProfileFilters
from app.services.ai import SearchFilterExtraction
from app.services.profiles import normalize_digits

RESIDENCE_ALIASES = {
    "شام": "دمشق", "الشام": "دمشق", "دمشق": "دمشق", "حلب": "حلب", "حمص": "حمص", "حماة": "حماة",
    "اللاذقية": "اللاذقية", "طرطوس": "طرطوس", "ادلب": "إدلب", "إدلب": "إدلب", "الرقة": "الرقة",
    "دير الزور": "دير الزور", "الحسكة": "الحسكة", "درعا": "درعا", "السويداء": "السويداء", "القنيطرة": "القنيطرة",
    "ريف دمشق": "ريف دمشق", "ريف حلب": "ريف حلب", "ريف حمص": "ريف حمص", "ريف حماة": "ريف حماة", "ريف إدلب": "ريف إدلب",
    "جرمانا": "جرمانا",
}

MARITAL_ALIASES = {
    "عزباء": "عزباء", "عازبة": "عزباء", "عزبا": "عزباء", "عزبة": "عزباء", "عزب": "عزباء",
    "أعزب": "عازب", "اعزب": "عازب", "عازب": "عازب", "مطلقة": "مطلقة", "مطلقه": "مطلقة", "مطلق": "مطلق",
    "أرملة": "أرملة", "ارملة": "أرملة", "أرمل": "أرمل", "ارمل": "أرمل", "متزوجة": "متزوجة", "متزوجه": "متزوجة", "متزوج": "متزوج",
    "منفصلة": "منفصلة", "منفصله": "منفصلة", "منفصل": "منفصل",
}


def _canonical_residence(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"\s+", " ", normalize_digits(value).strip().lower())
    return RESIDENCE_ALIASES.get(normalized, value.strip())


def _canonical_marital(value: str | None) -> str | None:
    if not value:
        return None
    normalized = normalize_digits(value).strip().lower()
    return MARITAL_ALIASES.get(normalized, value.strip())


def _is_negated(text: str, start: int) -> bool:
    prefix = text[max(0, start - 18):start]
    return bool(re.search(r"(?:مو|مش|ما\s+تكون|ما\s+يكون|غير|مو\s+هي|مو\s+هو)\s*$", prefix))


def _marital_mentioned(text: str, canonical: str) -> bool:
    for alias, normalized in MARITAL_ALIASES.items():
        if normalized != canonical:
            continue
        start = text.find(alias)
        while start >= 0:
            if not _is_negated(text, start):
                return True
            start = text.find(alias, start + len(alias))
    return False


def _residence_mentioned(text: str, residence: str) -> bool:
    normalized = normalize_digits(text).lower()
    value = residence.strip().lower()
    if value in normalized:
        return True
    for alias, canonical in RESIDENCE_ALIASES.items():
        if canonical.lower() == value and alias in normalized:
            return True
    return any(part.strip() and part.strip().lower() in normalized for part in re.split(r"[-–/]", value) if len(part.strip()) >= 3)


def _extract_age_range(text: str) -> tuple[int, int] | None:
    patterns = (
        r"(?:من|بين)\s*(?:ال\s*)?(\d{1,3})\s*(?:الى|إلى|و|ل(?:ـ)?|حتى|لـ|[-–])\s*(?:ال\s*)?(\d{1,3})",
        r"(?:من)\s*(\d{1,3})\s*(?:ل(?:ـ)?|الى|إلى|حتى)\s*(\d{1,3})",
        r"(?:ال)?\s*(\d{2,3})\s*[-–]\s*(?:ال)?\s*(\d{2,3})",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            values = tuple(sorted((int(match.group(1)), int(match.group(2)))))
            if all(18 <= value <= 100 for value in values):
                return values
    return None


def _extract_age_bounds(text: str) -> tuple[int | None, int | None]:
    normalized = normalize_digits(text).lower()
    for pattern in (
        r"(?:ما\s*يزيد\s*عن|ما\s*يتجاوز|حد(?:ود)?|لحد|حتى|أقصى|اقصى|تحت)\s*(?:ال)?\s*(\d{1,3})",
        r"(?:فوق|أكبر\s*من|اكبر\s*من|ابتداءً\s*من|من)\s*(?:ال)?\s*(\d{1,3})\s*(?:سنة|سنين|عام)?$",
    ):
        match = re.search(pattern, normalized)
        if match:
            value = int(match.group(1))
            if 18 <= value <= 100:
                if any(token in pattern for token in ("يزيد", "يتجاوز", "أقصى", "اقصى", "تحت", "حتى", "حد")):
                    return None, value
                return value, None
    match = re.search(r"(?:حوالي|قرابة|تقريباً|تقريبا|حدود)\s*(?:ال)?\s*(\d{1,3})", normalized)
    if match:
        value = int(match.group(1))
        if 18 <= value <= 100:
            return value, value
    return None, None


def _extract_single_age(text: str) -> int | None:
    match = re.search(r"(?:عمر|العمر|عمرا|عمرها|عمره|بعمر|سنها|سنه)\s*[:=-]?\s*(?:ال)?\s*(\d{1,3})", text)
    if match:
        value = int(match.group(1))
        if 18 <= value <= 100:
            return value
    return int(text) if text.isdigit() and 18 <= int(text) <= 100 else None


def _extract_children_filter(text: str) -> tuple[int | None, int | None]:
    normalized = normalize_digits(text).lower()
    if re.search(r"(?:بدون|ما\s*عندها|ماعندها|ما\s*عنده|ماعنده|ما\s*عندي|ماعندي|ما\s*فيها|مابيها)\s+(?:ولاد|اولاد|أولاد|أطفال|اطفال)", normalized):
        return 0, 0
    for phrase, count in (("ولد واحد", 1), ("طفل واحد", 1), ("ولدين", 2), ("طفلين", 2), ("ثلاثة أولاد", 3), ("ثلاث اولاد", 3)):
        if phrase in normalized:
            return count, count
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


def _extract_residence(text: str) -> str | None:
    normalized = normalize_digits(text).lower()
    for key in sorted(RESIDENCE_ALIASES, key=len, reverse=True):
        if re.search(rf"(?<![\u0600-\u06ff]){re.escape(key)}(?![\u0600-\u06ff])", normalized):
            return RESIDENCE_ALIASES[key]
    return None


def parse_search_text(text: str) -> ProfileFilters:
    normalized = normalize_digits(text).strip().lower()
    gender = "female" if re.search(r"بنت|صبية|عروس|حروس|انثى|أنثى|فتاة", normalized) else "male" if re.search(r"شاب|شب|عريس|ذكر|رجل", normalized) else None
    residence = _extract_residence(normalized)
    marital = None
    for _, canonical in MARITAL_ALIASES.items():
        if _marital_mentioned(normalized, canonical):
            marital = canonical
            break

    age_min = age_max = None
    age_range = _extract_age_range(normalized)
    if age_range:
        age_min, age_max = age_range
    else:
        bounds_min, bounds_max = _extract_age_bounds(normalized)
        if bounds_min is not None or bounds_max is not None:
            age_min, age_max = bounds_min, bounds_max
        else:
            single_age = _extract_single_age(normalized)
            if single_age is not None:
                age_min = age_max = single_age

    children_min, children_max = _extract_children_filter(normalized)
    education = _extract_education(normalized)

    occupation = None
    for marker in ("ربة منزل", "طالبة طب", "طالب طب", "طالبة", "طالب", "مدرسة", "مدرس", "مهندس", "طبيب", "ممرض", "موظف", "موظفة", "محامي", "محامية", "تاجر", "متعهد"):
        if marker in normalized:
            occupation = marker
            break

    return ProfileFilters(
        gender=gender, residence=residence, age_min=age_min, age_max=age_max,
        marital_status=marital, occupation=occupation, education=education,
        children_min=children_min, children_max=children_max,
    )


def _mentions_target_age(text: str, age: int) -> bool:
    normalized = normalize_digits(text).lower()
    value = str(age)
    if re.search(rf"(?:^|\s)عمري\s*[:=]?\s*{re.escape(value)}(?:\s|$)", normalized):
        return False
    if re.search(rf"(?:عمر|العمر|عمرا|عمرها|عمره|بعمر|سنها|سنه|حوالي|قرابة|تقريبا|تقريباً)\s*[:=]?\s*(?:ال)?\s*{re.escape(value)}(?:\s|$)", normalized):
        return True
    for match in re.finditer(r"(?:بين|من)\s*(?:ال)?\s*(\d{1,3})\s*(?:و|الى|إلى|ل(?:ـ)?|حتى|[-–]|لـ)\s*(?:ال)?\s*(\d{1,3})", normalized):
        if value in {match.group(1), match.group(2)}:
            return True
    return bool(re.search(rf"(?:حتى|حدود|ما\s*يتجاوز|ما\s*يزيد\s*عن|تحت|فوق)\s*(?:ال)?\s*{re.escape(value)}", normalized))


def filters_from_ai(extraction: SearchFilterExtraction, raw_text: str | None = None) -> ProfileFilters:
    source = normalize_digits(raw_text or "").lower()
    gender = extraction.gender if extraction.gender in {"male", "female"} else None
    if source and gender == "female" and not re.search(r"بنت|صبية|عروس|حروس|انثى|أنثى|فتاة", source):
        gender = None
    if source and gender == "male" and not re.search(r"شاب|شب|عريس|ذكر|رجل", source):
        gender = None

    residence = _canonical_residence(extraction.residence)
    if source and residence and not _residence_mentioned(source, residence):
        residence = None

    age_min = extraction.age_min if extraction.age_min is not None and 18 <= extraction.age_min <= 100 else None
    age_max = extraction.age_max if extraction.age_max is not None and 18 <= extraction.age_max <= 100 else None
    if source:
        if age_min is not None and not _mentions_target_age(source, age_min):
            age_min = None
        if age_max is not None and not _mentions_target_age(source, age_max):
            age_max = None
    if age_min is not None and age_max is not None:
        age_min, age_max = sorted((age_min, age_max))

    marital = _canonical_marital(extraction.marital_status)
    if source and marital and not _marital_mentioned(source, marital):
        marital = None

    occupation = extraction.occupation.strip() if extraction.occupation else None
    education = extraction.education.strip() if extraction.education else None
    if source and occupation and not any(token in source for token in occupation.lower().split() if len(token) >= 3):
        occupation = None
    if source and education and not any(token in source for token in education.lower().split() if len(token) >= 3):
        education = None

    children_min = extraction.children_min if extraction.children_min is not None and 0 <= extraction.children_min <= 50 else None
    children_max = extraction.children_max if extraction.children_max is not None and 0 <= extraction.children_max <= 50 else None
    local_min, local_max = _extract_children_filter(source)
    if local_min is not None:
        children_min = local_min if children_min is None else max(children_min, local_min)
    if local_max is not None:
        children_max = local_max if children_max is None else min(children_max, local_max)

    return ProfileFilters(
        gender=gender, residence=residence, age_min=age_min, age_max=age_max,
        marital_status=marital, occupation=occupation, education=education,
        children_min=children_min, children_max=children_max,
    )


def merge_filters(base: ProfileFilters, ai_filters: ProfileFilters) -> ProfileFilters:
    return replace(
        base,
        gender=ai_filters.gender or base.gender,
        residence=ai_filters.residence or base.residence,
        age_min=ai_filters.age_min if ai_filters.age_min is not None else base.age_min,
        age_max=ai_filters.age_max if ai_filters.age_max is not None else base.age_max,
        marital_status=ai_filters.marital_status or base.marital_status,
        occupation=ai_filters.occupation or base.occupation,
        education=ai_filters.education or base.education,
        children_min=ai_filters.children_min if ai_filters.children_min is not None else base.children_min,
        children_max=ai_filters.children_max if ai_filters.children_max is not None else base.children_max,
    )
