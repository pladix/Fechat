import os
from datetime import datetime
from typing import Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.chat import Chat, ChatMember
from app.models.message import Message
from app.services.crypto_service import CryptoEngine
from app.services.auth_service import get_password_hash
from app.services.ws_manager import ws_manager

BOT_NUMERIC_ID = "100000000000"
BOT_USERNAME = "fechat_oficial"

LEGAL_BOT_NUMERIC_ID = "100000000002"
LEGAL_BOT_USERNAME = "fechat_compliance"

async def get_or_create_official_bot(db: AsyncSession) -> User:

    stmt = select(User).where(User.numeric_id == BOT_NUMERIC_ID)
    res = await db.execute(stmt)
    bot = res.scalars().first()

    if not bot:
        bot = User(
            numeric_id=BOT_NUMERIC_ID,
            username=BOT_USERNAME,
            email="oficial@fechat.crypto",
            full_name="Fechat Oficial",
            password_hash=get_password_hash(os.urandom(32).hex()),
            bio="Canal oficial e informativo do Fechat. Avisos, novidades e suporte de segurança.",
            avatar_url="https://api.dicebear.com/7.x/identicon/svg?seed=fechat_official_shield",
            is_verified=True,
            is_bot=True,
            is_admin=True,
            is_active=True
        )
        db.add(bot)
        await db.commit()
        await db.refresh(bot)
    else:
        if not bot.is_verified or not bot.is_bot:
            bot.is_verified = True
            bot.is_bot = True
            await db.commit()

    return bot

async def get_or_create_compliance_bot(db: AsyncSession) -> User:

    stmt = select(User).where(User.numeric_id == LEGAL_BOT_NUMERIC_ID)
    res = await db.execute(stmt)
    bot = res.scalars().first()

    if not bot:
        bot = User(
            numeric_id=LEGAL_BOT_NUMERIC_ID,
            username=LEGAL_BOT_USERNAME,
            email="compliance@fechat.crypto",
            full_name="Fechat Conformidade Legal & Segurança",
            password_hash=get_password_hash(os.urandom(32).hex()),
            bio="Canal oficial para notificações judiciais, avisos de conformidade, ordens legais e integridade da rede.",
            avatar_url="https://api.dicebear.com/7.x/identicon/svg?seed=fechat_compliance_legal",
            is_verified=True,
            is_bot=True,
            is_admin=True,
            is_active=True
        )
        db.add(bot)
        await db.commit()
        await db.refresh(bot)
    else:
        if not bot.is_verified or not bot.is_bot:
            bot.is_verified = True
            bot.is_bot = True
            await db.commit()

    return bot

async def send_bot_welcome_message(db: AsyncSession, user: User):

    try:
        bot = await get_or_create_official_bot(db)
        if user.id == bot.id:
            return

        s1 = select(ChatMember.chat_id).where(ChatMember.user_id == user.id)
        s2 = select(ChatMember.chat_id).where(ChatMember.user_id == bot.id)
        common_chat = (await db.execute(select(Chat).where(and_(Chat.id.in_(s1), Chat.id.in_(s2), Chat.is_group == False)))).scalars().first()

        chat = common_chat
        if not chat:
            channel_key = CryptoEngine.generate_random_key_hex()
            chat = Chat(
                is_group=False,
                title="Fechat Oficial",
                aes_channel_key=channel_key
            )
            db.add(chat)
            await db.commit()
            await db.refresh(chat)

            db.add(ChatMember(chat_id=chat.id, user_id=bot.id, role="admin"))
            db.add(ChatMember(chat_id=chat.id, user_id=user.id, role="member"))
            await db.commit()

        if user.language == "en_US":
            welcome_text = (
                f"Hello, {user.full_name}! 👋\n\n"
                f"Welcome to Fechat. Your account was created successfully!\n"
                f"Your unique 12-digit ID is: {user.numeric_id}\n\n"
                f"🛡️ This is an official informative channel where you'll receive updates, news and security announcements.\n"
                f"ℹ️ Note: This is an automated channel and does not receive user replies."
            )
        else:
            welcome_text = (
                f"Olá, {user.full_name}! 👋\n\n"
                f"Seja muito bem-vindo(a) ao Fechat. Sua conta foi criada com sucesso!\n"
                f"Seu ID exclusivo de 12 dígitos é: {user.numeric_id}\n\n"
                f"🛡️ Este é o canal oficial de avisos, novidades e comunicações importantes do sistema.\n"
                f"ℹ️ Nota: Este canal é puramente informativo e não recebe respostas de mensagens."
            )

        encrypted_data = CryptoEngine.encrypt_aes_gcm(welcome_text, chat.aes_channel_key)

        msg = Message(
            chat_id=chat.id,
            sender_id=bot.id,
            ciphertext=encrypted_data["ciphertext"],
            iv=encrypted_data["iv"],
            tag=encrypted_data["tag"],
            message_type="text",
            status="sent",
            created_at=datetime.utcnow()
        )
        db.add(msg)
        chat.updated_at = datetime.utcnow()
        await db.commit()

    except Exception as e:
        print(f"Aviso ao enviar boas-vindas do bot: {e}")

async def send_compliance_notice(db: AsyncSession, target_user: User, notice_text: str, category: str = "warning"):

    try:
        legal_bot = await get_or_create_compliance_bot(db)
        if target_user.id == legal_bot.id:
            return None

        s1 = select(ChatMember.chat_id).where(ChatMember.user_id == target_user.id)
        s2 = select(ChatMember.chat_id).where(ChatMember.user_id == legal_bot.id)
        chat = (await db.execute(select(Chat).where(and_(Chat.id.in_(s1), Chat.id.in_(s2), Chat.is_group == False)))).scalars().first()

        if not chat:
            channel_key = CryptoEngine.generate_random_key_hex()
            chat = Chat(
                is_group=False,
                title="Fechat Conformidade Legal & Segurança",
                aes_channel_key=channel_key
            )
            db.add(chat)
            await db.commit()
            await db.refresh(chat)

            db.add(ChatMember(chat_id=chat.id, user_id=legal_bot.id, role="admin"))
            db.add(ChatMember(chat_id=chat.id, user_id=target_user.id, role="member"))
            await db.commit()

        encrypted_data = CryptoEngine.encrypt_aes_gcm(notice_text, chat.aes_channel_key)

        msg = Message(
            chat_id=chat.id,
            sender_id=legal_bot.id,
            ciphertext=encrypted_data["ciphertext"],
            iv=encrypted_data["iv"],
            tag=encrypted_data["tag"],
            message_type="text",
            status="sent",
            created_at=datetime.utcnow()
        )
        db.add(msg)
        chat.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(msg)

        await ws_manager.broadcast_to_user(target_user.id, {
            "type": "new_message",
            "data": {
                "id": msg.id,
                "chat_id": chat.id,
                "sender_id": legal_bot.id,
                "ciphertext": msg.ciphertext,
                "iv": msg.iv,
                "tag": msg.tag,
                "message_type": msg.message_type,
                "status": "sent",
                "created_at": msg.created_at.isoformat(),
                "sender": {
                    "id": legal_bot.id,
                    "numeric_id": legal_bot.numeric_id,
                    "username": legal_bot.username,
                    "full_name": legal_bot.full_name,
                    "avatar_url": legal_bot.avatar_url,
                    "is_verified": True,
                    "is_bot": True
                }
            }
        })

        return msg
    except Exception as e:
        print(f"Erro ao enviar notificação de conformidade: {e}")
        return None

async def ensure_admin_user(db: AsyncSession) -> User:

    stmt = select(User).where(User.username == "admin")
    res = await db.execute(stmt)
    admin = res.scalars().first()

    if not admin:
        admin = User(
            numeric_id="403195052721",
            username="admin",
            email="admin@fechat.local",
            full_name="Oficial de Segurança & Compliance",
            password_hash=get_password_hash("admin123456"),
            bio="Painel de Segurança e Atendimento Judicial Fechat",
            language="pt_BR",
            theme="dark",
            is_active=True,
            is_admin=True,
            is_verified=True,
            is_bot=False
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
    else:
        changed = False
        if not admin.is_admin:
            admin.is_admin = True
            changed = True
        if not admin.is_verified:
            admin.is_verified = True
            changed = True
        if not admin.is_active:
            admin.is_active = True
            changed = True
        if changed:
            await db.commit()

    return admin
