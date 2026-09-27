import asyncio
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

import app.models.user
import app.models.chat
import app.models.message
import app.models.contact
import app.models.compliance

from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.chat import Chat, ChatMember
from app.models.message import Message
from app.services.crypto_service import CryptoEngine
from app.services.rex_ai_service import (
    get_or_create_rex_bot,
    ensure_rex_chat_for_user,
    ensure_rex_chats_for_all_users,
    process_rex_reply_task,
    call_b_ai_llm
)
from sqlalchemy import select, and_, delete

async def test_rex_ai():
    print("=== TESTE DO COMPANHEIRO IA REX HENRIQUE (b.ai DeepSeek v4 Flash) ===")

    async with AsyncSessionLocal() as db:
        rex = await get_or_create_rex_bot(db)
        assert rex is not None, "Rex Henrique deve existir"
        assert rex.full_name == "Rex Henrique", f"Nome incorreto: {rex.full_name}"
        assert rex.is_verified is True, "Rex deve possuir selo de verificado"
        assert rex.is_bot is True, "Rex deve ser marcado como bot"
        print(f"✅ 1. Rex Henrique validado com sucesso! Nome: {rex.full_name}, Verificado: {rex.is_verified}")

        stmt_user = select(User).where(User.is_bot == False).limit(1)
        user = (await db.execute(stmt_user)).scalars().first()
        assert user is not None, "Usuário de teste deve existir"
        print(f"✅ 2. Usuário de teste selecionado: {user.full_name} (ID: {user.id})")

        s1 = select(ChatMember.chat_id).where(ChatMember.user_id == user.id)
        s2 = select(ChatMember.chat_id).where(ChatMember.user_id == rex.id)
        old_chats = (await db.execute(select(Chat).where(and_(Chat.id.in_(s1), Chat.id.in_(s2), Chat.is_group == False)))).scalars().all()
        for oc in old_chats:
            await db.execute(delete(Message).where(Message.chat_id == oc.id))
            await db.execute(delete(ChatMember).where(ChatMember.chat_id == oc.id))
            await db.execute(delete(Chat).where(Chat.id == oc.id))
        await db.commit()

        chat = await ensure_rex_chat_for_user(db, user)
        assert chat is not None, "Chat com Rex deve ser criado"
        print(f"✅ 3. Conversa com Rex Henrique garantida! Chat ID: {chat.id}")

        stmt_msgs = select(Message).where(Message.chat_id == chat.id).order_by(Message.created_at.asc())
        msgs = (await db.execute(stmt_msgs)).scalars().all()
        assert len(msgs) >= 1, "Deve haver ao menos uma mensagem inicial"
        first_msg = msgs[0]
        assert first_msg.sender_id == rex.id, "Remetente da mensagem inicial deve ser o Rex"

        decrypted_first = CryptoEngine.decrypt_aes_gcm(
            first_msg.ciphertext, first_msg.iv, first_msg.tag, chat.aes_channel_key
        )
        print(f"✅ 4. Mensagem inicial descriptografada: '{decrypted_first}'")

        user_text = "Oi Rex! Hoje meu dia foi meio corrido no trabalho, mas agora tô relaxando ouvindo uma musiquinha boa. E você, o que tá aprontando?"
        cipher, iv, tag = CryptoEngine.encrypt_aes_gcm(user_text, chat.aes_channel_key)
        user_msg = Message(
            chat_id=chat.id,
            sender_id=user.id,
            ciphertext=cipher,
            iv=iv,
            tag=tag,
            message_type="text",
            status="sent"
        )
        db.add(user_msg)
        await db.commit()
        print(f"✅ 5. Mensagem do usuário enviada para Rex: '{user_text}'")

    print("⏳ 6. Solicitando resposta inteligente e humana do Rex Henrique via b.ai...")
    await process_rex_reply_task(chat.id, user.id)

    async with AsyncSessionLocal() as db:
        stmt_last = select(Message).where(Message.chat_id == chat.id).order_by(Message.created_at.desc()).limit(1)
        last_msg = (await db.execute(stmt_last)).scalars().first()
        assert last_msg.sender_id == rex.id, "Última mensagem deve ter sido enviada por Rex Henrique"

        decrypted_reply = CryptoEngine.decrypt_aes_gcm(
            last_msg.ciphertext, last_msg.iv, last_msg.tag, chat.aes_channel_key
        )
        print(f"🎉 7. Resposta recebida do Rex Henrique:\n👉 '{decrypted_reply}'\n")

    print("🎉 TODOS OS TESTES DO REX HENRIQUE PASSARAM COM 100% DE SUCESSO!")

if __name__ == "__main__":
    asyncio.run(test_rex_ai())
