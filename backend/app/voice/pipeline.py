"""Voice pipeline – SmallWebRTC + Silero VAD + ElevenLabs STT/TTS + Gemini.

This module exposes ``run_bot(webrtc_connection)`` which is called once per
WebRTC session from the /api/offer route.
"""
import asyncio
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
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.call_session import CallSession
from app.models.enums import CallSessionStatus
from app.voice.tools import ALL_TOOLS

CLINIC_TZ = ZoneInfo("Asia/Kolkata")


class _PipelineLogObserver(BaseObserver):
    def __init__(self) -> None:
        super().__init__(observe_every_push=False)

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
        elif isinstance(frame, TTSStoppedFrame):
            logger.info("TTS stopped")


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

    return f"""\
You are the voice receptionist for a multi-speciality medical clinic.
Today is {today}. The current time is {time_str} Asia/Kolkata (IST).

CAPABILITIES:
• Check doctor availability by name, speciality, or date.
• Book an appointment for a patient.
• Cancel a patient's existing appointment.

RULES — follow these strictly:
1. IDENTITY: You handle appointments only. For medical questions, say:
   "I can only help with scheduling. Please consult a doctor for medical advice."
2. PHONE VERIFICATION: Before booking or cancelling, ask for the caller's
    10-digit Indian mobile number. Read each digit aloud individually, then ask
    for verbal confirmation. Only then call the tool with phone_confirmed=true.
3. ONE APPOINTMENT: Each phone can have only one active appointment. If the patient
   already has one, let them know and offer to cancel first.
4. SLOT CONFIRMATION: After finding slots, clearly state the doctor name, date,
   and time before booking. Get the patient's confirmation.
5. PAST SLOTS: Never attempt to book a slot in the past.
6. CONCISENESS: Use short spoken sentences. Avoid long lists and offer at most
    3 available slots.
7. POLITENESS: Be warm, professional, and helpful at all times.
8. ERRORS: If a tool returns an error, explain the issue to the patient in
   simple language and suggest what they can do (e.g. pick another slot).
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
            voice="b5RPB35vTODb3BEmR3Fc",   # Serein
            model="eleven_turbo_v2_5",      # from eleven_turbo_v2
        ),
    )

    # -- Context with tools + system prompt --
    context = LLMContext(
        messages=[{"role": "system", "content": _system_prompt()}],
        tools=ALL_TOOLS,
    )

    # -- Context aggregator pair (VAD lives here) --
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams())
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

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True),
        enable_rtvi=True,
        rtvi_observer_params=RTVIObserverParams(
            user_input_enabled=True,
            bot_output_enabled=True,
        ),
        observers=[_PipelineLogObserver()],
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
        await runner.cancel()

    @stt.event_handler("on_connection_error")
    async def on_stt_connection_error(service, error):
        logger.info("STT service error: {}", error)

    @tts.event_handler("on_connection_error")
    async def on_tts_connection_error(service, error):
        logger.info("TTS service error: {}", error)

    @llm.event_handler("on_completion_timeout")
    async def on_llm_completion_timeout(service):
        logger.info("LLM service error: completion timed out")

    @worker.event_handler("on_pipeline_error")
    async def on_pipeline_error(worker, frame: ErrorFrame):
        processor = getattr(frame, "processor", None)
        logger.info(
            "Pipeline service error from {}: {}",
            getattr(processor, "name", "unknown"),
            frame.error,
        )

    # -- Run --
    await runner.run()
