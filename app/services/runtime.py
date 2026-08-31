"""Shared runtime errors and safe user-facing messages."""

from __future__ import annotations


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when a feature requires a database but no session factory exists."""


def user_message_for_error(error: BaseException | None) -> str:
    """Return a safe Arabic message without exposing internal error details."""
    if isinstance(error, DatabaseNotConfiguredError):
        return "⚠️ قاعدة البيانات غير مهيأة حالياً. جرّب بعد ما تكتمل إعدادات البوت."
    return "❌ صار خطأ غير متوقع أثناء تنفيذ العملية. جرّب مرة تانية."
