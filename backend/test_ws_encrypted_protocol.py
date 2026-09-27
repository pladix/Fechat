import sys
import os
import asyncio
import json
import websockets
from app.services.crypto_service import CryptoEngine

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

WS_URL = "ws://127.0.0.1:80/ws/chat"

async def recv_unsealed(ws, key_hex):
    raw = await ws.recv()
    raw_json = json.loads(raw)
    assert "_shield" in raw_json and "c" in raw_json and "iv" in raw_json, f"Frame recebido não está cifrado: {raw_json}"
    return CryptoEngine.unseal_wire_packet(raw_json, key_hex), raw

async def recv_unsealed_rpc(ws, key_hex, rpc_id):
    while True:
        data, raw = await recv_unsealed(ws, key_hex)
        if data.get("type") == "rpc_response" and data.get("rpc_id") == rpc_id:
            return data, raw

async def test_wsep_encrypted_websocket():
    print("🚀 [TEST] Iniciando Bateria de Testes do Protocolo WSEP (WebSocket Secure Encrypted Protocol)...")

    preauth_key = CryptoEngine.get_preauth_wire_key_hex()

    async with websockets.connect(WS_URL) as ws_caller, websockets.connect(WS_URL) as ws_callee:
        login_req = {
            "type": "rpc_request",
            "rpc_id": "login_caller",
            "action": "auth_login",
            "payload": {
                "login": "admin",
                "password": "admin123456"
            }
        }
        sealed_login = CryptoEngine.seal_wire_packet(login_req, preauth_key)
        assert "_shield" in sealed_login, "Payload de login deve estar encapsulado em AES-256-GCM"
        await ws_caller.send(json.dumps(sealed_login))

        res_caller, raw_login_resp = await recv_unsealed(ws_caller, preauth_key)
        assert res_caller.get("success") is True, f"Falha no login do caller: {res_caller}"
        assert "admin123456" not in raw_login_resp, "A senha nunca deve trafegar em texto claro na rede!"

        caller_token = res_caller["data"]["access_token"]
        caller_session_key = CryptoEngine.derive_session_wire_key_hex(caller_token)
        print("✅ 1. Login do Admin executado com credenciais 100% cifradas no túnel WSEP!")

        unique_user = f"wsep_user_{int(asyncio.get_event_loop().time())}"
        reg_req = {
            "type": "rpc_request",
            "rpc_id": "reg_callee",
            "action": "auth_register",
            "payload": {
                "full_name": "Usuário Teste WSEP",
                "username": unique_user,
                "email": f"{unique_user}@fechat.test",
                "password": "Password123!"
            }
        }
        await ws_callee.send(json.dumps(CryptoEngine.seal_wire_packet(reg_req, preauth_key)))
        res_callee, raw_callee_resp = await recv_unsealed(ws_callee, preauth_key)
        assert res_callee.get("success") is True, f"Falha no registro do callee: {res_callee}"
        assert "Password123!" not in raw_callee_resp, "Senha não pode estar presente no payload legível!"

        callee_token = res_callee["data"]["access_token"]
        callee_session_key = CryptoEngine.derive_session_wire_key_hex(callee_token)
        print("✅ 2. Callee autenticado com chave de túnel de sessão WSEP exclusiva!")

        rpc_me = {
            "type": "rpc_request",
            "rpc_id": "me_test",
            "action": "auth_me",
            "payload": {}
        }
        await ws_caller.send(json.dumps(CryptoEngine.seal_wire_packet(rpc_me, caller_session_key)))
        res_me, raw_me_resp = await recv_unsealed_rpc(ws_caller, caller_session_key, "me_test")
        assert res_me["success"] is True
        assert res_me["data"]["user"]["username"] == "admin"
        assert "admin@fechat.local" not in raw_me_resp, "Dados do perfil devem estar 100% cifrados no frame!"
        print("✅ 3. RPC auth_me verificado: zero plaintext em trânsito no WebSocket!")

        rpc_chats = {
            "type": "rpc_request",
            "rpc_id": "chats_test",
            "action": "get_chats",
            "payload": {}
        }
        await ws_caller.send(json.dumps(CryptoEngine.seal_wire_packet(rpc_chats, caller_session_key)))
        res_chats, raw_chats = await recv_unsealed_rpc(ws_caller, caller_session_key, "chats_test")
        assert res_chats["success"] is True
        assert "chats" in res_chats["data"]
        print(f"✅ 4. RPC get_chats retornado com {len(res_chats['data']['chats'])} conversas cifradas no túnel!")

        await ws_caller.send(json.dumps(CryptoEngine.seal_wire_packet({"type": "ping"}, caller_session_key)))
        pong_resp, _ = await recv_unsealed(ws_caller, caller_session_key)
        assert pong_resp["type"] == "pong"
        print("✅ 5. Ping/Pong em tempo real trafega 100% cifrado!")

    print("\n🎉 [SUCESSO TOTAL] Protocolo WSEP (WebSocket Secure Encrypted Protocol) 100% Funcional e Blindado!")

if __name__ == "__main__":
    asyncio.run(test_wsep_encrypted_websocket())
