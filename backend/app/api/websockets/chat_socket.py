import json
from typing import Optional, Set
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.chat import ChatMember
from app.models.user import User
from app.services.auth_service import decode_access_token
from app.services.ws_manager import ws_manager
from app.api.websockets.ws_rpc_handler import handle_ws_rpc

def parse_device_info(ua: str) -> str:
    if not ua:
        return "Dispositivo Web Padrão"
    ua_lower = ua.lower()

    os_name = "Desktop"
    if "windows" in ua_lower:
        os_name = "Windows"
    elif "android" in ua_lower:
        os_name = "Android"
    elif "iphone" in ua_lower or "ipad" in ua_lower or "ios" in ua_lower:
        os_name = "iOS"
    elif "macintosh" in ua_lower or "mac os" in ua_lower:
        os_name = "macOS"
    elif "linux" in ua_lower:
        os_name = "Linux"

    browser = "Navegador Web"
    if "edg" in ua_lower:
        browser = "Edge"
    elif "chrome" in ua_lower or "crios" in ua_lower:
        browser = "Chrome"
    elif "firefox" in ua_lower or "fxios" in ua_lower:
        browser = "Firefox"
    elif "safari" in ua_lower and "chrome" not in ua_lower:
        browser = "Safari"
    elif "opera" in ua_lower or "opr" in ua_lower:
        browser = "Opera"

    dev_type = "Celular / Mobile" if any(k in ua_lower for k in ["mobile", "android", "iphone", "ipad"]) else "Computador / Desktop"
    return f"{os_name} • {dev_type} ({browser})"

async def update_user_last_seen(uid: int, client_ip: Optional[str] = None, user_agent: Optional[str] = None):
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, uid)
            if user:
                user.last_seen = datetime.utcnow()
                if client_ip:
                    user.last_ip = client_ip
                if user_agent:
                    user.user_agent = user_agent[:250]
                    user.device_info = parse_device_info(user_agent)
                await db.commit()
    except Exception:
        pass

from typing import Optional
from app.services.crypto_service import CryptoEngine

router = APIRouter(tags=["WebSockets em Tempo Real"])

@router.websocket("/ws/chat")
async def chat_websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    user_id: Optional[int] = None
    client_ip = websocket.client.host if websocket.client else "127.0.0.1"
    user_agent = websocket.headers.get("user-agent", "")
    session_key_hex = CryptoEngine.derive_session_wire_key_hex(token)

    if token:
        try:
            payload = decode_access_token(token)
            user_id = int(payload.get("sub"))
        except Exception:
            pass

    if user_id:
        await ws_manager.connect(user_id, websocket, session_key_hex=session_key_hex)
        await update_user_last_seen(user_id, client_ip, user_agent)
    else:
        await websocket.accept()
        ws_manager.set_socket_key(websocket, session_key_hex)

    try:
        while True:
            data_text = await websocket.receive_text()
            try:
                raw_data = json.loads(data_text)
                is_sealed = isinstance(raw_data, dict) and raw_data.get("_shield") == "aes256gcm"

                ws_manager.socket_sealed[websocket] = is_sealed

                msg_data = CryptoEngine.unseal_wire_packet(raw_data, session_key_hex) if is_sealed else raw_data
                if not isinstance(msg_data, dict):
                    continue

                msg_type = msg_data.get("type")

                if msg_type == "rpc_request":
                    rpc_id = msg_data.get("rpc_id")
                    action = msg_data.get("action")
                    payload_data = msg_data.get("payload", {})

                    try:
                        result, new_user_id = await handle_ws_rpc(user_id, action, payload_data, client_ip=client_ip, user_agent=user_agent)

                        if new_user_id:
                            if user_id and user_id != new_user_id:
                                if user_id in ws_manager.active_connections:
                                    ws_manager.active_connections[user_id].discard(websocket)
                            user_id = new_user_id
                            if user_id not in ws_manager.active_connections:
                                ws_manager.active_connections[user_id] = set()
                                await ws_manager.broadcast_presence(user_id, is_online=True)
                            ws_manager.active_connections[user_id].add(websocket)
                            await update_user_last_seen(user_id, client_ip, user_agent)

                        resp_payload = {
                            "type": "rpc_response",
                            "rpc_id": rpc_id,
                            "success": True,
                            "data": result,
                            "error": None
                        }

                        if is_sealed:
                            sealed_resp = CryptoEngine.seal_wire_packet(resp_payload, session_key_hex)
                            await websocket.send_json(sealed_resp)
                        else:
                            await websocket.send_json(resp_payload)

                        if isinstance(result, dict) and "access_token" in result:
                            session_key_hex = CryptoEngine.derive_session_wire_key_hex(result["access_token"])
                            ws_manager.set_socket_key(websocket, session_key_hex)
                    except Exception as err:
                        err_payload = {
                            "type": "rpc_response",
                            "rpc_id": rpc_id,
                            "success": False,
                            "data": None,
                            "error": str(err)
                        }
                        if is_sealed:
                            sealed_err = CryptoEngine.seal_wire_packet(err_payload, session_key_hex)
                            await websocket.send_json(sealed_err)
                        else:
                            await websocket.send_json(err_payload)

                elif msg_type == "typing" and user_id:
                    chat_id = msg_data.get("chat_id")
                    is_typing = bool(msg_data.get("is_typing", True))

                    if chat_id:
                        async with AsyncSessionLocal() as db:
                            q = select(ChatMember.user_id).where(ChatMember.chat_id == chat_id)
                            res = await db.execute(q)
                            member_ids = res.scalars().all()
                            await ws_manager.broadcast_typing(
                                chat_id=chat_id,
                                user_id=user_id,
                                is_typing=is_typing,
                                member_user_ids=member_ids
                            )

                elif msg_type == "ping":
                    if is_sealed:
                        sealed_pong = CryptoEngine.seal_wire_packet({"type": "pong"}, session_key_hex)
                        await websocket.send_json(sealed_pong)
                    else:
                        await websocket.send_json({"type": "pong"})

            except json.JSONDecodeError:
                pass

    except (WebSocketDisconnect, Exception):
        if user_id:
            await ws_manager.disconnect(user_id, websocket)
            await update_user_last_seen(user_id, client_ip, user_agent)
        else:
            ws_manager.socket_keys.pop(websocket, None)
