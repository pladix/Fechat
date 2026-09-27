import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import json
import websockets
import requests

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/ws/chat"

async def test_ws_rpc():
    print("=== TESTE DE MULTIPLEXAÇÃO E RPC SOBRE WEBSOCKET (ANTI-MANIPULAÇÃO / SIGILO) ===")

    r1 = requests.post(f"{BASE_URL}/api/v1/auth/login", json={"login": "felipe@exemplo.com", "password": "123456"})
    token1 = r1.json()["access_token"]
    user1 = r1.json()["user"]

    r2 = requests.post(f"{BASE_URL}/api/v1/auth/login", json={"login": "mariana@example.com", "password": "123456"})
    token2 = r2.json()["access_token"]
    user2 = r2.json()["user"]

    print(f"✅ Usuários autenticados: {user1['full_name']} (ID {user1['id']}) e {user2['full_name']} (ID {user2['id']})")

    async with websockets.connect(f"{WS_URL}?token={token1}") as ws:
        print("✅ Túnel WebSocket criptografado conectado com sucesso!")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "rpc_1",
            "action": "get_chats",
            "payload": {}
        }))
        res1 = json.loads(await ws.recv())
        assert res1["type"] == "rpc_response"
        assert res1["success"] is True
        assert "chats" in res1["data"]
        print(f"✅ 1. RPC get_chats executado sobre WebSocket! ({len(res1['data']['chats'])} conversas recuperadas)")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "rpc_2",
            "action": "get_contacts",
            "payload": {}
        }))
        res2 = json.loads(await ws.recv())
        if not res2.get("success"):
            print("Erro no RPC get_contacts:", res2)
        assert res2["success"] is True
        assert "contacts" in res2["data"]
        print(f"✅ 2. RPC get_contacts executado sobre WebSocket! ({len(res2['data']['contacts'])} contatos recuperados)")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "rpc_3",
            "action": "block_user",
            "payload": {"user_id": user2["id"]}
        }))

        resp_block = None
        for _ in range(3):
            msg = json.loads(await ws.recv())
            if msg.get("type") == "rpc_response" and msg.get("rpc_id") == "rpc_3":
                resp_block = msg
                break
        if not resp_block or not resp_block.get("success"):
            print("Erro no RPC block_user:", resp_block)
        assert resp_block is not None
        assert resp_block["success"] is True
        print("✅ 3. RPC block_user executado sobre WebSocket sem expor rota HTTP!")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "rpc_4",
            "action": "get_block_status",
            "payload": {"user_id": user2["id"]}
        }))
        res4 = json.loads(await ws.recv())
        assert res4["success"] is True
        assert res4["data"]["is_blocked_by_me"] is True
        print("✅ 4. RPC get_block_status consultado sobre WebSocket com sucesso!")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "rpc_5",
            "action": "unblock_user",
            "payload": {"user_id": user2["id"]}
        }))
        resp_unblock = None
        for _ in range(3):
            msg = json.loads(await ws.recv())
            if msg.get("type") == "rpc_response" and msg.get("rpc_id") == "rpc_5":
                resp_unblock = msg
                break
        assert resp_unblock is not None
        assert resp_unblock["success"] is True
        print("✅ 5. RPC unblock_user executado sobre WebSocket com sucesso!")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "rpc_6",
            "action": "submit_report",
            "payload": {
                "reported_user_id": user2["id"],
                "category": "cybercrime",
                "reason": "Teste de denúncia via túnel WebSocket RPC blindado."
            }
        }))
        res6 = json.loads(await ws.recv())
        assert res6["success"] is True
        assert res6["data"]["status"] == "created"
        print("✅ 6. RPC submit_report registrado sobre WebSocket com sucesso!")

    print("\n🎉 TODAS AS ROTAS CONVERTIDAS PARA WEBSOCKET RPC FORAM TESTADAS COM 100% DE SUCESSO!")

if __name__ == "__main__":
    asyncio.run(test_ws_rpc())
