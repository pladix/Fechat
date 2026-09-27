import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import json
import websockets
import random

WS_URL = "ws://127.0.0.1:8000/ws/chat"

async def test_bot_and_features():
    print("=== TESTE DE BOT OFICIAL VERIFICADO, BOAS-VINDAS E SEPARAÇÃO DE CONVERSAS ===")

    rnd = random.randint(100000, 999999)
    test_email = f"novo_usuario_{rnd}@fechat.crypto"
    test_user = f"usuario_{rnd}"

    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "reg_1",
            "action": "auth_register",
            "payload": {
                "full_name": f"Novo Usuário {rnd}",
                "username": test_user,
                "email": test_email,
                "password": "SenhaSegura123!",
                "language": "pt_BR"
            }
        }))
        res_reg = json.loads(await ws.recv())
        assert res_reg["success"] is True
        token = res_reg["data"]["access_token"]
        user_id = res_reg["data"]["user"]["id"]
        print(f"✅ 1. Usuário registrado com sucesso via WebSocket! (ID: {user_id})")

    async with websockets.connect(f"{WS_URL}?token={token}") as ws:
        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "get_chats_1",
            "action": "get_chats",
            "payload": {}
        }))
        res_chats = json.loads(await ws.recv())
        assert res_chats["success"] is True
        chats = res_chats["data"]["chats"]
        print(f"✅ 2. Conversas recuperadas: {len(chats)} conversa(s)")

        bot_chat = next((c for c in chats if c["target_user"] and c["target_user"]["is_bot"]), None)
        assert bot_chat is not None, "Conversa com Bot Oficial não foi encontrada!"
        assert bot_chat["target_user"]["is_verified"] is True, "Bot deve ser verificado!"
        print(f"✅ 3. Conversa com Bot Oficial identificada com sucesso! (Título: {bot_chat['title']} | Verificado: {bot_chat['target_user']['is_verified']})")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "get_msgs_1",
            "action": "get_messages",
            "payload": {"chat_id": bot_chat["id"]}
        }))
        res_msgs = json.loads(await ws.recv())
        assert res_msgs["success"] is True
        assert len(res_msgs["data"]["messages"]) >= 1
        print("✅ 4. Mensagem automática de boas-vindas do Bot Oficial recebida e armazenada com sucesso!")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "send_to_bot_1",
            "action": "send_message",
            "payload": {
                "chat_id": bot_chat["id"],
                "ciphertext": "teste_bloqueio",
                "iv": "teste_iv",
                "tag": "teste_tag",
                "message_type": "text"
            }
        }))
        res_send = json.loads(await ws.recv())
        assert res_send["success"] is False, "Envio para o bot deveria falhar!"
        print(f"✅ 5. Tentativa de envio para o Bot bloqueada com sucesso: '{res_send['error']}'")

    print("\n🎉 TODOS OS TESTES DE BOT OFICIAL, VERIFICAÇÃO E REGRAS DE CONVERSA PASSARAM COM SUCESSO!")

if __name__ == "__main__":
    asyncio.run(test_bot_and_features())
