"""Payment-contact helpers for manual WhatsApp follow-up."""

from __future__ import annotations

import re


def normalize_whatsapp(value: str) -> str | None:
    """Normalize a Syrian WhatsApp number to +9639XXXXXXXX."""
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("963"):
        local = digits[3:]
    else:
        local = digits
    if len(local) != 10 or not local.startswith("09"):
        return None
    normalized = f"+963{local[1:]}"
    if not re.fullmatch(r"\+9639\d{8}", normalized):
        return None
    return normalized


def whatsapp_prompt() -> str:
    return (
        "📱 ابعت رقم الواتساب اللي بدك الخطّابة تتواصل معك عليه.\n\n"
        "مثال:\n"
        "09xxxxxxxx\n"
        "أو +9639xxxxxxxx\n\n"
        "الرقم رح ينحفظ ضمن طلب التواصل ويظهر للأدمن فقط."
    )
