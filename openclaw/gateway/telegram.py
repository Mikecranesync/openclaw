"""Telegram channel adapter — polling-based bot."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Callable, Awaitable

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters

from openclaw.gateway.base import ChannelAdapter
from openclaw.messages.models import Attachment, InboundMessage, OutboundMessage
from openclaw.types import Channel

logger = logging.getLogger(__name__)


class TelegramAdapter(ChannelAdapter):
    def __init__(
        self,
        token: str,
        dispatch: Callable[[InboundMessage], Awaitable[OutboundMessage]],
        allowed_users: list[int] | None = None,
    ) -> None:
        self._token = token
        self._dispatch = dispatch
        self._allowed_users = set(allowed_users) if allowed_users else None
        self._app: Application | None = None

    async def start(self) -> None:
        self._app = Application.builder().token(self._token).build()
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))
        self._app.add_handler(MessageHandler(filters.PHOTO, self._on_photo))
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("help", self._on_help))
        self._app.add_handler(CommandHandler("status", self._on_command))
        self._app.add_handler(CommandHandler("diagnose", self._on_command))
        self._app.add_handler(CommandHandler("health", self._on_command))
        self._app.add_handler(CommandHandler("search", self._on_command))

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram adapter started")

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def send(self, message: OutboundMessage) -> None:
        if self._app:
            await self._app.bot.send_message(
                chat_id=int(message.user_id),
                text=message.text,
                parse_mode="Markdown" if message.parse_mode == "markdown" else None,
            )

    def name(self) -> str:
        return "telegram"

    def _is_allowed(self, user_id: int) -> bool:
        if not self._allowed_users:
            return True
        return user_id in self._allowed_users

    async def _reply(self, update: Update, text: str) -> None:
        """Reply with Markdown, falling back to plain text on parse errors."""
        try:
            await update.message.reply_text(text, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(text)

    async def _on_message(self, update: Update, context) -> None:
        if not update.message or not update.message.text:
            return
        user = update.message.from_user
        if not user or not self._is_allowed(user.id):
            return

        msg = InboundMessage(
            id=str(uuid.uuid4()),
            channel=Channel.TELEGRAM,
            user_id=str(user.id),
            user_name=user.first_name or "",
            text=update.message.text,
        )
        try:
            response = await self._dispatch(msg)
            await self._reply(update, response.text)
        except Exception as e:
            logger.error("dispatch failed: %s", e)
            await update.message.reply_text("Sorry, something went wrong. Please try again.")

    async def _on_photo(self, update: Update, context) -> None:
        if not update.message or not update.message.photo:
            return
        user = update.message.from_user
        if not user or not self._is_allowed(user.id):
            return

        photo = update.message.photo[-1]  # Largest size
        file = await context.bot.get_file(photo.file_id)
        data = await file.download_as_bytearray()

        msg = InboundMessage(
            id=str(uuid.uuid4()),
            channel=Channel.TELEGRAM,
            user_id=str(user.id),
            user_name=user.first_name or "",
            text=update.message.caption or "",
            attachments=[Attachment(type="image", data=bytes(data), mime_type="image/jpeg")],
        )
        try:
            response = await self._dispatch(msg)
            await self._reply(update, response.text)
        except Exception as e:
            logger.error("photo dispatch failed: %s", e)
            await update.message.reply_text("Sorry, something went wrong processing that image.")

    async def _on_start(self, update: Update, context) -> None:
        if update.message:
            await update.message.reply_text(
                "Welcome to OpenClaw! I'm your factory AI assistant.\n\n"
                "Send me a message like:\n"
                "- \"Why is conveyor 1 stopped?\"\n"
                "- \"Show me current status\"\n"
                "- Send a photo for equipment analysis\n"
                "- /health for system status"
            )

    async def _on_help(self, update: Update, context) -> None:
        await self._on_start(update, context)

    async def _on_command(self, update: Update, context) -> None:
        if not update.message:
            return
        user = update.message.from_user
        if not user or not self._is_allowed(user.id):
            return

        text = update.message.text or ""
        msg = InboundMessage(
            id=str(uuid.uuid4()),
            channel=Channel.TELEGRAM,
            user_id=str(user.id),
            user_name=user.first_name or "",
            text=text,
        )
        try:
            response = await self._dispatch(msg)
            await self._reply(update, response.text)
        except Exception as e:
            logger.error("command dispatch failed: %s", e)
            await update.message.reply_text("Sorry, something went wrong. Please try again.")
