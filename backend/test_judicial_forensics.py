import asyncio
import websockets
import json
import hashlib
import sys
import io
from datetime import datetime
from app.services.crypto_service import CryptoEngine

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

WS_URL = "ws://127.0.0.1:80/ws/chat"

async def test_judicial_forensics_suite():
    print("🚀 [TEST] Iniciando Bateria de Testes de Auditoria Forense e Painel Judicial...")

    preauth_key = CryptoEngine.get_preauth_wire_key_hex()
    active_key = preauth_key

    async with websockets.connect(WS_URL) as ws:
        async def call_rpc(action, payload, rpc_id):
            nonlocal active_key
            req = {
                "type": "rpc_request",
                "rpc_id": rpc_id,
                "action": action,
                "payload": payload
            }
            sealed = CryptoEngine.seal_wire_packet(req, active_key)
            await ws.send(json.dumps(sealed))
            while True:
                raw = await ws.recv()
                raw_json = json.loads(raw)
                data = CryptoEngine.unseal_wire_packet(raw_json, active_key)
                if isinstance(data, dict) and data.get("type") == "rpc_response" and data.get("rpc_id") == rpc_id:
                    return data

        res = await call_rpc("auth_login", {"login": "admin", "password": "admin123456"}, "login_admin")
        assert res.get("success") is True, f"Falha no login do admin: {res}"
        admin_data = res["data"]["user"]
        active_key = CryptoEngine.derive_session_wire_key_hex(res["data"]["access_token"])
        assert admin_data["is_admin"] is True, "Admin deve ter is_admin=True"
        assert admin_data["is_verified"] is True, "Admin deve ter is_verified=True (selo oficial)"
        print(f"✅ 1. Oficial de Segurança autenticado com sucesso! ID: {admin_data['numeric_id']}, Verificado: {admin_data['is_verified']}")

        res_users = await call_rpc("get_judicial_users_list", {"query": ""}, "get_users")
        assert res_users.get("success") is True, f"Falha ao listar usuários: {res_users}"
        users = res_users["data"]["users"]
        assert len(users) > 0, "Deve haver usuários registrados"
        target_user = next((u for u in users if u["username"] != "admin" and not u["is_bot"]), users[0])
        print(f"✅ 2. Rastreamento forense listou {len(users)} usuários com sucesso! Alvo selecionado: {target_user['full_name']} (@{target_user['username']}) - IP: {target_user['last_ip']} - Dispositivo: {target_user['device_info']}")

        res_dossier = await call_rpc("get_judicial_user_dossier", {"user_id": target_user["id"]}, "get_dossier")
        assert res_dossier.get("success") is True, f"Falha no dossiê: {res_dossier}"
        dossier = res_dossier["data"]
        assert dossier["user"]["id"] == target_user["id"]
        print(f"✅ 3. Dossiê do usuário consultado! Total de conversas monitoradas: {len(dossier['chats'])}, Denúncias: {len(dossier['reports'])}")

        if dossier["chats"]:
            chat_id = dossier["chats"][0]["chat_id"]
            res_msgs = await call_rpc("get_judicial_chat_messages", {"chat_id": chat_id, "limit": 50}, "get_chat_msgs")
            assert res_msgs.get("success") is True, f"Falha na descriptografia judicial: {res_msgs}"
            print(f"✅ 4. Descriptografia forense da conversa '{res_msgs['data']['title']}' concluída! Total de mensagens decifradas: {len(res_msgs['data']['messages'])}")

        res_notice = await call_rpc("send_judicial_notice", {
            "user_id": target_user["id"],
            "title": "AVISO DE CONFORMIDADE E AUDITORIA",
            "body": "Sua conta foi submetida a uma verificação de integridade de segurança pelos canais oficiais do Fechat."
        }, "send_notice")
        assert res_notice.get("success") is True, f"Falha no envio de notificação judicial: {res_notice}"
        print(f"✅ 5. Notificação judicial oficial transmitida com fé pública com sucesso para o usuário!")

        order_num = f"AUTOS-TEST-{int(datetime.utcnow().timestamp())}"
        res_export = await call_rpc("export_judicial_dossier", {
            "user_id": target_user["id"],
            "court_order_number": order_num,
            "issuing_court": "1ª Vara de Crimes Cibernéticos",
            "officer_badge": "Perito Federal 4410",
            "reason": "Instrução de Procedimento Investigatório"
        }, "export_dossier")
        assert res_export.get("success") is True, f"Falha na exportação do dossiê: {res_export}"
        export_data = res_export["data"]
        sha256_hash = export_data["sha256_hash"]
        assert len(sha256_hash) == 64, "Hash SHA-256 deve ter 64 caracteres hexadecimais"
        print(f"✅ 6. Dossiê integral exportado e registrado com Hash SHA-256: {sha256_hash}")

        res_susp = await call_rpc("suspend_user", {"user_id": target_user["id"], "reason": "Teste de Auditoria"}, "suspend")
        assert res_susp.get("success") is True, f"Falha ao suspender: {res_susp}"
        print("✅ 7.1 Suspensão de conta executada com sucesso!")

        res_unsusp = await call_rpc("unsuspend_user", {"user_id": target_user["id"]}, "unsuspend")
        assert res_unsusp.get("success") is True, f"Falha ao reativar: {res_unsusp}"
        print("✅ 7.2 Reativação de conta executada com sucesso!")

    print("\n🎉 [SUCESSO TOTAL] Todos os testes de Auditoria Forense, Descriptografia Judicial e Dossiê SHA-256 passaram 100%!")

if __name__ == "__main__":
    asyncio.run(test_judicial_forensics_suite())
