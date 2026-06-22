"""Phase 8.5 — WebSocket Streaming: دعم WebSocket للـ streaming."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    إدارة اتصالات WebSocket للـ streaming.
    """

    def __init__(self):
        self._connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        await websocket.accept()
        self._connections[client_id] = websocket
        logger.info("WebSocket connected: %s", client_id)

    def disconnect(self, client_id: str) -> None:
        self._connections.pop(client_id, None)
        logger.info("WebSocket disconnected: %s", client_id)

    async def send_json(self, client_id: str, data: Dict[str, Any]) -> bool:
        ws = self._connections.get(client_id)
        if ws:
            try:
                await ws.send_text(json.dumps(data, ensure_ascii=False))
                return True
            except Exception:
                self.disconnect(client_id)
        return False

    async def send_token(self, client_id: str, token: str, index: int) -> bool:
        return await self.send_json(client_id, {
            "type": "token",
            "data": token,
            "index": index,
        })

    async def send_done(self, client_id: str, metadata: Optional[Dict] = None) -> bool:
        return await self.send_json(client_id, {
            "type": "done",
            "metadata": metadata or {},
        })

    async def send_error(self, client_id: str, error: str) -> bool:
        return await self.send_json(client_id, {
            "type": "error",
            "error": error,
        })

    @property
    def active_connections(self) -> int:
        return len(self._connections)


# Singleton
ws_manager = WebSocketManager()


async def handle_ws_chat(websocket: WebSocket) -> None:
    """
    معالج WebSocket للـ chat streaming.

    Protocol:
    Client → {"message": "...", "session_id": "...", "language": "ar"}
    Server → {"type": "token", "data": "...", "index": N}
    Server → {"type": "done", "metadata": {...}}
    Server → {"type": "error", "error": "..."}
    """
    client_id = str(uuid.uuid4())
    await ws_manager.connect(websocket, client_id)

    try:
        while True:
            # استقبال طلب
            try:
                raw = await websocket.receive_text()
                data = json.loads(raw)
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await ws_manager.send_error(client_id, "Invalid JSON")
                continue

            message = data.get("message", "")
            session_id = data.get("session_id", str(uuid.uuid4()))
            language = data.get("language", "ar")

            if not message:
                await ws_manager.send_error(client_id, "Empty message")
                continue

            # تشغيل streaming inference
            try:
                from services.chat.chat_service import ChatRequest, get_chat_service

                chat_service = get_chat_service()
                request = ChatRequest(
                    message=message,
                    session_id=session_id,
                    language=language,
                    stream=True,
                    use_rag=False,
                )

                index = 0
                async for event in chat_service.stream_chat(request):
                    if event.event_type == "token":
                        sent = await ws_manager.send_token(client_id, event.data, index)
                        if not sent:
                            break
                        index += 1
                    elif event.event_type == "done":
                        await ws_manager.send_done(client_id, {
                            "chunks": index,
                            "session_id": session_id,
                        })
                        break
                    elif event.event_type == "error":
                        await ws_manager.send_error(client_id, event.data)
                        break

            except Exception as e:
                logger.error("WebSocket streaming error: %s", e)
                await ws_manager.send_error(client_id, str(e))

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected: %s", client_id)
    finally:
        ws_manager.disconnect(client_id)
