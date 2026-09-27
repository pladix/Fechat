import asyncio
from datetime import datetime
from sqlalchemy import select
from app.database import AsyncSessionLocal, engine, Base
import app.models.user
import app.models.chat
import app.models.message
import app.models.contact
import app.models.compliance
from app.models.user import User
from app.models.chat import Chat, ChatMember
from app.models.message import Message
from app.models.contact import Contact
from app.services.auth_service import get_password_hash
from app.services.id_generator import generate_numeric_id
from app.services.crypto_service import CryptoEngine

async def seed():
    print("Iniciando criação de dados e tabelas...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        stmt = select(User).where(User.username == "admin")
        res = await db.execute(stmt)
        if res.scalars().first():
            print("Base de dados já foi inicializada com os usuários padrão.")
            return

        admin_id = generate_numeric_id()
        admin_user = User(
            numeric_id=admin_id,
            username="admin",
            email="admin@fechat.local",
            full_name="Oficial de Segurança & Compliance",
            password_hash=get_password_hash("admin123456"),
            bio="Painel de Segurança e Atendimento Judicial Fechat",
            language="pt_BR",
            theme="dark",
            is_active=True,
            is_admin=True
        )

        user1_id = generate_numeric_id()
        user1 = User(
            numeric_id=user1_id,
            username="felipe",
            email="felipe@exemplo.com",
            full_name="Felipe Santos",
            password_hash=get_password_hash("123456"),
            bio="💡 Desenvolvendo experiências incríveis com código e café.",
            language="pt_BR",
            theme="dark",
            is_active=True
        )

        user2_id = generate_numeric_id()
        user2 = User(
            numeric_id=user2_id,
            username="mariana",
            email="mariana@example.com",
            full_name="Mariana Costa",
            password_hash=get_password_hash("123456"),
            bio="✨ Designing humanized interfaces for the world.",
            language="en_US",
            theme="dark",
            is_active=True
        )

        user3_id = generate_numeric_id()
        user3 = User(
            numeric_id=user3_id,
            username="lucas",
            email="lucas@exemplo.com",
            full_name="Lucas Ramos",
            password_hash=get_password_hash("123456"),
            bio="🚀 Sempre online para bater um papo.",
            language="pt_BR",
            theme="dark",
            is_active=True
        )

        db.add_all([admin_user, user1, user2, user3])
        await db.commit()
        await db.refresh(admin_user)
        await db.refresh(user1)
        await db.refresh(user2)
        await db.refresh(user3)

        c1 = Contact(user_id=user1.id, contact_user_id=user2.id, nickname="Mari Designer")
        c2 = Contact(user_id=user2.id, contact_user_id=user1.id, nickname="Felipe Dev")
        c3 = Contact(user_id=user1.id, contact_user_id=user3.id, nickname="Lucas Tech")
        db.add_all([c1, c2, c3])

        chat_key = CryptoEngine.generate_random_key_hex()
        chat_1 = Chat(is_group=False, aes_channel_key=chat_key, created_by_id=user1.id)
        db.add(chat_1)
        await db.flush()

        m1 = ChatMember(chat_id=chat_1.id, user_id=user1.id, role="admin")
        m2 = ChatMember(chat_id=chat_1.id, user_id=user2.id, role="member")
        db.add_all([m1, m2])

        enc = CryptoEngine.encrypt_aes_gcm("Olá Mariana! Bem-vinda à nova plataforma Fechat com criptografia AES-256-GCM!", chat_key)
        franking = CryptoEngine.generate_message_franking_tag(user1.id, "Olá Mariana!", datetime.utcnow().timestamp(), "server_secret")

        msg1 = Message(
            chat_id=chat_1.id,
            sender_id=user1.id,
            ciphertext=enc["ciphertext"],
            iv=enc["iv"],
            tag=enc["tag"],
            franking_tag=franking
        )
        db.add(msg1)

        group_key = CryptoEngine.generate_random_key_hex()
        group_1 = Chat(
            is_group=True,
            title="🚀 Desenvolvedores & Inovação",
            description="Espaço humanizado para troca de ideias e projetos de tecnologia.",
            group_invite_code="devs-2026",
            aes_channel_key=group_key,
            created_by_id=user1.id
        )
        db.add(group_1)
        await db.flush()

        gm1 = ChatMember(chat_id=group_1.id, user_id=user1.id, role="admin")
        gm2 = ChatMember(chat_id=group_1.id, user_id=user2.id, role="member")
        gm3 = ChatMember(chat_id=group_1.id, user_id=user3.id, role="member")
        db.add_all([gm1, gm2, gm3])

        enc_grp = CryptoEngine.encrypt_aes_gcm("Sejam todos bem-vindos ao grupo! Todas as mensagens aqui são criptografadas.", group_key)
        msg_grp = Message(
            chat_id=group_1.id,
            sender_id=user1.id,
            ciphertext=enc_grp["ciphertext"],
            iv=enc_grp["iv"],
            tag=enc_grp["tag"]
        )
        db.add(msg_grp)

        await db.commit()

        print("Base de dados semeada com sucesso!")
        print(f"Admin: {admin_user.email} (ID: {admin_user.numeric_id}) | Senha: admin123456")
        print(f"User 1: {user1.email} (ID: {user1.numeric_id}) | Senha: 123456")
        print(f"User 2: {user2.email} (ID: {user2.numeric_id}) | Senha: 123456")
        print(f"User 3: {user3.email} (ID: {user3.numeric_id}) | Senha: 123456")

if __name__ == "__main__":
    asyncio.run(seed())
