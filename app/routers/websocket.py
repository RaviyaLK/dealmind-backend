from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.websocket.manager import ws_manager
from app.agents.orchestrator import task_store
import json

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/agent/{task_id}")
async def agent_status_websocket(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time agent task updates.

    Connect to receive live updates as Quinn processes a deal through
    qualification, proposal generation, or monitoring flows.
    """
    await ws_manager.connect(websocket, task_id=task_id)
    try:
        # Send current status if task exists
        if task_id in task_store:
            await websocket.send_text(json.dumps(task_store[task_id]))

        # Keep connection alive and listen for client messages
        while True:
            data = await websocket.receive_text()
            # Client can send "ping" to keep alive
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, task_id=task_id)


@router.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket, user_id: str = Query(default="")):
    """WebSocket endpoint for dashboard real-time updates.

    Receives notifications about new alerts, deal status changes,
    and agent task completions.
    """
    await ws_manager.connect(websocket, user_id=user_id or "anonymous")
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, user_id=user_id or "anonymous")
