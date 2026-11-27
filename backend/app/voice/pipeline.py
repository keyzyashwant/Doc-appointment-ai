"""Voice pipeline – SmallWebRTC + Silero VAD + ElevenLabs STT/TTS + Gemini.

This module exposes ``run_bot(webrtc_connection)`` which is called once per
WebRTC session from the /api/offer route.
"""
import asyncio
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    ErrorFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMRunFrame,
    TTSAudioRawFrame,
    TranscriptionFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)

from pipecat.processors.frameworks.rtvi import RTVIObserverParams
from pipecat.services.elevenlabs.stt import CommitStrategy, ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.call_session import CallSession
from app.models.enums import CallSessionStatus
from app.core.specialities import get_speciality_catalog
from app.voice.tools import ALL_TOOLS, configure_speciality_catalog

CLINIC_TZ = ZoneInfo("Asia/Kolkata")


class _PipelineLogObserver(BaseObserver):
    def __init__(self) -> None:
        super().__init__(observe_every_push=False)
        self._greeting_audio_pending = False

    def expect_greeting_audio(self) -> None:
        self._greeting_audio_pending = True

    def clear_greeting_audio(self) -> None:
        self._greeting_audio_pending = False

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        if isinstance(frame, TranscriptionFrame):
            logger.info("Final STT transcript: {}", frame.text)
        elif isinstance(frame, LLMFullResponseStartFrame):
            logger.info("LLM response started")
        elif isinstance(frame, LLMFullResponseEndFrame):
            logger.info("LLM response ended")
        elif isinstance(frame, TTSStartedFrame):
            logger.info("TTS started")
        elif isinstance(frame, TTSAudioRawFrame) and frame.audio:
            if self._greeting_audio_pending:
                logger.info("Greeting audio started")
                self._greeting_audio_pending = False
        elif isinstance(frame, TTSStoppedFrame):
            logger.info("TTS stopped")


def _log_tts_failure(source: str, error: object, exception: Exception | None = None) -> None:
    response = getattr(exception, "response", None)
    http_status = getattr(response, "status_code", None) or getattr(response, "status", None)
    body = getattr(response, "body", None)
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")

    provider_status = None
    message = str(error)
    if body:
        try:
            payload = json.loads(body)
        except (TypeError, ValueError):
            payload = None
        if isinstance(payload, dict):
            detail = payload.get("detail", payload)
            if isinstance(detail, dict):
                provider_status = detail.get("status") or detail.get("code")
                message = detail.get("message") or payload.get("message") or str(detail)
            elif detail:
                message = str(detail)
        else:
            message = str(body)

    error_text = " ".join(part for part in (str(error), str(exception or "")) if part)
    if http_status is None:
        match = re.search(r"\bHTTP(?:\s+status)?\s*[:=]?\s*(\d{3})\b", error_text, re.I)
        if match:
            http_status = match.group(1)
    if provider_status is None:
        match = re.search(
            r"\b(paid_plan_required|invalid[_ ]voice|quota[_ ](?:exceeded|limit))\b",
            error_text,
            re.I,
        )
        if match:
            provider_status = match.group(1)

    logger.error(
        "ElevenLabs TTS failure source={} http_status={} provider_status={} message={} exception={}",
        source,
        http_status or "unknown",
        provider_status or "unknown",
        message,
        str(exception) if exception else "none",
    )


def _verify_voice_tool_handlers(context: LLMContext) -> list[str]:
    direct_functions = getattr(context.tools, "direct_functions", ())
    handlers = {tool.name: tool.function for tool in direct_functions}
    expected_names = [tool.__name__ for tool in ALL_TOOLS]
    if len(set(expected_names)) != len(expected_names):
        raise RuntimeError("Voice tools in ALL_TOOLS must have unique names")
    missing = [tool.__name__ for tool in ALL_TOOLS if handlers.get(tool.__name__) is not tool]
    if missing:
        raise RuntimeError(
            "Voice tools are missing registered handlers in LLMContext: "
            + ", ".join(missing)
        )
    return expected_names


def _start_call_session() -> int:
    with SessionLocal() as session:
        call_session = CallSession(
            started_at=datetime.now(timezone.utc),
            status=CallSessionStatus.active,
        )
        session.add(call_session)
        session.commit()
        session.refresh(call_session)
        return call_session.id


def _end_call_session(call_session_id: int) -> None:
    with SessionLocal() as session:
        call_session = session.get(CallSession, call_session_id)
        if call_session is None or call_session.status == CallSessionStatus.ended:
            return
        call_session.ended_at = datetime.now(timezone.utc)
        call_session.status = CallSessionStatus.ended
        session.commit()

# ── System prompt ──────────────────────────────────────────────────────

def _system_prompt() -> str:
    now = datetime.now(CLINIC_TZ)
    today = now.strftime("%A, %B %d, %Y")
    time_str = now.strftime("%I:%M %p")
    specialities = ", ".join(get_speciality_catalog()) or "None loaded"

    return f"""\
You are the voice receptionist for a multi-speciality medical clinic.
Today is {today}. The current time is {time_str} Asia/Kolkata (IST).

CAPABILITIES:
• Check doctor availability by name, speciality, or date.
• Exact DB specialities: {specialities}. Map what the caller says (cardiologist, heart doctor, kids doctor) to one of these names before calling the tool.
• Book an appointment for a patient.
• Cancel a patient's existing appointment.

RULES — follow these strictly:
1. IDENTITY: You handle appointments only. For medical questions, say:
   "I can only help with scheduling. Please consult a doctor for medical advice."
2. TURN STYLE: The caller has already been greeted. Do not greet them again.
    Ask only one question per turn and keep sentences short.
3. BOOKING FLOW: First ask which doctor or speciality they need. As soon as
    they answer, call check_doctor_availability with the information they gave;
    do not ask another question first. Offer no more than 3 available slots.
    Ask them to choose one. After they choose, say the doctor, date, and time
    aloud and ask them to confirm that exact slot. Only after they confirm it,
    ask for their 10-digit Indian mobile number. Read the number back one digit
    at a time and ask if that number is correct. Wait for a new, clear yes
    after the readback. The earlier yes that confirmed the slot does not confirm
    the phone number. Only then call book_appointment with phone_confirmed=true.
    State the booking result based on the tool response.
4. CANCELLATION FLOW: Ask for their 10-digit Indian mobile number. Read it
    back one digit at a time and ask if that number is correct. Wait for a new,
    clear yes after the readback. Only then call cancel_appointment with
    phone_confirmed=true.
5. ONE APPOINTMENT: Each phone can have only one active appointment. If the
    caller already has one, explain this briefly and offer cancellation.
6. PAST SLOTS: Never attempt to book a slot in the past.
7. POLITENESS: Be warm, professional, and helpful at all times.
8. ERRORS: If a tool returns an error, explain the issue simply and suggest
    what the caller can do next.
9. NO HALLUCINATION: Only provide information returned by your tools. Never
    invent doctor names, times, or appointment IDs.
10. BOOKING CLAIMS: Never say an appointment is booked unless the booking tool
     returned ok=true. If it returns ok=false, clearly say it was not booked.
"""


# ── Pipeline builder ───────────────────────────────────────────────────

async def run_bot(webrtc_connection) -> None:
    """Create and run the full voice pipeline for one WebRTC session."""
    settings = get_settings()
    settings.validate_voice_settings()
    configure_speciality_catalog(get_speciality_catalog())

    # -- Transport --
    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )

    # -- STT (ElevenLabs Realtime) --
    stt = ElevenLabsRealtimeSTTService(
        api_key=settings.elevenlabs_api_key,
        commit_strategy=CommitStrategy.VAD,
        settings=ElevenLabsRealtimeSTTService.Settings(
            language=Language.EN,
            vad_silence_threshold_secs=0.6,
        ),
    )

    # -- LLM (Gemini) --
    llm = GoogleLLMService(
        api_key=settings.google_api_key,
        settings=GoogleLLMService.Settings(
            model=settings.gemini_model,
        ),
    )

    # -- TTS (ElevenLabs) --
    tts = ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key,
        settings=ElevenLabsTTSService.Settings(
            voice=settings.elevenlabs_voice_id,
            model=settings.elevenlabs_tts_model,
        ),
    )

    # -- Context with tools + system prompt --
    context = LLMContext(
        messages=[{"role": "system", "content": _system_prompt()}],
        tools=ALL_TOOLS,
    )
    logger.info("LLM direct-function tool handlers ready: {}", _verify_voice_tool_handlers(context))

    # -- Context aggregator pair (VAD lives here) --
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(min_volume=0.35)),
            user_turn_strategies=UserTurnStrategies(
                stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.6)],
            ),
        ),
    )

    # -- Pipeline --
    pipeline = Pipeline([
        transport.input(),
        stt,
        context_aggregator.user(),
        llm,
        tts,
        transport.output(),
        context_aggregator.assistant(),
    ])

    pipeline_log_observer = _PipelineLogObserver()
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True),
        enable_rtvi=True,
        rtvi_observer_params=RTVIObserverParams(
            user_input_enabled=True,
            bot_output_enabled=True,
        ),
        observers=[pipeline_log_observer],
    )
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    logger.info("Voice pipeline ready with RTVI enabled")

    # -- Events --
    call_session_id: int | None = None

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        nonlocal call_session_id
        logger.info("WebRTC client connected")
        if call_session_id is None:
            try:
                call_session_id = await asyncio.to_thread(_start_call_session)
            except Exception:
                logger.exception("Could not create call session")

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        logger.info("RTVI client ready; starting greeting turn")
        pipeline_log_observer.expect_greeting_audio()
        context.add_message(
            {
                "role": "developer",
                "content": "Greet the caller, welcome them to the clinic, and ask how you can help.",
            }
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        nonlocal call_session_id
        logger.info("WebRTC client disconnected")
        if call_session_id is not None:
            try:
                await asyncio.to_thread(_end_call_session, call_session_id)
            except Exception:
                logger.exception("Could not end call session")
            call_session_id = None
        await worker.cancel(reason="WebRTC client disconnected")
        await runner.cancel(reason="WebRTC client disconnected")

    @stt.event_handler("on_connection_error")
    async def on_stt_connection_error(service, error):
        logger.info("STT service error: {}", error)

    @tts.event_handler("on_connection_error")
    async def on_tts_connection_error(service, error):
        _log_tts_failure("connection", error)

    @llm.event_handler("on_completion_timeout")
    async def on_llm_completion_timeout(service):
        logger.info("LLM service error: completion timed out")

    @worker.event_handler("on_pipeline_error")
    async def on_pipeline_error(worker, frame: ErrorFrame):
        processor = getattr(frame, "processor", None)
        processor_name = getattr(processor, "name", "unknown")
        if processor is tts or "elevenlabsttsservice" in processor_name.lower():
            _log_tts_failure("ErrorFrame", frame.error, frame.exception)
            pipeline_log_observer.clear_greeting_audio()
        else:
            logger.error("Pipeline service error from {}: {}", processor_name, frame.error)

    # -- Run --
    await runner.run()
