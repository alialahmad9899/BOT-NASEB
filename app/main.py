"""BOT-NASEB production entry point."""

from __future__ import annotations

import asyncio
import hmac
import logging
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler, filters

from app.config import Settings
from app.database.connection import build_engine, build_session_factory
from app.database.models import Base
from app.handlers.admin import (
    ADD_EDIT,
    ADD_RAW,
    DELETE_REQUEST,
    DISABLE_REQUEST,
    EDIT_FIELDS,
    EDIT_REQUEST,
    SEARCH_TEXT,
    admin_callback,
    admin_photo,
    admin_text,
)
from app.handlers.client import SEARCH_CONFIRM, SEARCH_TEXT as CLIENT_SEARCH_TEXT, client_callback, client_text
from app.handlers.payment import (
    WHATSAPP_INPUT,
    payment_whatsapp_cancel,
    payment_whatsapp_text,
    request_contact_callback,
    stale_payment_callback,
)
from app.handlers.start import start_command
from app.services.gemini_runtime import GeminiAIService
from app.services.runtime import user_message_for_error

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("bot-naseb")


def build_application(settings: Settings) -> Application:
    application = Application.builder().token(settings.telegram_bot_token).concurrent_updates(False).build()
    application.bot_data["settings"] = settings

    engine = build_engine(settings.database_url)
    if engine is not None:
        Base.metadata.create_all(engine)
    application.bot_data["engine"] = engine
    application.bot_data["session_factory"] = build_session_factory(engine)
    application.bot_data["ai_service"] = GeminiAIService(settings.ai_api_key, settings.ai_model)

    admin_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern=r"^admin:")],
        states={
            ADD_RAW: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text), MessageHandler(filters.PHOTO, admin_photo), CallbackQueryHandler(admin_callback, pattern=r"^admin:")],
            ADD_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text), CallbackQueryHandler(admin_callback, pattern=r"^admin:")],
            SEARCH_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text), CallbackQueryHandler(admin_callback, pattern=r"^admin:")],
            EDIT_REQUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text), CallbackQueryHandler(admin_callback, pattern=r"^admin:")],
            EDIT_FIELDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text), CallbackQueryHandler(admin_callback, pattern=r"^admin:")],
            DISABLE_REQUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text), CallbackQueryHandler(admin_callback, pattern=r"^admin:")],
            DELETE_REQUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text), CallbackQueryHandler(admin_callback, pattern=r"^admin:")],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        allow_reentry=True,
        per_message=False,
    )
    payment_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(request_contact_callback, pattern=r"^client:request:")],
        states={
            WHATSAPP_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, payment_whatsapp_text),
                CallbackQueryHandler(payment_whatsapp_cancel, pattern=r"^client:payment:whatsapp:cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        allow_reentry=True,
        per_message=False,
    )
    client_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(client_callback, pattern=r"^client:")],
        states={
            CLIENT_SEARCH_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_text), CallbackQueryHandler(client_callback, pattern=r"^client:")],
            SEARCH_CONFIRM: [CallbackQueryHandler(client_callback, pattern=r"^client:")],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        allow_reentry=True,
        per_message=False,
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(admin_conversation)
    application.add_handler(payment_conversation)
    application.add_handler(CallbackQueryHandler(stale_payment_callback, pattern=r"^client:payment:(?:submit(?:[:].*)?|cancel)$"))
    application.add_handler(client_conversation)
    application.add_error_handler(application_error)
    return application


async def cancel_command(update: Any, context: Any) -> int:
    context.user_data.clear()
    await update.effective_message.reply_text("✅ تم إلغاء العملية.")
    return ConversationHandler.END


async def application_error(update: object, context: Any) -> None:
    error = context.error
    error_type = type(error).__name__ if error else "UnknownError"
    logger.error("Unhandled application error: %s", error_type)
    message = getattr(update, "effective_message", None)
    if message is None:
        return
    try:
        await message.reply_text(user_message_for_error(error))
    except Exception:
        logger.error("Failed to send user-facing error message: ReplyError")


async def _health(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def create_web_app(application: Application, settings: Settings) -> Starlette:
    async def telegram_webhook(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not hmac.compare_digest(provided, settings.webhook_secret):
                return JSONResponse({"ok": False}, status_code=403)
        try:
            payload = await request.json()
            update = Update.de_json(payload, bot=application.bot)
            await application.update_queue.put(update)
        except Exception:
            return JSONResponse({"ok": False}, status_code=400)
        return JSONResponse({"ok": True})

    return Starlette(routes=[Route("/health", _health, methods=["GET"]), Route(settings.webhook_path, telegram_webhook, methods=["POST"])])


async def _run_webhook(application: Application, settings: Settings) -> None:
    base_url = (settings.public_base_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("PUBLIC_BASE_URL or RENDER_EXTERNAL_URL is required for webhook mode")
    webhook_url = f"{base_url}{settings.webhook_path}"
    web_app = create_web_app(application, settings)
    server = uvicorn.Server(uvicorn.Config(web_app, host="0.0.0.0", port=settings.port, log_level="info"))
    async with application:
        await application.start()
        await application.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES, secret_token=settings.webhook_secret)
        try:
            await server.serve()
        finally:
            await application.stop()


def run() -> None:
    settings = Settings.from_env()
    application = build_application(settings)
    if settings.public_base_url:
        asyncio.run(_run_webhook(application, settings))
    else:
        logger.info("No public webhook URL configured; using local polling mode")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
