import asyncio
import json
import websockets
from app.services.crypto_service import CryptoEngine

WS_URL = "ws://127.0.0.1:80/ws/chat"

async def test_invalid_login():
    preauth_key = CryptoEngine.get_preauth_wire_key_hex()

    async with websockets.connect(WS_URL) as ws:
        login_req = {
            "type": "rpc_request",
            "rpc_id": "test_invalid_plain",
            "action": "auth_login",
            "payload": {
                "login": "usuario_teste@exemplo.com",
                "password": "WrongPassword999!"
            }
        }
        await ws.send(json.dumps(login_req))
        raw = await ws.recv()
        resp = json.loads(raw)
        print("Invalid password plain response:", resp)
        assert resp["success"] is False
        assert "Credenciais inválidas" in resp["error"]

    async with websockets.connect(WS_URL) as ws:
        login_req = {
            "type": "rpc_request",
            "rpc_id": "test_invalid_sealed",
            "action": "auth_login",
            "payload": {
                "login": "usuario_teste@exemplo.com",
                "password": "WrongPassword999!"
            }
        }
        sealed = CryptoEngine.seal_wire_packet(login_req, preauth_key)
        await ws.send(json.dumps(sealed))
        raw = await ws.recv()
        resp = CryptoEngine.unseal_wire_packet(json.loads(raw), preauth_key)
        print("Invalid password sealed response:", resp)
        assert resp["success"] is False
        assert "Credenciais inválidas" in resp["error"]

    print("OK - Resposta de erro imediata validada com sucesso!")

if __name__ == "__main__":
    asyncio.run(test_invalid_login())
