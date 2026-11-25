"""WebRTC signaling route — POST /api/offer + PATCH /api/offer."""

from fastapi import APIRouter, BackgroundTasks
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from app.voice.pipeline import run_bot

router = APIRouter(tags=["voice"])

_handler = SmallWebRTCRequestHandler()


@router.post("/api/offer")
async def offer(request: SmallWebRTCRequest, background_tasks: BackgroundTasks):
    """Exchange SDP offer/answer and spin up a voice pipeline."""

    async def _on_connection(webrtc_connection):
        background_tasks.add_task(run_bot, webrtc_connection)

    return await _handler.handle_web_request(
        request=request,
        webrtc_connection_callback=_on_connection,
    )


@router.patch("/api/offer")
async def ice_candidate(request: SmallWebRTCPatchRequest):
    """Handle trickle ICE candidates from the browser."""
    await _handler.handle_patch_request(request)
    return {"status": "ok"}
