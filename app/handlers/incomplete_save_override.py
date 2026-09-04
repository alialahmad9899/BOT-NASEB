"""Hardened incomplete-profile save handler.

This module is installed from the production entry point after Admin V2 is fully
loaded. It keeps the user-facing "save despite missing fields" action independent
from the legacy router and uses the database-generated profile id to derive a
fresh request number at save time.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database.repositories import ProfileRepository
from app.handlers import admin_v2
from app.services.admin_meta import get_profile_meta, log_admin_action
from app.services.ai import ProfileExtraction
from app.services.profile_quality import score_profile
from app.services.profiles import ProfileDraft, extraction_to_draft, validate_profile_extraction

logger = logging.getLogger("bot-naseb.incomplete-save")


def _normalized_draft(draft: ProfileDraft) -> ProfileDraft:
    extraction = ProfileExtraction.model_validate({**draft.public_data, **draft.private_contact_data})
    return extraction_to_draft(extraction)


async def _save_add(update: Any, context: Any) -> int:
    draft: ProfileDraft | None = context.user_data.get("v2_draft")
    if draft is None:
        await update.callback_query.edit_message_text(
            "❌ ما في مسودة للحفظ.", reply_markup=admin_v2._dashboard_keyboard()
        )
        return admin_v2.END

    try:
        draft = _normalized_draft(draft)
        extraction = ProfileExtraction.model_validate({**draft.public_data, **draft.private_contact_data})
        validation = validate_profile_extraction(extraction, draft.private_contact_data)
        if not validation.ok:
            await update.callback_query.edit_message_text(
                "❌ في قيمة غير صحيحة بالإعلان:\n\n"
                + "\n".join(f"• {error}" for error in validation.errors)
                + "\n\nصحّح القيمة غير الصحيحة قبل الحفظ.",
                reply_markup=admin_v2._back_keyboard(),
            )
            return admin_v2.ADMIN_V2_INPUT

        quality = score_profile(draft)
        admin_id = int(update.effective_user.id)

        with admin_v2._session(context) as session:
            repository = ProfileRepository(session)
            # Never trust a preview-time number. The profile id is allocated by the
            # database now, then the repository derives a unique request number.
            profile = repository.create(draft, request_number=None)
            number = int(profile.request_number)

            meta = get_profile_meta(session, int(profile.id), create=True)
            meta.quality_score = quality.score
            meta.publication_status = "ready" if quality.ready else "review"
            log_admin_action(
                session,
                admin_id,
                "profile_add",
                "profile",
                number,
                {"quality": quality.score, "incomplete": bool(quality.missing_fields)},
            )
            session.commit()

        context.user_data.clear()
        message_text = (
            "✅ تم حفظ الإعلان بنجاح.\n\n"
            f"📌 رقم الإعلان: {number}\n"
            f"⭐ الجودة: {quality.score}/100\n"
            f"📤 الحالة: {'جاهز للنشر' if quality.ready else 'قيد المراجعة'}"
        )
        try:
            await update.callback_query.edit_message_text(
                message_text, reply_markup=admin_v2._dashboard_keyboard()
            )
        except Exception:
            logger.warning("Saved incomplete profile %s but Telegram edit failed", number, exc_info=True)
            try:
                await update.effective_message.reply_text(
                    message_text, reply_markup=admin_v2._dashboard_keyboard()
                )
            except Exception:
                logger.warning("Saved incomplete profile %s but fallback reply also failed", number, exc_info=True)
        return admin_v2.END

    except IntegrityError:
        logger.exception("Integrity error while saving incomplete profile")
        try:
            with admin_v2._session(context) as rollback_session:
                rollback_session.rollback()
        except Exception:
            pass
        await update.callback_query.edit_message_text(
            "❌ ما انحفظ الإعلان بسبب تعارض ببيانات الحفظ.\n\n"
            "ما تم ترك أي جزء من العملية محفوظ. اضغط رجوع وجرّب الإضافة من جديد.",
            reply_markup=admin_v2._dashboard_keyboard(),
        )
        return admin_v2.END
    except (SQLAlchemyError, ValueError, TypeError) as exc:
        logger.exception("Database/value error while saving incomplete profile: %s", type(exc).__name__)
        try:
            with admin_v2._session(context) as rollback_session:
                rollback_session.rollback()
        except Exception:
            pass
        await update.callback_query.edit_message_text(
            "❌ ما انحفظ الإعلان بسبب خطأ في بيانات الحفظ.\n\n"
            "ما تم اعتماد الإعلان. رجّع للإضافة وجرّب مرة ثانية.",
            reply_markup=admin_v2._dashboard_keyboard(),
        )
        return admin_v2.END
    except Exception:
        logger.exception("Unexpected error while saving incomplete profile")
        await update.callback_query.edit_message_text(
            "❌ صار خطأ أثناء حفظ الإعلان، وما تم اعتماد البيانات.\n\nجرّب إضافة الإعلان مرة ثانية.",
            reply_markup=admin_v2._dashboard_keyboard(),
        )
        return admin_v2.END


def install() -> None:
    admin_v2._save_add = _save_add
    logger.info("Installed hardened incomplete-profile save handler")
