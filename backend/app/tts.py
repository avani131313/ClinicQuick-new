"""Lena's voice: Gemini text-to-speech, returned as WAV (24 kHz mono 16-bit).

Tries the Interactions API first (current docs), then the older generate_content audio
path. Results are cached in memory, since many questions repeat across patients.
If both fail the endpoint returns 503 and the browser falls back to its own voice.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import time
import wave
from collections import OrderedDict

from . import gemini

log = logging.getLogger("prelude.tts")
TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-lite-tts")
TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", os.getenv("GEMINI_LIVE_VOICE", "Kore"))   # same voice as live Lena
STYLE = "calm, warm and unhurried, like a kind triage nurse speaking to a patient"
_cache: OrderedDict[str, bytes] = OrderedDict()
_MAX = 200
LAST_ERROR: str | None = None


def _pcm_to_wav(pcm: bytes, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _via_interactions(c, text: str) -> bytes | None:
    it = c.interactions.create(
        model=TTS_MODEL,
        input=[{"type": "user_input", "content": [{"type": "text", "text": text,
                "annotations": [{"type": "speech_metadata", "style": STYLE}]}]}],
        response_format={"type": "audio"},
        generation_config={"speech_config": [{"voice": TTS_VOICE}]},
    )
    data = base64.b64decode(it.output_audio.data)
    return data if data[:4] == b"RIFF" else _pcm_to_wav(data)


def _via_generate(c, text: str) -> bytes | None:
    from google.genai import types
    resp = c.models.generate_content(
        model=TTS_MODEL,
        contents=f"Say in a {STYLE} tone: {text}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE))),
        ),
    )
    part = resp.candidates[0].content.parts[0]
    data = part.inline_data.data
    if isinstance(data, str):
        data = base64.b64decode(data)
    return data if data[:4] == b"RIFF" else _pcm_to_wav(data)


def speak(text: str) -> bytes | None:
    global LAST_ERROR
    text = " ".join(text.split())[:600]
    if not text:
        return None
    key = f"{TTS_VOICE}|{text}"
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    c = gemini.client()
    if c is None:
        return None
    t0 = time.time()
    for fn in (_via_interactions, _via_generate):
        try:
            wav = fn(c, text)
            if wav:
                log.info("tts %s via %s %.1fs", TTS_MODEL, fn.__name__, time.time() - t0)
                _cache[key] = wav
                if len(_cache) > _MAX:
                    _cache.popitem(last=False)
                return wav
        except Exception as e:
            LAST_ERROR = f"{fn.__name__}: {type(e).__name__}: {e}"
            log.warning("tts %s failed: %s", fn.__name__, e)
            if gemini.rotate(e):  # out of quota: the next voice line uses the next key
                c = gemini.client()
    return None
