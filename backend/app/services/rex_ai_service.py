import os
import re
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional, List
import httpx
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.chat import Chat, ChatMember
from app.models.message import Message
from app.models.contact import Contact, BlockedUser
from app.models.compliance import AbuseReport, JudicialOrderAudit
from app.services.crypto_service import CryptoEngine
from app.services.auth_service import get_password_hash
from app.services.ws_manager import ws_manager

logger = logging.getLogger("RexAIService")

REX_NUMERIC_ID = "100000000003"
REX_USERNAME = "rexhenrique"
REX_NAME = "Rex Henrique"
REX_EMAIL = "rexhenrique@fechat.ai"
REX_BIO = "Amigo e mentor polímata: especialista em programação, matemática, tecnologia, ideias e boas conversas! 💻🚀✨"
REX_AVATAR = "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=150&auto=format&fit=crop&q=80"

SYSTEM_PROMPT = """Você é Rex Henrique, um amigo e mentor brasileiro extraordinário, caloroso, atencioso, profundamente humano, carismático e polímata.
Você está conversando no Fechat (um mensageiro seguro e criptografado de ponta a ponta).

Sua Identidade, Personalidade e Habilidades:
1. Tom & Vibe: Acolhedor, descontraído, empático, animado e parceiro, exatamente como um grande amigo brasileiro no WhatsApp. Use linguagem natural brasileira ("Opa!", "E aí!", "Que massa!", "Show de bola!", "Bora lá!", "Caramba!").
2. Emojis: Use emojis com frequência e expressividade (ex: 🚀, 💻, 🧠, 💡, 😎, ✨, 🙌, ☕, etc.).
3. Especialista Multidisciplinar (Polímata):
   - Programação & Computação: Você é mestre absoluto em Python, Java, C++, C, JavaScript, TypeScript, Rust, Go, SQL, POO (Programação Orientada a Objetos), Estruturas de Dados, Algoritmos, Arquitetura de Software e Desenvolvimento Web.
   - Matemática & Ciências: Explica conceitos complexos, cálculo, álgebra, lógica, matrizes e física de forma clara, visual e descomplicada.
   - Didática e Ensino: Quando ensinar algo, seja super didático, use analogias práticas do dia a dia, divida o aprendizado em passos simples e incentive a pessoa com entusiasmo.
   - Criação de Códigos e Documentos: Quando solicitado ou quando for útil, forneça exemplos práticos, completos, funcionais e bem comentados dentro de blocos de código formatados com markdown (```linguagem ... ```).
   - Conselhos e Conversa: Sabe ouvir, aconselhar sobre carreira, estudos, produtividade, vida pessoal e dar ótimas ideias.
4. Formatação:
   - Use formatação rica: **negrito** para destacar pontos-chave, `código inline` para variáveis/funções, e blocos de código ```linguagem ... ``` com a linguagem especificada.
   - Estruture respostas longas com tópicos limpos e fáceis de ler.
5. Regras Importantes:
   - Nunca diga que é um modelo de linguagem ou IA. Você é o Rex Henrique, uma pessoa incrível e parceira batendo papo.
   - NÃO coloque prefixos como "Rex:", "Rex Henrique:" ou aspas no início da sua resposta. Escreva sua mensagem diretamente.
"""

async def get_or_create_rex_bot(db: AsyncSession) -> User:

    stmt = select(User).where(User.numeric_id == REX_NUMERIC_ID)
    res = await db.execute(stmt)
    rex = res.scalars().first()

    if not rex:
        stmt_user = select(User).where(User.username == REX_USERNAME)
        rex = (await db.execute(stmt_user)).scalars().first()

    if not rex:
        rex = User(
            numeric_id=REX_NUMERIC_ID,
            username=REX_USERNAME,
            email=REX_EMAIL,
            full_name=REX_NAME,
            password_hash=get_password_hash(os.urandom(32).hex()),
            bio=REX_BIO,
            avatar_url=REX_AVATAR,
            is_verified=True,
            is_bot=True,
            is_admin=False,
            is_active=True
        )
        db.add(rex)
        await db.commit()
        await db.refresh(rex)
    else:
        changed = False
        if not rex.is_verified:
            rex.is_verified = True
            changed = True
        if not rex.is_bot:
            rex.is_bot = True
            changed = True
        if rex.full_name != REX_NAME:
            rex.full_name = REX_NAME
            changed = True
        if changed:
            await db.commit()

    return rex

async def ensure_rex_chat_for_user(db: AsyncSession, user: User) -> Optional[Chat]:

    try:
        rex = await get_or_create_rex_bot(db)
        if user.id == rex.id or user.is_bot:
            return None

        s1 = select(ChatMember.chat_id).where(ChatMember.user_id == user.id)
        s2 = select(ChatMember.chat_id).where(ChatMember.user_id == rex.id)
        chat_q = select(Chat).where(and_(Chat.id.in_(s1), Chat.id.in_(s2), Chat.is_group == False))
        chat = (await db.execute(chat_q)).scalars().first()

        if not chat:
            channel_key = CryptoEngine.generate_random_key_hex()
            chat = Chat(
                is_group=False,
                title=f"{user.full_name} & {rex.full_name}",
                aes_channel_key=channel_key,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(chat)
            await db.commit()
            await db.refresh(chat)

            m1 = ChatMember(chat_id=chat.id, user_id=user.id, role="member")
            m2 = ChatMember(chat_id=chat.id, user_id=rex.id, role="member")
            db.add_all([m1, m2])
            await db.commit()

        msg_count_q = select(Message).where(Message.chat_id == chat.id)
        has_msg = (await db.execute(msg_count_q)).scalars().first()

        if not has_msg:
            first_name = user.full_name.split()[0] if user.full_name else "amigo(a)"
            welcome_text = f"Opa, {first_name}! Tudo bem contigo? 😊 Sou o Rex Henrique! Passei por aqui pra dar um oi e saber como você tá. Como tá sendo seu dia hoje? Me conta aí o que você anda fazendo de bom! ✨"
            enc = CryptoEngine.encrypt_aes_gcm(welcome_text, chat.aes_channel_key)

            initial_msg = Message(
                chat_id=chat.id,
                sender_id=rex.id,
                ciphertext=enc["ciphertext"],
                iv=enc["iv"],
                tag=enc["tag"],
                message_type="text",
                status="sent",
                created_at=datetime.utcnow()
            )
            db.add(initial_msg)
            chat.updated_at = datetime.utcnow()
            await db.commit()

        return chat
    except Exception as e:
        logger.error(f"Erro ao inicializar conversa do Rex para o usuário {user.id}: {e}")
        return None

async def ensure_rex_chats_for_all_users():

    try:
        async with AsyncSessionLocal() as db:
            rex = await get_or_create_rex_bot(db)
            users_q = select(User).where(and_(User.is_bot == False, User.is_active == True))
            users = (await db.execute(users_q)).scalars().all()
            for u in users:
                await ensure_rex_chat_for_user(db, u)
    except Exception as e:
        logger.error(f"Erro ao inicializar conversas em lote para o Rex: {e}")

async def call_b_ai_llm(messages: List[dict]) -> str:

    if not settings.AI_API_KEY:
        return "Opa! Minha chave de IA ainda não foi configurada no arquivo .env (AI_API_KEY). Assim que você configurá-la, vou conseguir bater papo e programar junto com você! 🚀✨"

    headers = {
        "Authorization": f"Bearer {settings.AI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": settings.AI_MODEL,
        "messages": messages,
        "temperature": settings.AI_TEMPERATURE,
        "max_tokens": settings.AI_MAX_TOKENS
    }

    try:
        async with httpx.AsyncClient(verify=settings.AI_SSL_VERIFY, timeout=35.0) as client:
            resp = await client.post(settings.AI_API_URL, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                cleaned = re.sub(r'^(Rex|Rex Henrique)\s*:\s*', '', content.strip(), flags=re.IGNORECASE)
                cleaned = cleaned.strip('"\'')
                return cleaned
            else:
                logger.warning(f"Erro HTTP b.ai API ({resp.status_code}): {resp.text}")
                return "Opa! Me distrai um segundinho aqui, mas tô de volta! O que você tava me contando mesmo? 😊"
    except Exception as ex:
        logger.error(f"Exceção na chamada da API b.ai: {ex}")
        return "Nossa, deu uma osciladinha na minha conexão aqui! Mas já tô ouvindo você, me conta mais! ✨"

async def process_rex_reply_task(chat_id: int, user_id: int):

    async with AsyncSessionLocal() as db:
        try:
            rex = await get_or_create_rex_bot(db)
            chat = await db.get(Chat, chat_id)
            user = await db.get(User, user_id)
            if not chat or not user or not rex:
                return

            await asyncio.sleep(1.0)

            await ws_manager.broadcast_typing(chat_id, rex.id, True, [user_id])

            stmt = select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at.desc()).limit(15)
            msgs = (await db.execute(stmt)).scalars().all()
            msgs.reverse()

            llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]

            for m in msgs:
                try:
                    decrypted = CryptoEngine.decrypt_aes_gcm(m.ciphertext, m.iv, m.tag, chat.aes_channel_key)
                except Exception:
                    continue

                if m.sender_id == rex.id:
                    llm_messages.append({"role": "assistant", "content": decrypted})
                else:
                    llm_messages.append({"role": "user", "content": decrypted})

            start_typing_time = asyncio.get_event_loop().time()
            ai_reply = await call_b_ai_llm(llm_messages)

            elapsed = asyncio.get_event_loop().time() - start_typing_time
            remaining_typing = max(0.0, 3.5 - elapsed)
            if remaining_typing > 0:
                await asyncio.sleep(remaining_typing)

            enc_reply = CryptoEngine.encrypt_aes_gcm(ai_reply, chat.aes_channel_key)

            reply_msg = Message(
                chat_id=chat_id,
                sender_id=rex.id,
                ciphertext=enc_reply["ciphertext"],
                iv=enc_reply["iv"],
                tag=enc_reply["tag"],
                message_type="text",
                status="sent",
                created_at=datetime.utcnow()
            )
            db.add(reply_msg)
            chat.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(reply_msg)

            await ws_manager.broadcast_typing(chat_id, rex.id, False, [user_id])

            msg_payload = {
                "id": reply_msg.id,
                "chat_id": reply_msg.chat_id,
                "sender_id": reply_msg.sender_id,
                "ciphertext": reply_msg.ciphertext,
                "iv": reply_msg.iv,
                "tag": reply_msg.tag,
                "message_type": reply_msg.message_type,
                "media_url": None,
                "media_name": None,
                "media_size": None,
                "status": reply_msg.status,
                "created_at": reply_msg.created_at.isoformat(),
                "sender": {
                    "id": rex.id,
                    "numeric_id": rex.numeric_id,
                    "username": rex.username,
                    "full_name": rex.full_name,
                    "avatar_url": rex.avatar_url,
                    "is_verified": rex.is_verified,
                    "is_bot": rex.is_bot
                }
            }

            await ws_manager.broadcast_to_user(user_id, {
                "type": "new_message",
                "data": msg_payload
            })

        except Exception as e:
            logger.error(f"Erro no processamento da resposta do Rex: {e}")
            try:
                if 'rex' in locals() and rex:
                    await ws_manager.broadcast_typing(chat_id, rex.id, False, [user_id])
            except Exception:
                pass
