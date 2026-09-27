import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import json
import websockets
import random
from datetime import datetime, timedelta
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.chat import Chat, ChatMember
from app.models.message import Message
from app.models.contact import Contact

WS_URL = "ws://127.0.0.1:8000/ws/chat"

async def test_profile_and_validation():
    print("=== TESTE DE EDIÇÃO DE PERFIL E VALIDAÇÃO ESTRITA DE USERNAME ===")

    rnd = random.randint(100000, 999999)
    valid_initial_user = f"usuario_{rnd}"
    email = f"validacao_{rnd}@fechat.crypto"

    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "reg_invalid",
            "action": "auth_register",
            "payload": {
                "full_name": "Teste Inválido",
                "username": "usuario@invalido!#",
                "email": email,
                "password": "SenhaSegura123!"
            }
        }))
        res_inv = json.loads(await ws.recv())
        assert res_inv["success"] is False, "Cadastro com username contendo símbolos deveria falhar!"
        print(f"✅ 1. Cadastro com caracteres especiais bloqueado: '{res_inv['error']}'")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "reg_valid",
            "action": "auth_register",
            "payload": {
                "full_name": "Diego Rafael",
                "username": valid_initial_user,
                "email": email,
                "password": "SenhaSegura123!",
                "bio": "Olá! Estou usando o Fechat."
            }
        }))
        res_val = json.loads(await ws.recv())
        assert res_val["success"] is True
        token = res_val["data"]["access_token"]
        user_id = res_val["data"]["user"]["id"]
        print(f"✅ 2. Usuário cadastrado com sucesso! (Username: {valid_initial_user})")

    async with AsyncSessionLocal() as db:
        u = await db.get(User, user_id)
        u.created_at = datetime.utcnow() - timedelta(days=35)
        await db.commit()

    async with websockets.connect(f"{WS_URL}?token={token}") as ws:
        new_valid_username = f"diego_rafael.{rnd}"
        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "upd_valid",
            "action": "update_profile",
            "payload": {
                "full_name": "Diego Rafael Santos",
                "username": new_valid_username,
                "bio": "✨ Desenvolvedor focado em segurança e interfaces humanizadas."
            }
        }))
        res_upd = json.loads(await ws.recv())
        assert res_upd["success"] is True
        assert res_upd["data"]["user"]["username"] == new_valid_username
        print(f"✅ 3. Perfil atualizado com sucesso! (Novo username: {new_valid_username})")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "upd_invalid_html",
            "action": "update_profile",
            "payload": {
                "username": "<script>alert(1)</script>"
            }
        }))
        res_inv_html = json.loads(await ws.recv())
        assert res_inv_html["success"] is False
        print(f"✅ 4. Tentativa de injeção de HTML/Scripts no username bloqueada: '{res_inv_html['error']}'")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "upd_invalid_space",
            "action": "update_profile",
            "payload": {
                "username": "diego rafael com espacos"
            }
        }))
        res_inv_spc = json.loads(await ws.recv())
        assert res_inv_spc["success"] is False
        print(f"✅ 5. Tentativa de username com espaços bloqueada: '{res_inv_spc['error']}'")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "upd_sanitized",
            "action": "update_profile",
            "payload": {
                "full_name": "<b>Diego</b> <script>steal()</script>Rafael",
                "bio": "<h1>Bio Hack</h1> Teste limpo"
            }
        }))
        res_san = json.loads(await ws.recv())
        assert res_san["success"] is True
        user_data = res_san["data"]["user"]
        assert "<script>" not in user_data["full_name"]
        assert "<h1>" not in user_data["bio"]
        print(f"✅ 6. Sanitização aplicada com sucesso: Nome='{user_data['full_name']}', Bio='{user_data['bio']}'")

    print("\n🎉 TODOS OS TESTES DE VALIDAÇÃO ESTRITA DE PERFIL E SEGURANÇA PASSARAM COM SUCESSO!")

if __name__ == "__main__":
    asyncio.run(test_profile_and_validation())
