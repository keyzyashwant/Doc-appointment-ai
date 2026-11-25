"""WebSocket /ws/events – broadcasts domain events to the frontend."""

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import event_bus

router = APIRouter()


@router.websocket("/ws/events")
async def events_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        async for event in event_bus.subscribe():
            await websocket.send_text(json.dumps(event.to_dict()))
    except WebSocketDisconnect:
        pass
