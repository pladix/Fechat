import asyncio
import json
import sys
import websockets

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.services.crypto_service import CryptoEngine

WS_URL = "ws://127.0.0.1:80/ws/chat"

async def recv_rpc_response(ws, rpc_id, key_hex=None):
    while True:
        raw = await ws.recv()
        raw_json = json.loads(raw)
        data = CryptoEngine.unseal_wire_packet(raw_json, key_hex)
        if isinstance(data, dict) and data.get("type") == "rpc_response" and data.get("rpc_id") == rpc_id:
            return data

async def recv_event(ws, event_type, signal_type=None, key_hex=None):
    while True:
        raw = await ws.recv()
        raw_json = json.loads(raw)
        data = CryptoEngine.unseal_wire_packet(raw_json, key_hex)
        if isinstance(data, dict) and data.get("type") == event_type:
            if signal_type is None or data.get("data", {}).get("signal_type") == signal_type:
                return data

async def test_voice_calling_signaling():
    print("🚀 [TEST] Iniciando Bateria de Testes de Sinalização de Chamadas de Voz WebRTC E2EE...")

    preauth_key = CryptoEngine.get_preauth_wire_key_hex()

    async with websockets.connect(WS_URL) as ws_caller, websockets.connect(WS_URL) as ws_callee:
        await ws_caller.send(json.dumps(CryptoEngine.seal_wire_packet({
            "type": "rpc_request",
            "rpc_id": "login_caller",
            "action": "auth_login",
            "payload": {
                "login": "admin",
                "password": "admin123456"
            }
        }, preauth_key)))
        res_caller = await recv_rpc_response(ws_caller, "login_caller", preauth_key)
        assert res_caller.get("success") is True, f"Falha no login do caller: {res_caller}"
        user_admin = res_caller["data"]["user"]
        caller_key = CryptoEngine.derive_session_wire_key_hex(res_caller["data"]["access_token"])

        await ws_callee.send(json.dumps(CryptoEngine.seal_wire_packet({
            "type": "rpc_request",
            "rpc_id": "login_callee",
            "action": "auth_login",
            "payload": {
                "login": "voice_tester_callee",
                "password": "UserPassword123!"
            }
        }, preauth_key)))
        res_callee = await recv_rpc_response(ws_callee, "login_callee", preauth_key)
        if not res_callee.get("success"):
            await ws_callee.send(json.dumps(CryptoEngine.seal_wire_packet({
                "type": "rpc_request",
                "rpc_id": "reg_callee",
                "action": "auth_register",
                "payload": {
                    "username": "voice_tester_callee",
                    "full_name": "Testador Callee",
                    "email": "callee@fechat.com",
                    "password": "UserPassword123!"
                }
            }, preauth_key)))
            res_callee = await recv_rpc_response(ws_callee, "reg_callee", preauth_key)

        assert res_callee.get("success") is True, f"Falha no login do callee: {res_callee}"
        user_callee = res_callee["data"]["user"]
        callee_key = CryptoEngine.derive_session_wire_key_hex(res_callee["data"]["access_token"])

        print(f"✅ 1. Caller ({user_admin['username']} - ID {user_admin['id']}) e Callee ({user_callee['username']} - ID {user_callee['id']}) autenticados!")
        print("✅ 2. Túneis WebSocket do Caller e Callee conectados e ativos!")

        rpc_initiate = {
            "type": "rpc_request",
            "rpc_id": "rpc_call_init_001",
            "action": "call_signal",
            "payload": {
                "signal_type": "initiate",
                "target_user_id": user_callee["id"],
                "chat_id": 999,
                "sdp": {"type": "offer", "sdp": "v=0\r\no=- 485729 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\nm=audio 5004 RTP/SAVPF 111\r\n"}
            }
        }
        await ws_caller.send(json.dumps(CryptoEngine.seal_wire_packet(rpc_initiate, caller_key)))

        caller_rpc_resp = await recv_rpc_response(ws_caller, "rpc_call_init_001", caller_key)
        assert caller_rpc_resp.get("success") is True, f"Falha na entrega da chamada: {caller_rpc_resp}"
        assert caller_rpc_resp["data"]["status"] == "delivered"
        print("✅ 3. Caller emitiu sinal de 'initiate' com SDP Offer via RPC!")

        callee_event = await recv_event(ws_callee, "call_signal", signal_type="initiate", key_hex=callee_key)
        assert callee_event["data"]["sender_id"] == user_admin["id"]
        print(f"✅ 4. Callee recebeu chamada de '{callee_event['data']['sender_name']}' com oferta SDP!")

        rpc_accept = {
            "type": "rpc_request",
            "rpc_id": "rpc_call_accept_001",
            "action": "call_signal",
            "payload": {
                "signal_type": "accept",
                "target_user_id": user_admin["id"],
                "chat_id": 999,
                "sdp": {"type": "answer", "sdp": "v=0\r\no=- 982731 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\nm=audio 5004 RTP/SAVPF 111\r\n"}
            }
        }
        await ws_callee.send(json.dumps(CryptoEngine.seal_wire_packet(rpc_accept, callee_key)))
        callee_rpc_resp = await recv_rpc_response(ws_callee, "rpc_call_accept_001", callee_key)
        assert callee_rpc_resp.get("success") is True

        caller_event = await recv_event(ws_caller, "call_signal", signal_type="accept", key_hex=caller_key)
        assert caller_event["data"]["signal_type"] == "accept"
        print("✅ 5. Caller recebeu confirmação de aceitação da chamada (SDP Answer)!")

        rpc_candidate = {
            "type": "rpc_request",
            "rpc_id": "rpc_call_ice_001",
            "action": "call_signal",
            "payload": {
                "signal_type": "candidate",
                "target_user_id": user_callee["id"],
                "chat_id": 999,
                "candidate": {"candidate": "candidate:1 1 UDP 2122252543 192.168.1.100 50000 typ host", "sdpMid": "0", "sdpMLineIndex": 0}
            }
        }
        await ws_caller.send(json.dumps(CryptoEngine.seal_wire_packet(rpc_candidate, caller_key)))

        callee_ice_event = await recv_event(ws_callee, "call_signal", signal_type="candidate", key_hex=callee_key)
        assert callee_ice_event["data"]["signal_type"] == "candidate"
        print("✅ 6. Candidato ICE transmitido e recebido com sucesso!")

        rpc_hangup = {
            "type": "rpc_request",
            "rpc_id": "rpc_call_hangup_001",
            "action": "call_signal",
            "payload": {
                "signal_type": "hangup",
                "target_user_id": user_callee["id"],
                "chat_id": 999,
                "duration": 42
            }
        }
        await ws_caller.send(json.dumps(CryptoEngine.seal_wire_packet(rpc_hangup, caller_key)))

        callee_hangup_event = await recv_event(ws_callee, "call_signal", signal_type="hangup", key_hex=callee_key)
        assert callee_hangup_event["data"]["signal_type"] == "hangup"
        assert callee_hangup_event["data"]["duration"] == 42
        print("✅ 7. Chamada finalizada com registro de 42 segundos de duração!")

    print("\n🎉 [SUCESSO TOTAL] Sistema de Sinalização de Chamadas de Voz WebRTC E2EE 100% Funcional e Validado!")

    print("\n🎉 [SUCESSO TOTAL] Sistema de Sinalização de Chamadas de Voz WebRTC E2EE 100% Funcional e Validado!")

if __name__ == "__main__":
    asyncio.run(test_voice_calling_signaling())
