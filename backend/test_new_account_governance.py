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

async def test_new_account_governance():
    print("=== TESTE DE GOVERNANÇA DE CONTAS NOVAS (30 DIAS) E COOLDOWN DE 7 DIAS ===")

    rnd = random.randint(100000, 999999)
    test_user = f"novaconta_{rnd}"
    email = f"novaconta_{rnd}@fechat.crypto"

    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "reg_gov",
            "action": "auth_register",
            "payload": {
                "full_name": "Usuário Nova Conta",
                "username": test_user,
                "email": email,
                "password": "SenhaSegura123!"
            }
        }))
        res_reg = json.loads(await ws.recv())
        token = res_reg["data"]["access_token"]
        user_id = res_reg["data"]["user"]["id"]
        assert res_reg["data"]["user"]["is_new_account"] is True
        assert res_reg["data"]["user"]["days_until_username_unlock"] == 30
        print(f"✅ 1. Nova conta identificada com período probatório de 30 dias (ID {user_id})")

    async with websockets.connect(f"{WS_URL}?token={token}") as ws:
        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "try_change_username_new",
            "action": "update_profile",
            "payload": {
                "username": f"trocado_{rnd}"
            }
        }))
        res_blocked = json.loads(await ws.recv())
        assert res_blocked["success"] is False
        assert "30 dias" in res_blocked["error"]
        print(f"✅ 2. Bloqueio de alteração de username em conta nova validado: '{res_blocked['error']}'")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "update_name_and_bio",
            "action": "update_profile",
            "payload": {
                "full_name": "Nome Atualizado Com Sucesso",
                "bio": "Bio atualizada sem restrição"
            }
        }))
        res_bio = json.loads(await ws.recv())
        assert res_bio["success"] is True
        assert res_bio["data"]["user"]["full_name"] == "Nome Atualizado Com Sucesso"
        print("✅ 3. Alteração de nome completo e bio em conta nova permitida com sucesso!")

    async with AsyncSessionLocal() as db:
        u = await db.get(User, user_id)
        u.created_at = datetime.utcnow() - timedelta(days=35)
        await db.commit()
        print("⚡ 4. Conta envelhecida artificialmente para 35 dias (Conta Estabelecida).")

    async with websockets.connect(f"{WS_URL}?token={token}") as ws:
        first_new_username = f"liberado_{rnd}"
        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "change_username_mature",
            "action": "update_profile",
            "payload": {
                "username": first_new_username
            }
        }))
        res_mature = json.loads(await ws.recv())
        assert res_mature["success"] is True
        assert res_mature["data"]["user"]["username"] == first_new_username
        print(f"✅ 5. Nome de usuário alterado com sucesso após 30 dias: {first_new_username}")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "change_username_cooldown",
            "action": "update_profile",
            "payload": {
                "username": f"outro_nome_{rnd}"
            }
        }))
        res_cooldown = json.loads(await ws.recv())
        assert res_cooldown["success"] is False
        assert "7 dias" in res_cooldown["error"]
        print(f"✅ 6. Cooldown de 7 dias entre trocas de username validado: '{res_cooldown['error']}'")

    print("\n🎉 TODOS OS TESTES DE GOVERNANÇA DE CONTAS NOVAS E COOLDOWN PASSARAM COM SUCESSO!")

if __name__ == "__main__":
    asyncio.run(test_new_account_governance())
