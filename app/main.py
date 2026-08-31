"""BOT-NASEB application entry point."""

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
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from app.config import Settings
from app.handlers.admin import admin_callback
from app.handlers.client import client_callback
from app.handlers.start import start_command

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("bot-naseb")


def build_application(settings: Settings) -> Application:
    """Create exactly one Telegram application and register its Phase 1 handlers."""
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["settings"] = settings

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin:"))
    application.add_handler(CallbackQueryHandler(client_callback, pattern=r"^client:"))
    return application


def create_web_app(application: Application, settings: Settings) -> Starlette:
    """Create the small HTTP surface required for Render web service + Telegram webhook."""

    async def health(_: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    async def telegram_webhook(request: Request) -> JSONResponse:
        if settings.webhook_secret:
            provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not hmac.compare_digest(provided, settings.webhook_secret):
                return JSONResponse({"ok": False}, status_code=403)

        payload = await request.json()
        update = Update.de_json(payload, bot=application.bot)
        await application.update_queue.put(update)
        return JSONResponse({"ok": True})

    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route(settings.webhook_path, telegram_webhook, methods=["POST"]),
        ]
    )


async def _run_webhook(application: Application, settings: Settings) -> None:
    """Run the Telegram application and HTTP server together."""
    base_url = (settings.public_base_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("PUBLIC_BASE_URL or RENDER_EXTERNAL_URL is required for webhook mode")

    webhook_url = f"{base_url}{settings.webhook_path}"
    web_app = create_web_app(application, settings)
    server = uvicorn.Server(
        uvicorn.Config(web_app, host="0.0.0.0", port=settings.port, log_level="info")
    )

    async with application:
        await application.start()
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
            secret_token=settings.webhook_secret,
        )
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
        application.run_polling()


if __name__ == "__main__":
    run()
