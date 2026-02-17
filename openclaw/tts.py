"""Bulletproof TTS — multi-provider voice synthesis with fallback chain.

Strategy (never fails):
  1. edge-tts (free, no API key, ~1-2s) → MP3 → ffmpeg → OGG Opus
  2. OpenAI TTS (paid, opus direct output)
  3. gTTS (Google Translate TTS, free, no key) → MP3 → ffmpeg → OGG Opus
  4. espeak (offline, always available) → WAV → ffmpeg → OGG Opus

If ALL providers fail, returns None (caller sends text instead).
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# edge-tts voice: clear American male, good for factory floor
EDGE_VOICE = "en-US-GuyNeural"
EDGE_VOICE_FALLBACK = "en-US-ChristopherNeural"

# Max text length for TTS (Telegram voice max ~1MB ≈ ~60s of audio)
MAX_TEXT_LENGTH = 3000


def _mp3_to_ogg_opus(mp3_path: str, ogg_path: str) -> bool:
    """Convert MP3/WAV to OGG Opus using ffmpeg. Returns True on success."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", mp3_path,
                "-c:a", "libopus", "-b:a", "48k",
                "-vbr", "on", "-application", "voip",
                "-ar", "48000", "-ac", "1",
                ogg_path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            logger.warning("ffmpeg conversion failed: %s", result.stderr[:200])
            return False
        return Path(ogg_path).exists() and Path(ogg_path).stat().st_size > 0
    except Exception:
        logger.exception("ffmpeg conversion error")
        return False


async def _tts_edge(text: str, ogg_path: str) -> bool:
    """Primary: edge-tts (Microsoft, free, no API key)."""
    try:
        import edge_tts

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            mp3_path = tmp.name

        try:
            communicate = edge_tts.Communicate(text, EDGE_VOICE)
            await communicate.save(mp3_path)

            if not Path(mp3_path).exists() or Path(mp3_path).stat().st_size == 0:
                # Try fallback voice
                communicate = edge_tts.Communicate(text, EDGE_VOICE_FALLBACK)
                await communicate.save(mp3_path)

            return _mp3_to_ogg_opus(mp3_path, ogg_path)
        finally:
            if os.path.exists(mp3_path):
                os.unlink(mp3_path)
    except Exception:
        logger.exception("edge-tts failed")
        return False


async def _tts_openai(text: str, ogg_path: str, api_key: str) -> bool:
    """Fallback 1: OpenAI TTS (opus direct output)."""
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        response = await client.audio.speech.create(
            model="tts-1",
            voice="onyx",
            input=text,
            response_format="opus",
        )

        # OpenAI returns raw opus, wrap in OGG container via ffmpeg
        with tempfile.NamedTemporaryFile(suffix=".opus", delete=False) as tmp:
            opus_path = tmp.name
            tmp.write(response.content)

        try:
            return _mp3_to_ogg_opus(opus_path, ogg_path)
        finally:
            if os.path.exists(opus_path):
                os.unlink(opus_path)
    except Exception:
        logger.exception("OpenAI TTS failed")
        return False


async def _tts_gtts(text: str, ogg_path: str) -> bool:
    """Fallback 2: gTTS (Google Translate, free, no API key)."""
    try:
        from gtts import gTTS

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            mp3_path = tmp.name

        try:
            tts = gTTS(text=text, lang="en", slow=False)
            tts.save(mp3_path)
            return _mp3_to_ogg_opus(mp3_path, ogg_path)
        finally:
            if os.path.exists(mp3_path):
                os.unlink(mp3_path)
    except Exception:
        logger.exception("gTTS failed")
        return False


async def _tts_espeak(text: str, ogg_path: str) -> bool:
    """Fallback 3: espeak (offline, always available on Linux)."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        try:
            # espeak writes WAV
            result = await asyncio.create_subprocess_exec(
                "espeak", "-w", wav_path, text[:1000],
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(result.wait(), timeout=10)
            return _mp3_to_ogg_opus(wav_path, ogg_path)
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)
    except Exception:
        logger.exception("espeak failed")
        return False


async def synthesize(text: str, openai_api_key: str = "") -> bytes | None:
    """Synthesize text to OGG Opus bytes. Returns None only if ALL providers fail.

    Fallback chain: edge-tts → OpenAI → gTTS → espeak
    """
    # Truncate for sanity
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "..."

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        ogg_path = tmp.name

    try:
        # Provider 1: edge-tts (free, fast, high quality)
        if await _tts_edge(text, ogg_path):
            logger.info("TTS: edge-tts success (%d bytes)", Path(ogg_path).stat().st_size)
            return Path(ogg_path).read_bytes()

        # Provider 2: OpenAI TTS (paid, reliable)
        if openai_api_key and await _tts_openai(text, ogg_path, openai_api_key):
            logger.info("TTS: OpenAI success (%d bytes)", Path(ogg_path).stat().st_size)
            return Path(ogg_path).read_bytes()

        # Provider 3: gTTS (free, Google Translate quality)
        if await _tts_gtts(text, ogg_path):
            logger.info("TTS: gTTS success (%d bytes)", Path(ogg_path).stat().st_size)
            return Path(ogg_path).read_bytes()

        # Provider 4: espeak (offline, robotic but never fails)
        if await _tts_espeak(text, ogg_path):
            logger.info("TTS: espeak success (%d bytes)", Path(ogg_path).stat().st_size)
            return Path(ogg_path).read_bytes()

        logger.error("TTS: ALL providers failed for %d chars", len(text))
        return None
    finally:
        if os.path.exists(ogg_path):
            os.unlink(ogg_path)
