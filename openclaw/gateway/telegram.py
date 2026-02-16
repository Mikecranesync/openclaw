"""Telegram channel adapter — polling-based bot."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Callable, Awaitable

import httpx
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters

from openclaw.gateway.base import ChannelAdapter
from openclaw.messages.models import Attachment, InboundMessage, OutboundMessage
from openclaw.types import Channel

logger = logging.getLogger(__name__)

TELEGRAM_MAX_LEN = 4096
WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-large-v3-turbo"


def _chunk_text(text: str, max_len: int = TELEGRAM_MAX_LEN) -> list[str]:
    """Split text into chunks that fit Telegram message limit.

    Split strategy: prefer \\n\\n boundaries, then \\n, then hard cut.
    """
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Try to split on paragraph break
        cut = text.rfind("\n\n", 0, max_len)
        if cut == -1:
            # Try line break
            cut = text.rfind("\n", 0, max_len)
        if cut == -1:
            # Hard cut
            cut = max_len

        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")

    logger.debug("_chunk_text: %d chars -> %d chunk(s)", sum(len(c) for c in chunks), len(chunks))
    return chunks


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
        self._app.add_handler(MessageHandler(filters.VOICE, self._on_voice))
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
            for chunk in _chunk_text(message.text):
                try:
                    await self._app.bot.send_message(
                        chat_id=int(message.user_id),
                        text=chunk,
                        parse_mode="Markdown" if message.parse_mode == "markdown" else None,
                    )
                except Exception:
                    await self._app.bot.send_message(
                        chat_id=int(message.user_id),
                        text=chunk.replace("*", "").replace("_", "").replace("`", ""),
                    )

    def name(self) -> str:
        return "telegram"

    def _is_allowed(self, user_id: int) -> bool:
        if not self._allowed_users:
            return True
        return user_id in self._allowed_users

    async def _reply(self, update: Update, text: str) -> None:
        """Reply with chunking + Markdown fallback on parse errors."""
        for i, chunk in enumerate(_chunk_text(text)):
            try:
                await update.message.reply_text(chunk, parse_mode="Markdown")
            except Exception:
                try:
                    plain = chunk.replace("*", "").replace("_", "").replace("`", "")
                    await update.message.reply_text(plain)
                except Exception as e:
                    logger.error("Failed to send chunk %d: %s", i + 1, e)
                    try:
                        await update.message.reply_text("Response too long to display. Check logs.")
                    except Exception:
                        pass
                    break

    async def _transcribe_voice(self, audio_bytes: bytes) -> str:
        """Transcribe voice audio using Groq Whisper API."""
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                WHISPER_URL,
                files={
                    "file": ("voice.ogg", audio_bytes, "audio/ogg"),
                    "model": (None, WHISPER_MODEL),
                    "response_format": (None, "text"),
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code == 200:
                return resp.text.strip()
            raise RuntimeError(f"Whisper API {resp.status_code}: {resp.text[:200]}")

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
        try:
            file = await context.bot.get_file(photo.file_id)
            data = await file.download_as_bytearray()
        except Exception as e:
            logger.error("Failed to download photo: %s", e)
            await update.message.reply_text("Could not download photo. Please try again.")
            return

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

    async def _on_voice(self, update: Update, context) -> None:
        if not update.message or not update.message.voice:
            return
        user = update.message.from_user
        if not user or not self._is_allowed(user.id):
            return

        voice = update.message.voice
        logger.info("Voice message: %ds, %d bytes", voice.duration, voice.file_size or 0)

        # Download
        try:
            file = await context.bot.get_file(voice.file_id)
            data = await file.download_as_bytearray()
        except Exception as e:
            logger.error("Failed to download voice: %s", e)
            await update.message.reply_text("Could not download voice message. Please try again.")
            return

        # Transcribe
        try:
            transcript = await self._transcribe_voice(bytes(data))
        except Exception as e:
            logger.error("Voice transcription failed: %s", e)
            await update.message.reply_text("Could not transcribe voice message. Please try again.")
            return

        if not transcript or not transcript.strip():
            await update.message.reply_text("I couldn't make out any words. Could you try again?")
            return

        logger.info("Transcribed voice: %s", transcript[:100])

        # Dispatch transcribed text through normal pipeline
        msg = InboundMessage(
            id=str(uuid.uuid4()),
            channel=Channel.TELEGRAM,
            user_id=str(user.id),
            user_name=user.first_name or "",
            text=transcript,
        )
        try:
            response = await self._dispatch(msg)
            reply_text = f'Heard: "{transcript}"\n\n{response.text}'
            await self._reply(update, reply_text)
        except Exception as e:
            logger.error("voice dispatch failed: %s", e)
            await update.message.reply_text("Sorry, something went wrong processing your voice message.")

    async def _on_start(self, update: Update, context) -> None:
        if update.message:
            await update.message.reply_text(
                "Jarvis here. Send me a message, photo, or voice note and I will help diagnose your equipment.\n\n"
                "Commands:\n"
                "- /status - system status\n"
                "- /diagnose - equipment diagnosis\n"
                "- /search <query> - web search\n"
                "- /health - system health"
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
