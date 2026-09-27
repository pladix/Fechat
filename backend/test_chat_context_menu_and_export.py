import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import json
import websockets
import random
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.chat import Chat, ChatMember
from app.models.message import Message
from app.models.contact import Contact

WS_URL = "ws://127.0.0.1/ws/chat"

async def test_chat_context_menu_actions():
    print("=== TESTE DE MENU DE CONTEXTO (FIXAR, SILENCIAR, ARQUIVAR, EXPORTAR JSON E APAGAR) ===")

    rnd = random.randint(100000, 999999)
    user_a = f"usera_{rnd}"
    user_b = f"userb_{rnd}"

    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "reg_a", "action": "auth_register",
            "payload": {"full_name": "Usuário Alpha", "username": user_a, "email": f"{user_a}@fechat.crypto", "password": "SenhaSegura123!"}
        }))
        res_a = json.loads(await ws.recv())
        token_a = res_a["data"]["access_token"]
        id_a = res_a["data"]["user"]["id"]

        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "reg_b", "action": "auth_register",
            "payload": {"full_name": "Usuário Beta", "username": user_b, "email": f"{user_b}@fechat.crypto", "password": "SenhaSegura123!"}
        }))
        res_b = json.loads(await ws.recv())
        token_b = res_b["data"]["access_token"]
        id_b = res_b["data"]["user"]["id"]

    async with websockets.connect(f"{WS_URL}?token={token_a}") as ws:
        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "create_chat", "action": "create_direct_chat",
            "payload": {"target_user_id": id_b}
        }))
        res_chat = json.loads(await ws.recv())
        assert res_chat["success"] is True
        chat_id = res_chat["data"]["chat"]["id"]
        aes_key = res_chat["data"]["chat"]["aes_channel_key"]
        print(f"✅ 1. Conversa criada com sucesso (ID: {chat_id})")

        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "send_msg", "action": "send_message",
            "payload": {
                "chat_id": chat_id,
                "ciphertext": "cipher_export_sample",
                "iv": "iv_sample",
                "tag": "tag_sample",
                "message_type": "text"
            }
        }))
        res_msg = json.loads(await ws.recv())
        assert res_msg["success"] is True
        print("✅ 2. Mensagem enviada para teste de exportação.")

        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "pin_chat", "action": "toggle_pin_chat",
            "payload": {"chat_id": chat_id}
        }))
        res_pin = json.loads(await ws.recv())
        assert res_pin["success"] is True
        assert res_pin["data"]["is_pinned"] is True
        print(f"✅ 3. Conversa fixada com sucesso: is_pinned={res_pin['data']['is_pinned']}")

        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "mute_chat", "action": "toggle_mute_chat",
            "payload": {"chat_id": chat_id}
        }))
        res_mute = json.loads(await ws.recv())
        assert res_mute["success"] is True
        assert res_mute["data"]["is_muted"] is True
        print(f"✅ 4. Conversa silenciada com sucesso: is_muted={res_mute['data']['is_muted']}")

        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "archive_chat", "action": "toggle_archive_chat",
            "payload": {"chat_id": chat_id}
        }))
        res_arc = json.loads(await ws.recv())
        assert res_arc["success"] is True
        assert res_arc["data"]["is_archived"] is True
        print(f"✅ 5. Conversa arquivada com sucesso: is_archived={res_arc['data']['is_archived']}")

        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "export_chat", "action": "export_chat_data",
            "payload": {"chat_id": chat_id}
        }))
        res_exp = json.loads(await ws.recv())
        assert res_exp["success"] is True
        assert len(res_exp["data"]["messages"]) >= 1
        assert res_exp["data"]["chat"]["id"] == chat_id
        print(f"✅ 6. Dados exportados com sucesso! ({len(res_exp['data']['messages'])} mensagens extraídas para JSON)")

        await ws.send(json.dumps({
            "type": "rpc_request", "rpc_id": "del_chat", "action": "delete_chat",
            "payload": {"chat_id": chat_id}
        }))
        res_del = json.loads(await ws.recv())
        assert res_del["success"] is True
        print(f"✅ 7. Conversa apagada com sucesso (Status: {res_del['data']['status']})")

    print("\n🎉 TODOS OS TESTES DE MENU DE CONTEXTO E GERENCIAMENTO DE CHAT PASSARAM COM SUCESSO!")

if __name__ == "__main__":
    asyncio.run(test_chat_context_menu_actions())
