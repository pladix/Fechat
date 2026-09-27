import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import json
import websockets
from sqlalchemy import select

import app.models.user
import app.models.chat
import app.models.message
import app.models.contact
import app.models.compliance

from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.auth_service import create_access_token, get_password_hash
from app.services.id_generator import generate_numeric_id

BASE_WS = "ws://127.0.0.1:80/ws/chat"

async def test_group_features_suite():
    print("=== TESTE AUTOMATIZADO DE RECURSOS AVANÇADOS DE GRUPO DO FECHAT ===")

    async with AsyncSessionLocal() as db:
        u1_res = await db.execute(select(User).where(User.email == 'felipe@exemplo.com'))
        u1 = u1_res.scalars().first()
        if not u1:
            u1 = User(
                email='felipe@exemplo.com',
                username='felipe',
                full_name='Felipe Santos',
                password_hash=get_password_hash('123456'),
                numeric_id=generate_numeric_id()
            )
            db.add(u1)
            await db.commit()
            await db.refresh(u1)

        u1_token = create_access_token(data={"sub": str(u1.id), "username": u1.username})
        u1_id = u1.id
        print(f"✅ 1. Criador do Grupo autenticado! (ID: {u1_id}, Nome: {u1.full_name})")

        u2_res = await db.execute(select(User).where(User.email == 'membro_grupo@fechat.local'))
        u2 = u2_res.scalars().first()
        if not u2:
            u2 = User(
                email='membro_grupo@fechat.local',
                username='membro_grupo_teste',
                full_name='Membro Teste Grupo',
                password_hash=get_password_hash('123456'),
                numeric_id=generate_numeric_id()
            )
            db.add(u2)
            await db.commit()
            await db.refresh(u2)

        u2_token = create_access_token(data={"sub": str(u2.id), "username": u2.username})
        u2_id = u2.id
        print(f"✅ 2. Membro do Grupo autenticado! (ID: {u2_id}, Nome: {u2.full_name})")

    async with websockets.connect(f"{BASE_WS}?token={u1_token}") as ws1, websockets.connect(f"{BASE_WS}?token={u2_token}") as ws2:
        async def rpc_call(ws, action, payload):
            rpc_id = f"rpc_test_{action}_{asyncio.get_event_loop().time()}"
            await ws.send(json.dumps({
                "type": "rpc_request",
                "rpc_id": rpc_id,
                "action": action,
                "payload": payload
            }))
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if data.get("type") == "rpc_response" and data.get("rpc_id") == rpc_id:
                    return data

        res = await rpc_call(ws1, "create_group_chat", {
            "title": "Grupo VIP Fechat",
            "description": "Comunidade com regras de WhatsApp",
            "member_ids": [u2_id]
        })
        assert res.get("success") is True, f"Falha ao criar grupo: {res}"
        group_chat = res["data"]["chat"]
        chat_id = group_chat["id"]
        print(f"✅ 3. Grupo criado com sucesso! (ID: {chat_id}, Título: '{group_chat['title']}')")

        res = await rpc_call(ws1, "get_group_details", {"chat_id": chat_id})
        assert res.get("success") is True, f"Falha ao obter detalhes: {res}"
        g_details = res["data"]["group"]
        assert len(g_details["members"]) == 2
        print(f"✅ 4. Detalhes do grupo consultados: {len(g_details['members'])} participantes confirmados!")

        res = await rpc_call(ws1, "change_group_member_role", {"chat_id": chat_id, "user_id": u2_id, "role": "admin"})
        assert res.get("success") is True, f"Falha ao promover admin: {res}"
        print(f"✅ 5. Membro promovido a Administrador com sucesso!")

        res = await rpc_call(ws1, "change_group_member_role", {"chat_id": chat_id, "user_id": u2_id, "role": "member"})
        assert res.get("success") is True, f"Falha ao rebaixar membro: {res}"
        print(f"✅ 6. Administrador rebaixado a Membro com sucesso!")

        res = await rpc_call(ws1, "update_group_info", {
            "chat_id": chat_id,
            "only_admins_send_messages": True
        })
        assert res.get("success") is True, f"Falha ao atualizar permissões: {res}"
        print(f"✅ 7. Permissão 'Apenas Administradores Enviam' ativada com sucesso!")

        res_mem_send = await rpc_call(ws2, "send_message", {
            "chat_id": chat_id,
            "ciphertext": "VGVzdGUgbWVtYnJv",
            "iv": "MTIzNDU2Nzg5MDEy",
            "tag": "MTIzNDU2Nzg5MDEyMzQ1Ng==",
            "message_type": "text"
        })
        assert res_mem_send.get("success") is False, "Membro comum não deveria conseguir enviar mensagem!"
        print(f"✅ 8. Envio de mensagem por membro comum bloqueado corretamente: '{res_mem_send.get('error')}'")

        res_admin_send = await rpc_call(ws1, "send_message", {
            "chat_id": chat_id,
            "ciphertext": "VGVzdGUgYWRtaW4gYXZpc28=",
            "iv": "MTIzNDU2Nzg5MDEy",
            "tag": "MTIzNDU2Nzg5MDEyMzQ1Ng==",
            "message_type": "text"
        })
        assert res_admin_send.get("success") is True, f"Falha no envio do admin: {res_admin_send}"
        msg1 = res_admin_send["data"]["message"]
        msg1_id = msg1["id"]
        print(f"✅ 9. Mensagem enviada pelo Administrador com sucesso! (ID: {msg1_id})")

        res = await rpc_call(ws1, "pin_group_message", {"chat_id": chat_id, "message_id": msg1_id})
        assert res.get("success") is True, f"Falha ao fixar mensagem: {res}"
        print(f"✅ 10. Mensagem {msg1_id} fixada no topo do grupo para todos com sucesso!")

        res_reply = await rpc_call(ws1, "send_message", {
            "chat_id": chat_id,
            "ciphertext": "UmVzcG9uZGlkbyBjb20gc3VjZXNzbw==",
            "iv": "MTIzNDU2Nzg5MDEy",
            "tag": "MTIzNDU2Nzg5MDEyMzQ1Ng==",
            "message_type": "text",
            "reply_to_message_id": msg1_id,
            "reply_to_sender_name": "Oficial de Segurança",
            "reply_to_snippet": "Aviso importante para o grupo"
        })
        assert res_reply.get("success") is True, f"Falha no envio da resposta: {res_reply}"
        reply_msg = res_reply["data"]["message"]
        assert reply_msg["reply_to_message_id"] == msg1_id
        assert reply_msg["reply_to_sender_name"] == "Oficial de Segurança"
        print(f"✅ 11. Mensagem de Resposta/Citação vinculada com sucesso! (ID: {reply_msg['id']}, Respondendo a: {msg1_id})")

        res = await rpc_call(ws1, "delete_message_for_everyone", {"message_id": msg1_id})
        assert res.get("success") is True, f"Falha ao apagar mensagem para todos: {res}"
        print(f"✅ 12. Mensagem {msg1_id} apagada para todos com sucesso!")

        res = await rpc_call(ws1, "pin_group_message", {"chat_id": chat_id, "message_id": None})
        assert res.get("success") is True, f"Falha ao desafixar mensagem: {res}"
        print(f"✅ 13. Mensagem desafixada do grupo com sucesso!")

    print("\n🎉 TODOS OS TESTES DE RECURSOS DE GRUPO ESTILO WHATSAPP PASSARAM COM 100% DE SUCESSO!")

if __name__ == "__main__":
    asyncio.run(test_group_features_suite())
