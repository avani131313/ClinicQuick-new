"""Thin wrapper over the Gemini API (google-genai). Every call has a schema and a fallback:
if there's no key, the model is unavailable, or the output fails validation, callers get
None and switch to the deterministic offline path. The demo never dies on an API error."""
from __future__ import annotations

import json
import logging
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .config import GEMINI_API_KEY, GEMINI_EMBED_MODEL, GEMINI_FAST_MODEL, GEMINI_SMART_MODEL

log = logging.getLogger("prelude.gemini")
T = TypeVar("T", bound=BaseModel)

import os

_client = None
_fast_client = None
LAST_ERROR: str | None = None
# A patient should never wait longer than this for the next question. If Gemini is slower,
# that turn uses the built-in question set instead (logged), and the next turn tries Gemini again.
TURN_TIMEOUT_S = float(os.getenv("GEMINI_TURN_TIMEOUT", "12"))


def enabled() -> bool:
    return bool(GEMINI_API_KEY)


def client():
    global _client
    if _client is None and GEMINI_API_KEY:
        from google import genai
        from google.genai import types
        _client = genai.Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=90_000))
    return _client


def fast_client():
    global _fast_client
    if _fast_client is None and GEMINI_API_KEY:
        from google import genai
        from google.genai import types
        _fast_client = genai.Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=int(TURN_TIMEOUT_S * 1000)))
    return _fast_client


# Models differ in which thinking controls they accept. Try the cheapest setting first and
# remember, per model, the first one that works.
_LADDER = ["MINIMAL", "LOW", "BUDGET0", "DEFAULT"]
_model_step: dict[str, int] = {}


def _thinking(types, step: str):
    if step in ("MINIMAL", "LOW", "MEDIUM", "HIGH"):
        return types.ThinkingConfig(thinking_level=getattr(types.ThinkingLevel, step))
    if step == "BUDGET0":
        return types.ThinkingConfig(thinking_budget=0)
    return None


def generate_json(system: str, prompt: str, schema: type[T], *, smart: bool = False,
                  parts: list | None = None, temperature: float = 0.3, thinking: str | None = None) -> T | None:
    """Ask Gemini for JSON matching `schema`. Returns a validated model or None (caller falls back)."""
    global LAST_ERROR
    c = client() if smart else fast_client()
    if c is None:
        return None
    from google.genai import types
    model = GEMINI_SMART_MODEL if smart else GEMINI_FAST_MODEL
    contents = (parts or []) + [prompt]
    want = thinking or ("LOW" if smart else "MINIMAL")
    ladder = _LADDER[_LADDER.index(want):] if want in _LADDER else _LADDER
    step_i = _model_step.get(model + want, 0)
    invalid = 0
    while step_i < len(ladder):
        step = ladder[step_i]
        try:
            t0 = time.time()
            resp = c.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=temperature,
                    thinking_config=_thinking(types, step),
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            _model_step[model + want] = step_i
            log.info("gemini %s (thinking=%s) %.1fs", model, step.lower(), time.time() - t0)
            if getattr(resp, "parsed", None) is not None and isinstance(resp.parsed, schema):
                return resp.parsed
            return schema.model_validate(json.loads(resp.text))
        except (ValidationError, json.JSONDecodeError) as e:
            LAST_ERROR = f"invalid output: {e}"
            log.warning("gemini output invalid: %s", e)
            invalid += 1
            if invalid >= 2:
                return None
        except Exception as e:  # network, quota, model name, timeout
            msg = str(e)
            if "thinking" in msg.lower() and step_i + 1 < len(ladder):
                log.warning("%s rejected thinking=%s (%s); trying %s", model, step.lower(), msg[:160], ladder[step_i + 1].lower())
                step_i += 1
                continue
            LAST_ERROR = f"{type(e).__name__}: {msg[:300]}"
            if "timeout" in type(e).__name__.lower() or "timed out" in msg.lower():
                log.warning("gemini %s took over %ss; using the built-in question for this turn", model, TURN_TIMEOUT_S if not smart else 90)
            else:
                log.warning("gemini call failed: %s", msg[:300])
            return None
    return None


def generate_text(system: str, prompt: str, *, temperature: float = 0.3) -> str | None:
    global LAST_ERROR
    c = fast_client()
    if c is None:
        return None
    from google.genai import types
    step = _LADDER[_model_step.get(GEMINI_FAST_MODEL + "MINIMAL", 0)]
    try:
        resp = c.models.generate_content(
            model=GEMINI_FAST_MODEL, contents=[prompt],
            config=types.GenerateContentConfig(system_instruction=system, temperature=temperature,
                                               thinking_config=_thinking(types, step)))
        return (resp.text or "").strip() or None
    except Exception as e:
        LAST_ERROR = f"{type(e).__name__}: {e}"
        log.warning("gemini text failed: %s", e)
        return None


def embed(texts: list[str]) -> list[list[float]] | None:
    c = client()
    if c is None or not texts:
        return None
    from google.genai import types
    try:
        resp = c.models.embed_content(model=GEMINI_EMBED_MODEL, contents=texts,
                                      config=types.EmbedContentConfig(output_dimensionality=768))
        return [e.values for e in resp.embeddings]
    except Exception as e:
        log.warning("embedding failed: %s", e)
        return None


def file_part(data: bytes, mime: str):
    from google.genai import types
    return types.Part.from_bytes(data=data, mime_type=mime)
