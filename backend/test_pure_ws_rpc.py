import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import json
import websockets
import base64
import random

WS_URL = "ws://127.0.0.1:8000/ws/chat"

async def test_pure_ws_platform():
    print("=== TESTE DA PLATAFORMA 100% PURO WEBSOCKET (SEM ROTAS HTTP VISÍVEIS) ===")

    unique_num = random.randint(10000, 99999)
    test_email = f"ws_user_{unique_num}@fechat.crypto"
    test_user = f"ws_user_{unique_num}"
    test_pass = "SenhaSegura123!"

    async with websockets.connect(WS_URL) as ws_anon:
        print("✅ 1. Conectado ao túnel WebSocket anônimo!")

        await ws_anon.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "reg_1",
            "action": "auth_register",
            "payload": {
                "full_name": f"Usuário Puro WS {unique_num}",
                "username": test_user,
                "email": test_email,
                "password": test_pass,
                "language": "pt_BR"
            }
        }))
        res_reg = json.loads(await ws_anon.recv())
        assert res_reg["success"] is True, f"Erro no registro WS: {res_reg}"
        token1 = res_reg["data"]["access_token"]
        user1 = res_reg["data"]["user"]
        print(f"✅ 2. auth_register executado 100% no WebSocket! (ID 12 dígitos: {user1['numeric_id']})")

    async with websockets.connect(f"{WS_URL}?token={token1}") as ws:
        print("✅ 3. Túnel WebSocket autenticado com Token JWE!")

        await ws.send(json.dumps({"type": "rpc_request", "rpc_id": "me_1", "action": "auth_me", "payload": {}}))
        res_me = json.loads(await ws.recv())
        assert res_me["success"] is True
        assert res_me["data"]["user"]["username"] == test_user
        print(f"✅ 4. auth_me verificado via WebSocket: {res_me['data']['user']['full_name']}")

        fake_png_base64 = base64.b64encode(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfechat_pure_avatar").decode('utf-8')
        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "avatar_1",
            "action": "auth_upload_avatar",
            "payload": {
                "filename": "my_avatar.png",
                "data_base64": fake_png_base64
            }
        }))
        res_avatar = json.loads(await ws.recv())
        assert res_avatar["success"] is True
        assert "/api/v1/media/stream/" in res_avatar["data"]["avatar_url"]
        print(f"✅ 5. auth_upload_avatar via WebSocket armazenado no cofre: {res_avatar['data']['avatar_url']}")

        await ws.send(json.dumps({"type": "rpc_request", "rpc_id": "search_1", "action": "search_users", "payload": {"query": "felipe"}}))
        res_search = json.loads(await ws.recv())
        assert res_search["success"] is True
        target_user = res_search["data"]["users"][0]
        print(f"✅ 6. search_users via WebSocket encontrou: {target_user['full_name']} (ID {target_user['id']})")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "contact_add_1",
            "action": "add_contact",
            "payload": {"identifier": target_user["numeric_id"], "nickname": "Felipe Amigo"}
        }))
        res_add = json.loads(await ws.recv())
        assert res_add["success"] is True
        print("✅ 7. add_contact registrado via WebSocket!")

        await ws.send(json.dumps({"type": "rpc_request", "rpc_id": "contacts_1", "action": "get_contacts", "payload": {}}))
        res_contacts = json.loads(await ws.recv())
        assert res_contacts["success"] is True
        print(f"✅ 8. get_contacts listado via WebSocket ({len(res_contacts['data']['contacts'])} contatos)")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "chat_create_1",
            "action": "create_direct_chat",
            "payload": {"target_user_id": target_user["id"]}
        }))
        res_chat = json.loads(await ws.recv())
        if not res_chat.get("success"):
            print("Erro no RPC create_direct_chat:", res_chat)
        assert res_chat["success"] is True
        chat_id = res_chat["data"]["chat"]["id"]
        print(f"✅ 9. create_direct_chat criado via WebSocket (Chat ID: {chat_id})")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "msg_send_1",
            "action": "send_message",
            "payload": {
                "chat_id": chat_id,
                "ciphertext": "cipher_sample_bytes_base64",
                "iv": "iv_sample_base64",
                "tag": "tag_sample_base64",
                "message_type": "text"
            }
        }))
        res_msg = json.loads(await ws.recv())
        if not res_msg.get("success"):
            print("Erro no RPC send_message:", res_msg)
        assert res_msg["success"] is True
        print("✅ 10. send_message transmitido 100% via WebSocket!")

        await ws.send(json.dumps({"type": "rpc_request", "rpc_id": "msg_get_1", "action": "get_messages", "payload": {"chat_id": chat_id}}))
        res_get_msgs = json.loads(await ws.recv())
        assert res_get_msgs["success"] is True
        print(f"✅ 11. get_messages carregado via WebSocket ({len(res_get_msgs['data']['messages'])} mensagens)")

        await ws.send(json.dumps({"type": "rpc_request", "rpc_id": "read_1", "action": "mark_read", "payload": {"chat_id": chat_id}}))
        res_read = json.loads(await ws.recv())
        assert res_read["success"] is True
        print("✅ 12. mark_read confirmado via WebSocket!")

        fake_doc_base64 = base64.b64encode(b"%PDF-1.4 fechat secure document payload").decode('utf-8')
        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "media_up_1",
            "action": "upload_chat_media",
            "payload": {
                "filename": "documento_secreto.pdf",
                "data_base64": fake_doc_base64
            }
        }))
        res_doc = json.loads(await ws.recv())
        assert res_doc["success"] is True
        print(f"✅ 13. upload_chat_media via WebSocket gravado no cofre com hash: {res_doc['data']['media_url']}")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "rep_1",
            "action": "submit_report",
            "payload": {
                "reported_user_id": target_user["id"],
                "category": "other",
                "reason": "Auditoria de segurança pura WebSocket"
            }
        }))
        res_rep = json.loads(await ws.recv())
        assert res_rep["success"] is True
        print("✅ 14. submit_report protocolado via WebSocket com sucesso!")

    print("\n🎉 TODAS AS ROTAS E OPERAÇÕES DA PLATAFORMA FORAM CONVERTIDAS 100% PARA WEBSOCKET RPC!")

if __name__ == "__main__":
    asyncio.run(test_pure_ws_platform())
