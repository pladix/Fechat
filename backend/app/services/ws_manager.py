import json
from typing import Dict, Set, Optional, List
from fastapi import WebSocket
from app.services.crypto_service import CryptoEngine

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        self.socket_keys: Dict[WebSocket, str] = {}
        self.socket_sealed: Dict[WebSocket, bool] = {}
        self.chat_subscriptions: Dict[int, Set[int]] = {}

    async def connect(self, user_id: int, websocket: WebSocket, session_key_hex: Optional[str] = None):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
            await self.broadcast_presence(user_id, is_online=True)
        self.active_connections[user_id].add(websocket)
        self.socket_keys[websocket] = session_key_hex or CryptoEngine.get_preauth_wire_key_hex()
        self.socket_sealed[websocket] = True

    def set_socket_key(self, websocket: WebSocket, session_key_hex: str):
        self.socket_keys[websocket] = session_key_hex

    async def disconnect(self, user_id: int, websocket: WebSocket):
        self.socket_keys.pop(websocket, None)
        self.socket_sealed.pop(websocket, None)
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                await self.broadcast_presence(user_id, is_online=False)

    def is_user_online(self, user_id: int) -> bool:
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0

    async def send_personal_message(self, message: dict, user_id: int):
        if user_id in self.active_connections:
            dead_sockets = set()
            for ws in list(self.active_connections[user_id]):
                try:
                    is_sealed = self.socket_sealed.get(ws, True)
                    if is_sealed:
                        key_hex = self.socket_keys.get(ws) or CryptoEngine.get_preauth_wire_key_hex()
                        sealed = CryptoEngine.seal_wire_packet(message, key_hex)
                        await ws.send_json(sealed)
                    else:
                        await ws.send_json(message)
                except Exception:
                    dead_sockets.add(ws)
            for ws in dead_sockets:
                self.active_connections[user_id].discard(ws)
                self.socket_keys.pop(ws, None)
                self.socket_sealed.pop(ws, None)

    async def broadcast_to_user(self, user_id: int, message: dict):

        await self.send_personal_message(message, user_id)

    async def broadcast_to_chat(self, chat_id: int, message: dict, member_user_ids: List[int], exclude_user_id: Optional[int] = None):

        for user_id in member_user_ids:
            if exclude_user_id and user_id == exclude_user_id:
                continue
            await self.send_personal_message(message, user_id)

    async def broadcast_presence(self, user_id: int, is_online: bool):

        payload = {
            "type": "presence_update",
            "data": {
                "user_id": user_id,
                "is_online": is_online
            }
        }
        for uid in list(self.active_connections.keys()):
            if uid != user_id:
                await self.send_personal_message(payload, uid)

    async def broadcast_typing(self, chat_id: int, user_id: int, is_typing: bool, member_user_ids: List[int]):

        payload = {
            "type": "typing_indicator",
            "data": {
                "chat_id": chat_id,
                "user_id": user_id,
                "is_typing": is_typing
            }
        }
        await self.broadcast_to_chat(chat_id, payload, member_user_ids, exclude_user_id=user_id)

ws_manager = ConnectionManager()

