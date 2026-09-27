import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.chat import Chat
from app.services.auth_service import get_password_hash
from app.services.id_generator import generate_numeric_id
from app.api.websockets.ws_rpc_handler import handle_ws_rpc

async def call_rpc(user_id, action, payload):
    try:
        res, _ = await handle_ws_rpc(user_id, action, payload)
        return res, None
    except Exception as e:
        return None, str(e)

async def run_invites_and_suspension_tests():
    print("🚀 [TEST] Iniciando bateria de testes para Links de Convites e Suspensão de Grupos...")

    async with AsyncSessionLocal() as db:
        async def get_or_create_user(email, username, full_name):
            stmt = select(User).where(User.email == email)
            res = await db.execute(stmt)
            u = res.scalars().first()
            if not u:
                u = User(
                    email=email,
                    username=username,
                    full_name=full_name,
                    password_hash=get_password_hash("123456"),
                    numeric_id=generate_numeric_id(),
                    is_active=True,
                    is_suspended=False
                )
                db.add(u)
                await db.commit()
                await db.refresh(u)
            return u

        u_owner = await get_or_create_user("inv_owner@fechat.local", "inv_owner", "Dono do Grupo")
        u_member = await get_or_create_user("inv_member@fechat.local", "inv_member", "Membro Comum")
        u_joiner = await get_or_create_user("inv_joiner@fechat.local", "inv_joiner", "Entrante via Link")
        u_rep1 = await get_or_create_user("inv_rep1@fechat.local", "inv_rep1", "Denunciante 1")
        u_rep2 = await get_or_create_user("inv_rep2@fechat.local", "inv_rep2", "Denunciante 2")
        u_rep3 = await get_or_create_user("inv_rep3@fechat.local", "inv_rep3", "Denunciante 3")

        u_rep1.is_verified = True
        u_rep2.is_verified = True
        u_rep3.is_verified = True
        await db.commit()

    print(f"✅ 1. Usuários de teste configurados com sucesso.")

    res, err = await call_rpc(
        u_owner.id,
        "create_group_chat",
        {"title": "Grupo de Teste Convites", "description": "Comunidade de Teste", "member_user_ids": [u_member.id]}
    )
    assert err is None, f"Erro ao criar grupo: {err}"
    group_id = res["chat"]["id"]
    print(f"✅ 2. Grupo criado com sucesso (ID: {group_id})")

    res_link, err = await call_rpc(u_owner.id, "get_group_invite_link", {"chat_id": group_id})
    assert err is None, f"Erro ao obter link: {err}"
    invite_code_1 = res_link["invite_code"]
    assert invite_code_1.startswith("fe1_inv_"), "Formato de código inválido"
    print(f"✅ 3. Link de convite gerado com sucesso: {res_link['invite_link']}")

    res_fail, err = await call_rpc(u_member.id, "get_group_invite_link", {"chat_id": group_id})
    assert err is not None, "Membro comum não deveria conseguir obter link de convite!"
    print(f"✅ 4. Bloqueio de permissão para membro comum validado: {err}")

    res_prev, err = await call_rpc(u_joiner.id, "get_group_preview_by_invite", {"invite_code": invite_code_1})
    assert err is None, f"Erro na prévia: {err}"
    assert res_prev["group_preview"]["title"] == "Grupo de Teste Convites"
    assert res_prev["group_preview"]["is_already_member"] is False
    print(f"✅ 5. Prévia do grupo via link validada com sucesso: {res_prev['group_preview']['title']}")

    res_join, err = await call_rpc(u_joiner.id, "join_group_via_invite", {"invite_code": invite_code_1})
    assert err is None, f"Erro ao entrar no grupo: {err}"
    assert res_join["status"] == "joined"
    assert len(res_join["chat"]["members"]) == 3
    print(f"✅ 6. Ingresso no grupo via link concluído! Membros atuais: {len(res_join['chat']['members'])}")

    res_rev, err = await call_rpc(u_owner.id, "revoke_group_invite_link", {"chat_id": group_id})
    assert err is None, f"Erro ao revogar link: {err}"
    invite_code_2 = res_rev["invite_code"]
    assert invite_code_1 != invite_code_2, "O novo código gerado deve ser diferente do antigo revogado"
    print(f"✅ 7. Link revogado e novo link ativo gerado: {res_rev['invite_link']}")

    res_fail_join, err = await call_rpc(u_joiner.id, "get_group_preview_by_invite", {"invite_code": invite_code_1})
    assert err is not None, "Código revogado não deveria mais funcionar!"
    print(f"✅ 8. Tentativa com código antigo revogado rejeitada com sucesso: {err}")

    res_msg, err = await call_rpc(u_joiner.id, "send_message", {
        "chat_id": group_id,
        "ciphertext": "msg_cipher",
        "iv": "iv_sample",
        "tag": "tag_sample",
        "message_type": "text"
    })
    assert err is None, f"Erro ao enviar mensagem: {err}"
    print("✅ 9. Mensagem enviada pelo novo membro no grupo com sucesso.")

    await call_rpc(u_rep1.id, "submit_report", {
        "chat_id": group_id,
        "category": "fraud",
        "reason": "Grupo aplicando golpes financeiros reiterados",
        "plaintext_evidence": "Transfira para nossa conta investimento falso",
        "franking_tag": "valid_franking_tag_1"
    })

    await call_rpc(u_rep2.id, "submit_report", {
        "chat_id": group_id,
        "category": "fraud",
        "reason": "Grupo de esquemas fraudulentos com envio de comprovantes falsos",
        "plaintext_evidence": "Compre o pacote de investimentos fraudulentos aqui",
        "franking_tag": "valid_franking_tag_2"
    })

    await call_rpc(u_rep3.id, "submit_report", {
        "chat_id": group_id,
        "category": "fraud",
        "reason": "Fraude comprovada com links de roubo de credenciais bancárias",
        "plaintext_evidence": "Acesse http://bancofalso.scam e digite sua senha",
        "franking_tag": "valid_franking_tag_3"
    })

    print("✅ 10. Três denúncias de usuários distintos submetidas contra o grupo.")

    async with AsyncSessionLocal() as db:
        chat_check = await db.get(Chat, group_id)
        assert chat_check.is_suspended is True, "O grupo deveria ter sido suspenso pelo Sentinel!"
        print(f"✅ 11. Sentinel suspendeu o grupo automaticamente! Motivo: {chat_check.suspension_reason}")

    res_msg_fail, err = await call_rpc(u_owner.id, "send_message", {
        "chat_id": group_id,
        "ciphertext": "msg_cipher_blocked",
        "iv": "iv_sample",
        "tag": "tag_sample",
        "message_type": "text"
    })
    assert err is not None, "Envio em grupo suspenso deve ser bloqueado!"
    print(f"✅ 12. Bloqueio de envio em grupo suspenso confirmado: {err}")

    res_join_fail, err = await call_rpc(u_rep1.id, "join_group_via_invite", {"invite_code": invite_code_2})
    assert err is not None, "Ingresso em grupo suspenso via link deve ser bloqueado!"
    print(f"✅ 13. Bloqueio de ingresso em grupo suspenso via link confirmado: {err}")

    print("\n🎉 [SUCESSO TOTAL] Todos os 13 testes de Links de Convite e Suspensão de Grupos passaram 100%!")

if __name__ == "__main__":
    asyncio.run(run_invites_and_suspension_tests())
