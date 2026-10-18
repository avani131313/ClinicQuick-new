"""Live voice check-ins (Gemini Live API), like talking to ChatGPT voice.

Browser  ⇄  /live/{encounter_id} WebSocket  ⇄  Gemini Live session
  • browser → server: binary = 16 kHz mono PCM16 mic audio; JSON = {type: image|text|end}
  • server → browser: binary = 24 kHz mono PCM16 Lena audio; JSON events:
      lena (caption delta) · user (caption delta) · turn_complete · interrupted
      coverage · red_flag · done · error

Safety stays in code: every chunk of the patient's live transcript runs through the
hard-coded red-flag engine (plus screen-answer checks on Lena's last question). A hit ends
the call and the browser shows the 911 / 9-8-8 screen. A background pass tags each question
(standard vs AI-personalised) and fills the intake sheet, so the clinician note still works.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from . import db, gemini, safety, triage
from .auth import read_token
from .context import compact, load_patient, memory
from .interview import PERSONALISED_RULES, SLOT_LABELS, SLOTS, coverage, required_for
from ddx.service import live_hint as ddx_live_hint  # DDX: hidden decision-support hint for Lena

log = logging.getLogger("prelude.live")
router = APIRouter()
LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live")
LIVE_VOICE = os.getenv("GEMINI_LIVE_VOICE", "Kore")
DDX_LIVE_HINTS = os.getenv("DDX_LIVE_HINTS", "1") != "0"  # DDX: set to 0 to stop hints in live voice

SYSTEM = """You are Lena, a warm, calm AI intake assistant speaking OUT LOUD with a patient before they see a clinician.
You are doing the nurse's pre-visit interview. Speak naturally and briefly, like a kind triage nurse on the phone.

How to talk:
- One short question at a time (one sentence, two at most). Never read lists aloud. No jargon.
- React briefly and humanly to what they say ("Okay, that sounds uncomfortable."), then ask the next question.
- If they interrupt or go off topic, gently follow them, then steer back.
- Never diagnose, never name possible conditions, never say it's "probably nothing", never give medication doses.
- If they describe anything that could be an emergency (chest pain, stroke signs, severe trouble breathing,
  thoughts of self-harm, heavy bleeding), tell them clearly to call 911 (or 988 for thoughts of self-harm) right now.
  The app will also stop the call automatically.

What to cover (like a nurse's intake sheet): main concern; onset; what makes it better or worse; what it feels like;
where it is and whether it spreads; severity 0-10 (only if it's a pain or discomfort); timing and pattern;
other symptoms; relevant negatives (e.g. fever); what they've tried; impact on daily life; and their own
worries and what they hope to get from the visit. Personalise using the patient context below (age, medicines such
as blood thinners, conditions, smoking, pregnancy, past visits): ask the questions a clinician would ask THIS person.
If a photo would help (skin, swelling, eyes), invite them once to tap the camera button.
If wearable_trends in the patient context show a clear change that could relate to their concern (e.g. steps down, resting heart rate up, less sleep), mention it once, naturally, and ask about it — e.g. "Your watch shows you've been walking a lot less this week than usual — is that because of this?" Never read out raw numbers lists.

Start by greeting them by first name in one sentence and asking what's brought them in today.
When the main topics are covered (usually 8-12 questions) or they want to stop, thank them, tell them you'll prepare
a summary for their clinician, and call the function finish_interview."""

SCREEN_PATTERNS = [
    ("chest_pain", r"chest (pain|pressure|tight)"),
    ("stroke", r"(weak|numb).*(one side|face|arm)|face droop|trouble (speaking|talking)|slurred"),
    ("breathing", r"(trouble|difficulty|hard to|struggling to) breath"),
    ("suicide_risk", r"(harm|hurt)(ing)? yourself|ending your life|suicid|end your life"),
    ("meningitis", r"stiff neck"),
    ("major_bleeding", r"bleeding (that )?(won'?t|doesn'?t) stop|vomiting blood|heavy bleeding"),
    ("anaphylaxis", r"(throat|tongue|lips?).*(swell|closing)"),
]


RULE_TOPICS = {"hematuria": "blood in their urine (or pink/red/brown urine)", "headache": "a headache",
               "skin": "a rash or skin problem", "skin_scalp": "an itchy or flaky scalp"}


def must_ask_rules(ctx: dict) -> str:
    """The typed interview's code-enforced personalised questions, written out for the live model.
    Live Lena is configured once at call start (before the complaint is known), so we hand her every rule
    that applies to this patient, keyed by complaint."""
    mods = {m["key"] for m in compact(ctx, [])["context_modifiers"]}
    lines = []
    for cat, mod, _slot, q, why in PERSONALISED_RULES:
        if mod not in mods:
            continue
        when = "Whatever their concern" if cat == "*" else f"If their concern is {RULE_TOPICS.get(cat, cat)}"
        lines.append(f"- {when}: you MUST ask (in your own words, early, after onset): \"{q}\" Reason: {why}")
    if not lines:
        return ""
    return ("\n\nREQUIRED PERSONALISED QUESTIONS FOR THIS PATIENT (a clinician would always ask these; do not skip them, "
            "do not finish the interview without asking the ones that apply):\n" + "\n".join(lines))


def screen_flag(lena_text: str) -> str | None:
    t = (lena_text or "").lower()
    for flag, pat in SCREEN_PATTERNS:
        if re.search(pat, t):
            return flag
    return None


# ---------------------------------------------------------------------------
# Background intake-sheet pass (keeps the clinician note structured)
# ---------------------------------------------------------------------------
class TurnTag(BaseModel):
    index: int
    question_type: str            # STANDARD | AI_PERSONALISED
    slot: str
    rationale: str


class SlotFill(BaseModel):
    slot: str
    summary: str


class SheetOut(BaseModel):
    slots_filled: list[SlotFill] = []
    turns: list[TurnTag] = []
    topics: list[str] = []


SHEET_SYSTEM = f"""You maintain a nurse's intake sheet from a live voice interview transcript.
For each numbered question, tag question_type STANDARD (generic framework question anyone would be asked) or
AI_PERSONALISED (tailored to this patient's context or answers), the slot it targeted (one of
{SLOTS + ['chief_complaint', 'other']}), and a rationale of at most 12 words.
slots_filled: every slot the patient has now answered, with a 3-12 word summary in their terms.
topics: broad themes if present (mood, sleep, fatigue, stress, anxiety, pain, skin, urinary, breathing). JSON only."""


def _update_sheet(encounter_id: str) -> list[dict] | None:
    turns = db.q("SELECT id, question, answer FROM interview_turns WHERE encounter_id=%s AND answer IS NOT NULL ORDER BY id", (encounter_id,))
    if not turns:
        return None
    tx = "\n".join(f"{i}. Q: {t['question']}\n   A: {t['answer']}" for i, t in enumerate(turns))
    out = gemini.generate_json(SHEET_SYSTEM, tx, SheetOut, thinking="MINIMAL")
    enc = db.q1("SELECT state FROM encounters WHERE id=%s", (encounter_id,))
    state = enc["state"]
    if out:
        for s in out.slots_filled:
            if s.slot in SLOTS or s.slot == "chief_complaint":
                state["slots"][s.slot] = s.summary
        state["topics"] = sorted(set(state.get("topics", [])) | {t.lower() for t in out.topics})
        for tag in out.turns:
            if 0 <= tag.index < len(turns):
                qt = tag.question_type if tag.question_type in ("STANDARD", "AI_PERSONALISED") else "AI_PERSONALISED"
                db.exe("UPDATE interview_turns SET q_type=%s, slot=%s, rationale=%s WHERE id=%s",
                       (qt, tag.slot, tag.rationale, turns[tag.index]["id"]))
    db.exe("UPDATE encounters SET state=%s WHERE id=%s", (db.J(state), encounter_id))
    return coverage(state)


def _store_turn(encounter_id: str, question: str, answer: str, first: bool):
    db.exe("""INSERT INTO interview_turns (encounter_id, question, answer, q_type, slot, rationale)
              VALUES (%s,%s,%s,'AI_PERSONALISED',%s,'Live conversation')""",
           (encounter_id, question.strip(), answer.strip(), "chief_complaint" if first else "other"))
    enc = db.q1("SELECT state FROM encounters WHERE id=%s", (encounter_id,))
    state = enc["state"]
    state.setdefault("asked_questions", []).append(question.strip())
    if first:
        state["slots"]["chief_complaint"] = triage.tidy_complaint(answer)
        state["category"] = triage.categorise(answer)
        db.exe("UPDATE encounters SET chief_complaint=%s WHERE id=%s", (triage.tidy_complaint(answer), encounter_id))
    db.exe("UPDATE encounters SET state=%s WHERE id=%s", (db.J(state), encounter_id))


def _stop_red_flag(encounter_id: str, rf: safety.RedFlagResult):
    enc = db.q1("SELECT state FROM encounters WHERE id=%s", (encounter_id,))
    state = enc["state"]
    state["red_flag"] = rf.to_dict()
    db.exe("INSERT INTO red_flag_events (encounter_id, flag, label, matched_text, action) VALUES (%s,%s,%s,%s,%s)",
           (encounter_id, rf.flag, rf.label, rf.matched_text, rf.action))
    db.exe("UPDATE encounters SET status='stopped_red_flag', urgency=%s, ended_at=now(), state=%s WHERE id=%s",
           ("er" if rf.action == "GO_TO_ER" else "emergency_911", db.J(state), encounter_id))


@router.websocket("/live/{encounter_id}")
async def live(ws: WebSocket, encounter_id: str, t: str = ""):
    try:
        user = read_token(t)
    except Exception:
        await ws.close(code=4401)
        return
    enc = await asyncio.to_thread(db.q1, "SELECT * FROM encounters WHERE id=%s AND patient_id=%s", (encounter_id, user.get("pid")))
    if not enc or enc["status"] != "active" or not gemini.enabled():
        await ws.close(code=4404 if not enc else 4409)
        return
    await ws.accept()
    ctx = await asyncio.to_thread(load_patient, str(enc["patient_id"]))
    mem = await asyncio.to_thread(memory, ctx["id"], None, 4)

    # The live call replaces the typed opening question.
    await asyncio.to_thread(db.exe, "DELETE FROM interview_turns WHERE encounter_id=%s AND answer IS NULL", (encounter_id,))
    state = enc["state"]
    state["mode"] = "live"
    await asyncio.to_thread(db.exe, "UPDATE encounters SET state=%s WHERE id=%s", (db.J(state), encounter_id))

    from google.genai import types
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=LIVE_VOICE))),
        system_instruction=SYSTEM + f"\n\nPATIENT CONTEXT (first name {ctx['first_name']}):\n{compact(ctx, mem)}" + must_ask_rules(ctx),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        tools=[types.Tool(function_declarations=[types.FunctionDeclaration(
            name="finish_interview",
            description="Call once the intake is complete or the patient wants to stop, after thanking them.",
            parameters=types.Schema(type="OBJECT", properties={}))])],
    )
    lena_buf, user_buf, last_q = "", "", ""
    n_answers = 0
    finishing = False
    sheet_task: asyncio.Task | None = None
    ddx_task: asyncio.Task | None = None  # DDX hint state
    ddx_sent, ddx_pending = "", ""

    async def send(obj):
        try:
            await ws.send_text(json.dumps(obj))
        except Exception:
            pass

    async def refresh_sheet():
        cov = await asyncio.to_thread(_update_sheet, encounter_id)
        if cov:
            await send({"type": "coverage", "coverage": cov})

    try:
        async with gemini.client().aio.live.connect(model=LIVE_MODEL, config=config) as session:
            await session.send_realtime_input(text="(The patient has just joined the call.)")
            await send({"type": "ready", "model": LIVE_MODEL})

            async def ddx_push():
                # DDX: give Lena the newest hidden hint, only between turns so she is never cut off mid-sentence
                nonlocal ddx_sent, ddx_pending
                if not ddx_pending or lena_buf.strip():
                    return
                hint, ddx_pending = ddx_pending, ""
                try:
                    await session.send_client_content(turns=types.Content(role="user", parts=[types.Part(text=(
                        "(Note from the clinic system, not said by the patient. Do not read it aloud or reply to it.)" + hint))]),
                        turn_complete=False)
                    ddx_sent = hint
                except Exception as e:  # noqa: BLE001  never break the call
                    log.warning("ddx live hint not sent: %s", e)

            async def ddx_refresh():
                # DDX: re-rank after each answer (in a thread), then push the hint if Lena is quiet
                nonlocal ddx_pending
                hint = await asyncio.to_thread(ddx_live_hint, encounter_id)
                if hint and hint != ddx_sent:
                    ddx_pending = hint
                    await ddx_push()

            async def from_browser():
                nonlocal finishing
                while True:
                    msg = await ws.receive()
                    if msg.get("type") == "websocket.disconnect":
                        return
                    if msg.get("bytes"):
                        await session.send_realtime_input(audio=types.Blob(data=msg["bytes"], mime_type="audio/pcm;rate=16000"))
                    elif msg.get("text"):
                        m = json.loads(msg["text"])
                        if m.get("type") == "image" and m.get("data"):
                            await session.send_realtime_input(video=types.Blob(data=base64.b64decode(m["data"]), mime_type=m.get("mime", "image/jpeg")))
                            await session.send_realtime_input(text="(The patient just shared the photo you can now see. Describe what you see neutrally and ask about it.)")
                        elif m.get("type") == "text" and m.get("text"):
                            await session.send_realtime_input(text=m["text"])
                        elif m.get("type") == "end":
                            finishing = True
                            return

            async def from_gemini():
                nonlocal lena_buf, user_buf, last_q, n_answers, finishing, sheet_task, ddx_task
                while True:
                    async for r in session.receive():
                        if r.tool_call:
                            for fc in r.tool_call.function_calls or []:
                                if fc.name == "finish_interview":
                                    finishing = True
                                    await session.send_tool_response(function_responses=[types.FunctionResponse(id=fc.id, name=fc.name, response={"ok": True})])
                        sc = r.server_content
                        if not sc:
                            continue
                        if sc.interrupted:
                            await send({"type": "interrupted"})
                        if sc.model_turn:
                            for part in sc.model_turn.parts or []:
                                if part.inline_data and part.inline_data.data:
                                    await ws.send_bytes(part.inline_data.data)
                        if sc.output_transcription and sc.output_transcription.text:
                            lena_buf += sc.output_transcription.text
                            await send({"type": "lena", "text": sc.output_transcription.text})
                        if sc.input_transcription and sc.input_transcription.text:
                            user_buf += sc.input_transcription.text
                            await send({"type": "user", "text": sc.input_transcription.text})
                            rf = safety.check_message(user_buf, ctx["profile"])
                            if not rf:
                                flag = screen_flag(last_q or lena_buf)
                                if flag:
                                    status, rf2 = safety.evaluate_screen(flag, user_buf, ctx["profile"])
                                    rf = rf2 if status == "positive" else None
                            if rf:
                                await asyncio.to_thread(_store_turn, encounter_id, last_q or "(live)", user_buf, n_answers == 0)
                                user_buf = ""
                                await asyncio.to_thread(_stop_red_flag, encounter_id, rf)
                                await send({"type": "red_flag", "red_flag": rf.to_dict()})
                                return
                        if sc.turn_complete:
                            if user_buf.strip() and last_q:
                                await asyncio.to_thread(_store_turn, encounter_id, last_q, user_buf, n_answers == 0)
                                n_answers += 1
                                if sheet_task is None or sheet_task.done():
                                    sheet_task = asyncio.create_task(refresh_sheet())
                                if DDX_LIVE_HINTS and (ddx_task is None or ddx_task.done()):
                                    ddx_task = asyncio.create_task(ddx_refresh())
                            if lena_buf.strip():
                                last_q = lena_buf.strip()
                            lena_buf, user_buf = "", ""
                            if DDX_LIVE_HINTS:
                                await ddx_push()  # a hint that arrived while Lena was talking
                            await send({"type": "turn_complete", "answers": n_answers})
                            if finishing:
                                await send({"type": "done"})
                                return

            tasks = [asyncio.create_task(from_browser()), asyncio.create_task(from_gemini())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()
            for d in done:
                if d.exception() and not isinstance(d.exception(), WebSocketDisconnect):
                    raise d.exception()
            # patient ended the call mid-answer: keep what they said
            if user_buf.strip() and last_q:
                await asyncio.to_thread(_store_turn, encounter_id, last_q, user_buf, n_answers == 0)
            if finishing:
                await refresh_sheet()
                await send({"type": "done"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.exception("live session failed")
        gemini.LAST_ERROR = f"live: {type(e).__name__}: {str(e)[:300]}"
        gemini.rotate(e)  # out of quota: the next call (and the fallback voice mode) uses the next key
        await send({"type": "error", "message": "The live voice connection dropped. Switching to the standard voice mode."})
    finally:
        try:
            await ws.close()
        except Exception:
            pass
