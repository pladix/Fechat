import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.chat import Chat, ChatMember
from app.models.compliance import AbuseReport
from app.models.message import Message
from app.services.auth_service import get_password_hash
from app.services.id_generator import generate_numeric_id
from app.api.websockets.ws_rpc_handler import handle_ws_rpc

async def call_rpc(user_id, action, payload):
    try:
        res, _ = await handle_ws_rpc(user_id, action, payload)
        return res, None
    except Exception as e:
        return None, str(e)

async def test_probabilistic_moderation_suite():
    print("🚀 [TEST] Iniciando Bateria de Testes do Motor Probabilístico de Moderação (Risk Scoring)...")

    async with AsyncSessionLocal() as db:
        target_u = User(
            email=f"target_{generate_numeric_id()}@fechat.local",
            username=f"target_{generate_numeric_id()[:6]}",
            full_name="Usuário Alvo Inocente",
            password_hash=get_password_hash("123456"),
            numeric_id=generate_numeric_id(),
            created_at=datetime.utcnow() - timedelta(days=60),
            is_active=True,
            is_suspended=False
        )
        db.add(target_u)
        await db.commit()
        await db.refresh(target_u)
        target_id = target_u.id

        burners = []
        for i in range(3):
            b = User(
                email=f"burner_{i}_{generate_numeric_id()}@fechat.local",
                username=f"burner_{i}_{generate_numeric_id()[:6]}",
                full_name=f"Conta Fake {i+1}",
                password_hash=get_password_hash("123456"),
                numeric_id=generate_numeric_id(),
                created_at=datetime.utcnow(),
                is_active=True,
                is_suspended=False
            )
            db.add(b)
            burners.append(b)
        await db.commit()
        for b in burners:
            await db.refresh(b)
        burner_ids = [b.id for b in burners]

    print("✅ 1. Cenário de teste montado: Alvo inocente e 3 contas recém-criadas.")

    for b_id in burner_ids:
        await call_rpc(b_id, "submit_report", {
            "reported_user_id": target_id,
            "category": "harassment",
            "reason": "Ele foi rude comigo"
        })

    async with AsyncSessionLocal() as db:
        target_check = await db.get(User, target_id)
        assert target_check.is_suspended is False, "FALHA: O usuário alvo foi banido indevidamente por ataque de contas novas!"
    print("✅ 2. Proteção Anti-Brigading validada com sucesso: 3 denúncias de contas novas NÃO baniram o usuário inocente.")

    veteran_ids = []
    async with AsyncSessionLocal() as db:
        for i in range(3):
            v = User(
                email=f"vet_{i}_{generate_numeric_id()}@fechat.local",
                username=f"vet_{i}_{generate_numeric_id()[:6]}",
                full_name=f"Usuário Veterano {i+1}",
                password_hash=get_password_hash("123456"),
                numeric_id=generate_numeric_id(),
                created_at=datetime.utcnow() - timedelta(days=90),
                is_active=True,
                is_suspended=False
            )
            db.add(v)
            await db.commit()
            await db.refresh(v)
            for m_idx in range(6):
                db.add(Message(
                    chat_id=1,
                    sender_id=v.id,
                    ciphertext="sample_cipher",
                    iv="sample_iv",
                    tag="sample_tag",
                    message_type="text"
                ))
            await db.commit()
            veteran_ids.append(v.id)

        bad_user = User(
            email=f"bad_{generate_numeric_id()}@fechat.local",
            username=f"bad_{generate_numeric_id()[:6]}",
            full_name="Golpista Comprovado",
            password_hash=get_password_hash("123456"),
            numeric_id=generate_numeric_id(),
            created_at=datetime.utcnow() - timedelta(days=2),
            is_active=True,
            is_suspended=False
        )
        db.add(bad_user)
        await db.commit()
        await db.refresh(bad_user)
        bad_id = bad_user.id

    for v_id in veteran_ids:
        await call_rpc(v_id, "submit_report", {
            "reported_user_id": bad_id,
            "category": "fraud",
            "reason": "Tentativa comprovada de golpe financeiro com envio de links falsos",
            "plaintext_evidence": "Transfira 5000 reais para chave pix falsa urgente",
            "franking_tag": "tag_franking_valid_hmac_123"
        })

    async with AsyncSessionLocal() as db:
        bad_check = await db.get(User, bad_id)
        assert bad_check.is_suspended is True, f"FALHA: O infrator comprovado com evidências deveria ter sido suspenso! Status: {bad_check.is_suspended}"
    print("✅ 3. Moderação com Alta Confiança validada: Infrator comprovado suspenso com Risk Score alto.")

    res_grp, _ = await call_rpc(veteran_ids[0], "create_group_chat", {
        "title": "Comunidade Saudável",
        "description": "Discussão produtiva",
        "member_user_ids": veteran_ids + [target_id]
    })
    group_id = res_grp["chat"]["id"]

    for b_id in burner_ids[:2]:
        await call_rpc(b_id, "submit_report", {
            "chat_id": group_id,
            "category": "other",
            "reason": "Não gostei desse grupo"
        })

    async with AsyncSessionLocal() as db:
        grp_check = await db.get(Chat, group_id)
        assert grp_check.is_suspended is False, "FALHA: Grupo legítimo foi suspenso por denúncias vazias!"
    print("✅ 4. Proteção de Grupos validada: Grupo legítimo não foi derrubado por denúncias vazias.")

    print("\n🎉 [SUCESSO TOTAL] Todos os 4 testes de Moderação Probabilística e Anti-Brigade passaram 100%!")

if __name__ == "__main__":
    asyncio.run(test_probabilistic_moderation_suite())
