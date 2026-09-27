import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import json
import websockets
import random

WS_URL = "ws://127.0.0.1/ws/chat"

async def test_report_immunity_and_flexible_payload():
    print("=== TESTE DE IMUNIDADE DE DENÚNCIA (BOTS, ADMINS, VERIFICADOS) E PAYLOAD SEGURO ===")

    rnd = random.randint(100000, 999999)
    user_a = f"reporter_{rnd}"
    user_target = f"target_{rnd}"

    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "reg_a", "action": "auth_register",
            "payload": {"full_name": "Denunciante Teste", "username": user_a, "email": f"{user_a}@fechat.crypto", "password": "SenhaSegura123!"}
        }))
        res_a = json.loads(await ws.recv())
        token_a = res_a["data"]["access_token"]
        id_a = res_a["data"]["user"]["id"]

        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "reg_target", "action": "auth_register",
            "payload": {"full_name": "Usuário Alvo Comum", "username": user_target, "email": f"{user_target}@fechat.crypto", "password": "SenhaSegura123!"}
        }))
        res_t = json.loads(await ws.recv())
        id_target = res_t["data"]["user"]["id"]

    async with websockets.connect(f"{WS_URL}?token={token_a}") as ws:
        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "rep_dict", "action": "submit_report",
            "payload": {
                "category": {
                    "reported_user_id": id_target,
                    "category": "harassment",
                    "reason": "Comportamento inapropriado em teste",
                    "plaintext_evidence": "Texto de prova descriptografado"
                }
            }
        }))
        res_dict = json.loads(await ws.recv())
        assert res_dict["success"] is True, f"Falha no payload dict: {res_dict}"
        print("✅ 1. Denúncia com payload flexível/aninhado processada com sucesso sem erro de binding do SQLite!")

        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "get_chats", "action": "get_chats"
        }))
        res_chats = json.loads(await ws.recv())
        bot_chat = next((c for c in res_chats["data"]["chats"] if c.get("target_user") and c["target_user"]["is_bot"]), None)
        assert bot_chat is not None, "Chat com Bot Oficial não encontrado"
        bot_id = bot_chat["target_user"]["id"]

        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "rep_bot", "action": "submit_report",
            "payload": {
                "reported_user_id": bot_id,
                "category": "csam",
                "reason": "Tentativa indevida de denunciar o bot oficial"
            }
        }))
        res_bot = json.loads(await ws.recv())
        assert res_bot["success"] is False
        assert "Contatos oficiais, bots e administradores da plataforma não podem ser denunciados" in res_bot["error"]
        print(f"✅ 2. Imunidade do Bot Oficial confirmada com sucesso: '{res_bot['error']}'")

        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "rep_bot_chat", "action": "submit_report",
            "payload": {
                "chat_id": bot_chat["id"],
                "category": "fraud",
                "reason": "Tentativa via chat_id"
            }
        }))
        res_bot_chat = json.loads(await ws.recv())
        assert res_bot_chat["success"] is False
        assert "Contatos oficiais, bots e administradores da plataforma não podem ser denunciados" in res_bot_chat["error"]
        print(f"✅ 3. Imunidade via Chat ID com Bot Oficial confirmada com sucesso: '{res_bot_chat['error']}'")

        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "rep_admin", "action": "submit_report",
            "payload": {
                "reported_user_id": 1,
                "category": "cybercrime",
                "reason": "Tentativa de denunciar admin do sistema"
            }
        }))
        res_admin = json.loads(await ws.recv())
        assert res_admin["success"] is False
        assert "Contatos oficiais, bots e administradores da plataforma não podem ser denunciados" in res_admin["error"]
        print(f"✅ 4. Imunidade do Administrador confirmada com sucesso: '{res_admin['error']}'")

    print("\n🎉 TODOS OS TESTES DE IMUNIDADE DE DENÚNCIA E COMPATIBILIDADE DE PAYLOAD FORAM APROVADOS COM 100% DE SUCESSO!")

if __name__ == "__main__":
    asyncio.run(test_report_immunity_and_flexible_payload())
