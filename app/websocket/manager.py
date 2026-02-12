from fastapi import WebSocket
from typing import Dict, List
import json
import asyncio


class ConnectionManager:
    """Manages WebSocket connections for real-time agent status updates."""

    def __init__(self):
        # Map of task_id -> list of connected websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Map of user_id -> list of connected websockets (for general updates)
        self.user_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, task_id: str = None, user_id: str = None):
        await websocket.accept()
        if task_id:
            if task_id not in self.active_connections:
                self.active_connections[task_id] = []
            self.active_connections[task_id].append(websocket)
        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = []
            self.user_connections[user_id].append(websocket)

    def disconnect(self, websocket: WebSocket, task_id: str = None, user_id: str = None):
        if task_id and task_id in self.active_connections:
            self.active_connections[task_id] = [
                ws for ws in self.active_connections[task_id] if ws != websocket
            ]
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
        if user_id and user_id in self.user_connections:
            self.user_connections[user_id] = [
                ws for ws in self.user_connections[user_id] if ws != websocket
            ]
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

    async def send_task_update(self, task_id: str, data: dict):
        """Send update to all clients watching a specific task."""
        if task_id in self.active_connections:
            message = json.dumps(data)
            dead_connections = []
            for ws in self.active_connections[task_id]:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead_connections.append(ws)
            for ws in dead_connections:
                self.active_connections[task_id].remove(ws)

    async def send_user_update(self, user_id: str, data: dict):
        """Send update to all connections for a user."""
        if user_id in self.user_connections:
            message = json.dumps(data)
            dead_connections = []
            for ws in self.user_connections[user_id]:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead_connections.append(ws)
            for ws in dead_connections:
                self.user_connections[user_id].remove(ws)

    async def broadcast(self, data: dict):
        """Broadcast to all connected clients."""
        message = json.dumps(data)
        for connections in self.user_connections.values():
            for ws in connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    pass


ws_manager = ConnectionManager()
