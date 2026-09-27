import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import json
import websockets
import random

WS_URL = "ws://127.0.0.1:80/ws/chat"

async def test_sentinel_and_immunity():
    print("=== TESTE DE IMUNIDADE DE BOTS/VERIFICADOS, BOT JUDICIAL E SENTINEL ANTI-ABUSO ===")

    rnd = random.randint(100000, 999999)
    test_user_email = f"sentinel_user_{rnd}@fechat.crypto"
    test_username = f"sentinel_{rnd}"

    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "reg_sentinel",
            "action": "auth_register",
            "payload": {
                "full_name": f"Usuário Sentinel {rnd}",
                "username": test_username,
                "email": test_user_email,
                "password": "SenhaForte987!",
                "language": "pt_BR"
            }
        }))
        res_reg = json.loads(await ws.recv())
        assert res_reg["success"] is True
        token = res_reg["data"]["access_token"]
        user_id = res_reg["data"]["user"]["id"]
        print(f"✅ 1. Usuário registrado com sucesso! (ID: {user_id})")

    async with websockets.connect(f"{WS_URL}?token={token}") as ws:
        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "get_chats_sentinel",
            "action": "get_chats",
            "payload": {}
        }))
        res_chats = json.loads(await ws.recv())
        chats = res_chats["data"]["chats"]
        bot_chat = next(c for c in chats if c["target_user"] and c["target_user"]["is_bot"])
        bot_user_id = bot_chat["target_user"]["id"]
        print(f"✅ 2. Bot Oficial verificado identificado (ID: {bot_user_id})")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "block_bot_attempt",
            "action": "block_user",
            "payload": {"user_id": bot_user_id}
        }))
        res_block = json.loads(await ws.recv())
        assert res_block["success"] is False, "Bloquear bot deveria ter falhado!"
        print(f"✅ 3. Imunidade de Bloqueio validada: '{res_block['error']}'")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "report_bot_attempt",
            "action": "submit_report",
            "payload": {
                "reported_user_id": bot_user_id,
                "category": "harassment",
                "reason": "Tentativa indevida de denunciar bot oficial"
            }
        }))
        res_report = json.loads(await ws.recv())
        assert res_report["success"] is False, "Denunciar bot deveria ter falhado!"
        print(f"✅ 4. Imunidade de Denúncia validada: '{res_report['error']}'")

        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "create_chat_test",
            "action": "create_direct_chat",
            "payload": {"target_user_id": 2}
        }))
        res_dc = json.loads(await ws.recv())
        target_chat_id = res_dc["data"]["chat"]["id"]

        print("⚡ 5. Disparando rajada de mensagens rápidas para testar Sentinel Anti-Spam...")
        flood_blocked = False
        for i in range(25):
            await ws.send(json.dumps({
                "type": "rpc_request",
                "rpc_id": f"flood_{i}",
                "action": "send_message",
                "payload": {
                    "chat_id": target_chat_id,
                    "ciphertext": f"burst_cipher_{i}",
                    "iv": "burst_iv",
                    "tag": "burst_tag",
                    "message_type": "text"
                }
            }))

            while True:
                msg_raw = await ws.recv()
                msg_data = json.loads(msg_raw)
                if msg_data.get("type") == "rpc_response" and msg_data.get("rpc_id") == f"flood_{i}":
                    err_lower = str(msg_data.get("error") or "").lower()
                    if not msg_data.get("success") and ("spam" in err_lower or "rápido" in err_lower or "pausado" in err_lower or "suspenso" in err_lower):
                        flood_blocked = True
                        print(f"✅ 6. Sentinel detectou e bloqueou flood em tempo real: '{msg_data['error']}'")
                    break

            if flood_blocked:
                break

        assert flood_blocked, "O Sentinel Anti-Spam deveria ter interceptado a rajada de mensagens!"

    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "login_admin",
            "action": "auth_login",
            "payload": {"identifier": "admin@fechat.local", "password": "admin123456"}
        }))
        res_admin = json.loads(await ws.recv())
        print(f"DEBUG res_admin: {res_admin}")
        admin_token = res_admin["data"]["access_token"]
        print("✅ 7. Autenticado como Administrador de Segurança.")

    async with websockets.connect(f"{WS_URL}?token={admin_token}") as ws:
        await ws.send(json.dumps({
            "type": "rpc_request",
            "rpc_id": "send_legal_notice",
            "action": "send_compliance_notice",
            "payload": {
                "user_id": user_id,
                "notice_text": "⚖️ NOTIFICAÇÃO OFICIAL: Ordem Judicial nº 8492/2026 recebida pela Vara Especializada.",
                "category": "judicial_notice"
            }
        }))
        res_notice = json.loads(await ws.recv())
        assert res_notice["success"] is True
        print("✅ 8. Notificação Judicial transmitida com sucesso pelo Bot de Conformidade Legal!")

    print("\n🎉 TODOS OS TESTES DE IMUNIDADE, BOT JUDICIAL E COMPLIANCE SENTINEL PASSARAM COM SUCESSO!")

if __name__ == "__main__":
    asyncio.run(test_sentinel_and_immunity())
