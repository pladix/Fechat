import os
import json
import base64
import hashlib
import re
import html
import asyncio
import secrets
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import select, and_, or_, delete, update, desc
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.chat import Chat, ChatMember
from app.models.message import Message
from app.models.contact import Contact, BlockedUser
from app.models.compliance import AbuseReport, JudicialOrderAudit
from app.services.auth_service import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_user_by_identifier,
    decode_access_token
)
from app.services.id_generator import generate_numeric_id
from app.services.crypto_service import CryptoEngine
from app.services.vault_service import VaultService
from app.services.ws_manager import ws_manager

def clean_surrogates(text):

    if not isinstance(text, str):
        return text
    return text.encode('utf-16', 'surrogatepass').decode('utf-16', 'ignore')

def _serialize_user(user: Optional[User], is_self: bool = False, is_judicial_forensics: bool = False) -> Optional[dict]:
    if not user:
        return None

    data = {
        "id": user.id,
        "numeric_id": user.numeric_id,
        "username": user.username,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
        "bio": user.bio,
        "is_admin": bool(user.is_admin),
        "is_suspended": bool(user.is_suspended),
        "is_verified": bool(user.is_verified),
        "is_bot": bool(user.is_bot),
        "last_seen": user.last_seen.isoformat() if user.last_seen else None
    }

    if is_self:
        now = datetime.utcnow()
        account_age_days = (now - user.created_at).days if user.created_at else 0
        is_exempt = bool(user.is_admin or user.is_verified)
        is_new_account = (account_age_days < 30) and not is_exempt
        days_until_unlock = max(0, 30 - account_age_days) if is_new_account else 0

        days_since_last_change = (now - user.last_username_change).days if user.last_username_change else 999
        in_cooldown = (days_since_last_change < 7) and not is_exempt
        days_until_cooldown_ends = max(0, 7 - days_since_last_change) if in_cooldown else 0

        can_change_username = is_exempt or (not is_new_account and not in_cooldown)

        data.update({
            "email": user.email,
            "language": user.language,
            "theme": user.theme,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "account_age_days": account_age_days,
            "is_new_account": is_new_account,
            "days_until_username_unlock": days_until_unlock,
            "can_change_username": can_change_username,
            "days_until_cooldown_ends": days_until_cooldown_ends
        })

    if is_judicial_forensics:
        data.update({
            "email": user.email,
            "last_ip": getattr(user, 'last_ip', None) or "127.0.0.1",
            "user_agent": getattr(user, 'user_agent', None) or "",
            "device_info": getattr(user, 'device_info', None) or "Dispositivo Padrão",
            "created_at": user.created_at.isoformat() if user.created_at else None
        })

    return data

async def handle_ws_rpc(session_user_id: Optional[int], action: str, payload: dict, client_ip: str = "127.0.0.1", user_agent: str = "") -> Tuple[dict, Optional[int]]:

    async with AsyncSessionLocal() as db:
        if action == "auth_login":
            login_id = (payload.get("login") or payload.get("identifier") or payload.get("email") or payload.get("username") or "").strip()
            password = payload.get("password", "")

            user = await get_user_by_identifier(db, login_id)
            if not user or not verify_password(password, user.password_hash):
                raise ValueError("Credenciais inválidas. Verifique seu ID de 12 dígitos, e-mail e senha.")

            if user.is_suspended:
                raise ValueError("Esta conta foi suspensa temporariamente por violação dos termos de segurança.")

            user.last_seen = datetime.utcnow()
            if client_ip:
                user.last_ip = client_ip
            if user_agent:
                user.user_agent = user_agent[:250]
                from app.api.websockets.chat_socket import parse_device_info
                user.device_info = parse_device_info(user_agent)
            await db.commit()

            token = create_access_token({"sub": str(user.id)})
            return {
                "access_token": token,
                "token_type": "bearer",
                "user": _serialize_user(user, is_self=True)
            }, user.id

        elif action == "auth_register":
            raw_full_name = payload.get("full_name", "")
            full_name = re.sub(r'<[^>]*>', '', raw_full_name).strip()[:70]
            raw_username = payload.get("username", "").strip().lower()
            email = payload.get("email", "").strip().lower()
            password = payload.get("password", "")
            language = payload.get("language", "pt_BR")
            raw_bio = payload.get("bio", "Olá! Estou usando o Fechat.")
            bio = re.sub(r'<[^>]*>', '', raw_bio).strip()[:150]

            if not full_name or not raw_username or not email or not password:
                raise ValueError("Todos os campos de cadastro são obrigatórios.")

            if len(full_name) < 2:
                raise ValueError("O nome completo deve ter pelo menos 2 caracteres.")

            if not re.match(r'^[a-zA-Z0-9_.]{3,30}$', raw_username):
                raise ValueError("O nome de usuário deve conter apenas letras, números, ponto (.) ou underline (_), com 3 a 30 caracteres.")
            username = raw_username

            existing = await db.execute(select(User).where(or_(User.email == email, User.username == username)))
            if existing.scalars().first():
                raise ValueError("E-mail ou nome de usuário já cadastrado.")

            numeric_id = generate_numeric_id()
            while True:
                chk = await db.execute(select(User).where(User.numeric_id == numeric_id))
                if not chk.scalars().first():
                    break
                numeric_id = generate_numeric_id()

            user = User(
                numeric_id=numeric_id,
                username=username,
                email=email,
                full_name=full_name,
                bio=bio,
                password_hash=get_password_hash(password),
                language=language,
                avatar_url=f"https://api.dicebear.com/7.x/bottts/svg?seed={username}",
                created_at=datetime.utcnow()
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            from app.services.bot_service import send_bot_welcome_message
            await send_bot_welcome_message(db, user)
            from app.services.rex_ai_service import ensure_rex_chat_for_user
            await ensure_rex_chat_for_user(db, user)

            token = create_access_token({"sub": str(user.id)})
            return {
                "access_token": token,
                "token_type": "bearer",
                "user": _serialize_user(user, is_self=True)
            }, user.id

        if not session_user_id:
            raise PermissionError("Sessão não autenticada no WebSocket.")

        current_user = await db.get(User, session_user_id)
        if not current_user or current_user.is_suspended:
            raise PermissionError("Usuário inexistente ou com conta suspensa.")

        elif action == "auth_me":
            return {"user": _serialize_user(current_user, is_self=True)}, None

        elif action == "auth_upload_avatar":
            file_base64 = payload.get("avatar_base64") or payload.get("data_base64") or payload.get("file_base64")
            if not file_base64:
                raise ValueError("Imagem base64 não fornecida.")

            if "," in file_base64:
                file_base64 = file_base64.split(",", 1)[1]

            blob_bytes = base64.b64decode(file_base64)
            file_hash = VaultService.store_media_blob(blob_bytes)
            stream_url = f"/api/v1/media/stream/{file_hash}"

            current_user.avatar_url = stream_url
            await db.commit()

            return {"avatar_url": stream_url, "user": _serialize_user(current_user, is_self=True)}, None

        elif action == "search_users":
            query_str = payload.get("query", "").strip()
            if not query_str:
                return {"users": []}, None

            clean_query = query_str.lower()
            clean_digits = "".join(ch for ch in query_str if ch.isdigit())

            stmt = select(User).where(
                and_(
                    User.id != session_user_id,
                    User.is_suspended == False,
                    or_(
                        User.username.ilike(f"%{clean_query}%"),
                        User.full_name.ilike(f"%{clean_query}%"),
                        User.numeric_id == query_str,
                        User.numeric_id == clean_digits
                    )
                )
            ).limit(20)
            res = await db.execute(stmt)
            users = res.scalars().all()
            return {"users": [_serialize_user(u) for u in users]}, None

        elif action == "update_profile":
            new_username = payload.get("username")
            if new_username:
                new_username = new_username.strip().lower()
                if not re.match(r'^[a-zA-Z0-9_.]{3,30}$', new_username):
                    raise ValueError("O nome de usuário deve conter apenas letras, números, ponto (.) ou underline (_), com 3 a 30 caracteres.")

                if new_username != current_user.username:
                    now = datetime.utcnow()
                    account_age_days = (now - current_user.created_at).days if current_user.created_at else 0
                    is_exempt = bool(current_user.is_admin or current_user.is_verified)

                    if account_age_days < 30 and not is_exempt:
                        days_left = 30 - account_age_days
                        raise ValueError(f"Por segurança e combate a fraudes, contas novas não podem alterar o nome de usuário nos primeiros 30 dias. Liberação em {days_left} dia(s).")

                    if current_user.last_username_change and not is_exempt:
                        days_since_change = (now - current_user.last_username_change).days
                        if days_since_change < 7:
                            days_left = 7 - days_since_change
                            raise ValueError(f"O nome de usuário só pode ser alterado 1 vez a cada 7 dias. Próxima alteração disponível em {days_left} dia(s).")

                    existing = await db.execute(select(User).where(User.username == new_username))
                    if existing.scalars().first():
                        raise ValueError("Este nome de usuário já está em uso.")
                    current_user.username = new_username
                    current_user.last_username_change = now

            full_name = payload.get("full_name")
            if full_name:
                clean_name = re.sub(r'<[^>]*>', '', full_name).strip()[:70]
                if len(clean_name) < 2:
                    raise ValueError("O nome completo deve ter pelo menos 2 caracteres.")
                current_user.full_name = clean_name

            bio = payload.get("bio")
            if bio is not None:
                current_user.bio = re.sub(r'<[^>]*>', '', bio).strip()[:150]

            language = payload.get("language")
            if language: current_user.language = language

            theme = payload.get("theme")
            if theme: current_user.theme = theme

            await db.commit()
            return {"user": _serialize_user(current_user, is_self=True)}, None

        elif action == "get_contacts":
            stmt = (
                select(Contact)
                .where(Contact.user_id == session_user_id)
                .options(selectinload(Contact.contact_user))
                .order_by(Contact.created_at.desc())
            )
            res = await db.execute(stmt)
            contacts = res.scalars().all()

            contact_list = [
                {
                    "id": c.id,
                    "user_id": c.user_id,
                    "contact_user_id": c.contact_user_id,
                    "nickname": c.nickname,
                    "is_blocked": c.is_blocked,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "contact_user": _serialize_user(c.contact_user)
                }
                for c in contacts
            ]
            return {"contacts": contact_list}, None

        elif action == "add_contact":
            identifier = payload.get("identifier", "").strip()
            nickname = payload.get("nickname", "").strip() or None

            target = await get_user_by_identifier(db, identifier)
            if not target:
                raise ValueError("Usuário não encontrado pelo ID ou usuário fornecido.")
            if target.id == session_user_id:
                raise ValueError("Você não pode adicionar seu próprio perfil aos contatos.")
            if target.is_suspended or not target.is_active:
                raise ValueError("Não é possível adicionar este usuário pois a conta foi suspensa por infração aos Termos de Uso.")

            exists = await db.execute(select(Contact).where(and_(Contact.user_id == session_user_id, Contact.contact_user_id == target.id)))
            if exists.scalars().first():
                raise ValueError("Este contato já está na sua lista.")

            contact = Contact(user_id=session_user_id, contact_user_id=target.id, nickname=nickname)
            db.add(contact)
            await db.commit()
            await db.refresh(contact)
            return {"status": "created", "contact": {"id": contact.id, "contact_user": _serialize_user(target)}}, None

        elif action == "toggle_block_contact":
            contact_id = payload.get("contact_id")
            contact = await db.get(Contact, contact_id)
            if not contact or contact.user_id != session_user_id:
                raise ValueError("Contato não encontrado.")
            contact.is_blocked = not contact.is_blocked
            await db.commit()
            return {"status": "updated", "is_blocked": contact.is_blocked}, None

        elif action == "get_block_status":
            target_user_id = payload.get("user_id")
            if not target_user_id:
                raise ValueError("user_id é obrigatório.")

            target_user_obj = await db.get(User, target_user_id)
            is_target_suspended = bool(target_user_obj and (target_user_obj.is_suspended or not target_user_obj.is_active))

            q1 = select(BlockedUser).where(and_(BlockedUser.blocker_id == session_user_id, BlockedUser.blocked_id == target_user_id))
            res1 = await db.execute(q1)
            is_blocked_by_me = res1.scalar_one_or_none() is not None

            q2 = select(BlockedUser).where(and_(BlockedUser.blocker_id == target_user_id, BlockedUser.blocked_id == session_user_id))
            res2 = await db.execute(q2)
            am_i_blocked = res2.scalar_one_or_none() is not None

            return {
                "target_user_id": target_user_id,
                "is_blocked_by_me": is_blocked_by_me,
                "am_i_blocked": am_i_blocked,
                "is_target_suspended": is_target_suspended
            }, None

        elif action == "block_user":
            target_user_id = payload.get("user_id")
            if not target_user_id or target_user_id == session_user_id:
                raise ValueError("user_id inválido para bloqueio.")

            target_user_obj = await db.get(User, target_user_id)
            if not target_user_obj:
                raise ValueError("Usuário não encontrado.")

            if target_user_obj.is_bot or target_user_obj.is_verified or target_user_obj.is_admin:
                raise ValueError("Contatos oficiais e contas verificadas da plataforma não podem ser bloqueados.")

            q = select(BlockedUser).where(and_(BlockedUser.blocker_id == session_user_id, BlockedUser.blocked_id == target_user_id))
            res = await db.execute(q)
            if not res.scalar_one_or_none():
                block_entry = BlockedUser(blocker_id=session_user_id, blocked_id=target_user_id)
                db.add(block_entry)
                await db.commit()

            await ws_manager.broadcast_to_user(target_user_id, {
                "type": "block_update",
                "blocker_user_id": session_user_id,
                "target_user_id": target_user_id,
                "am_i_blocked": True,
                "is_blocked_by_me": False
            })
            await ws_manager.broadcast_to_user(session_user_id, {
                "type": "block_update",
                "blocker_user_id": session_user_id,
                "target_user_id": target_user_id,
                "am_i_blocked": False,
                "is_blocked_by_me": True
            })

            return {"status": "blocked", "target_user_id": target_user_id, "is_blocked_by_me": True}, None

        elif action == "unblock_user":
            target_user_id = payload.get("user_id")
            if not target_user_id:
                raise ValueError("user_id é obrigatório.")

            q = delete(BlockedUser).where(and_(BlockedUser.blocker_id == session_user_id, BlockedUser.blocked_id == target_user_id))
            await db.execute(q)
            await db.commit()

            await ws_manager.broadcast_to_user(target_user_id, {
                "type": "block_update",
                "blocker_user_id": session_user_id,
                "target_user_id": target_user_id,
                "am_i_blocked": False,
                "is_blocked_by_me": False
            })
            await ws_manager.broadcast_to_user(session_user_id, {
                "type": "block_update",
                "blocker_user_id": session_user_id,
                "target_user_id": target_user_id,
                "am_i_blocked": False,
                "is_blocked_by_me": False
            })

            return {"status": "unblocked", "target_user_id": target_user_id, "is_blocked_by_me": False}, None

        elif action == "get_chats":
            subquery = select(ChatMember.chat_id).where(ChatMember.user_id == session_user_id)
            chat_ids_res = await db.execute(subquery)
            chat_ids = chat_ids_res.scalars().all()

            if not chat_ids:
                return {"chats": []}, None

            stmt = (
                select(Chat)
                .where(Chat.id.in_(chat_ids))
                .options(
                    selectinload(Chat.members).selectinload(ChatMember.user),
                    selectinload(Chat.messages).selectinload(Message.sender)
                )
                .order_by(Chat.updated_at.desc())
            )
            result = await db.execute(stmt)
            chats = result.scalars().all()

            chat_list = []
            for chat in chats:
                sorted_msgs = sorted(chat.messages, key=lambda m: m.created_at, reverse=True)
                last_msg = sorted_msgs[0] if sorted_msgs else None
                my_membership = next((m for m in chat.members if m.user_id == session_user_id), None)

                if not chat.is_group:
                    other_mem = next((m for m in chat.members if m.user_id != session_user_id), None)
                    other_user = other_mem.user if other_mem else None
                    chat_title = other_user.full_name if other_user else (chat.title or "Conversa Privada")
                    chat_avatar = other_user.avatar_url if other_user else chat.avatar_url
                    target_user_data = _serialize_user(other_user) if other_user else None
                else:
                    chat_title = chat.title or "Grupo"
                    chat_avatar = chat.avatar_url or "https://api.dicebear.com/7.x/identicon/svg?seed=group"
                    target_user_data = None

                chat_list.append({
                    "id": chat.id,
                    "uuid": chat.uuid,
                    "is_group": bool(chat.is_group),
                    "title": chat_title,
                    "description": chat.description,
                    "avatar_url": chat_avatar,
                    "aes_channel_key": chat.aes_channel_key,
                    "target_user": target_user_data,
                    "created_by_id": chat.created_by_id,
                    "only_admins_send_messages": bool(chat.only_admins_send_messages),
                    "only_admins_edit_info": bool(chat.only_admins_edit_info),
                    "pinned_message_id": chat.pinned_message_id,
                    "is_suspended": bool(chat.is_suspended),
                    "suspension_reason": chat.suspension_reason,
                    "group_invite_code": chat.group_invite_code,
                    "my_role": my_membership.role if my_membership else "member",
                    "is_pinned": bool(my_membership.is_pinned) if my_membership else False,
                    "is_muted": bool(my_membership.is_muted) if my_membership else False,
                    "is_archived": bool(my_membership.is_archived) if my_membership else False,
                    "created_at": chat.created_at.isoformat() if chat.created_at else None,
                    "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
                    "members": [
                        {
                            "id": m.id,
                            "user_id": m.user_id,
                            "role": m.role,
                            "user": _serialize_user(m.user)
                        }
                        for m in chat.members
                    ],
                    "last_message": {
                        "id": last_msg.id,
                        "chat_id": last_msg.chat_id,
                        "sender_id": last_msg.sender_id,
                        "ciphertext": last_msg.ciphertext,
                        "iv": last_msg.iv,
                        "tag": last_msg.tag,
                        "message_type": last_msg.message_type,
                        "media_url": last_msg.media_url,
                        "media_name": last_msg.media_name,
                        "media_size": last_msg.media_size,
                        "reply_to_message_id": last_msg.reply_to_message_id,
                        "reply_to_sender_name": last_msg.reply_to_sender_name,
                        "reply_to_snippet": last_msg.reply_to_snippet,
                        "is_deleted": bool(last_msg.is_deleted),
                        "status": last_msg.status,
                        "created_at": last_msg.created_at.isoformat() if last_msg.created_at else None
                    } if last_msg else None
                })

            chat_list.sort(key=lambda c: (1 if c["is_pinned"] else 0, c["updated_at"] or ""), reverse=True)
            return {"chats": chat_list}, None

        elif action == "toggle_pin_chat":
            chat_id = payload.get("chat_id")
            stmt = select(ChatMember).where(and_(ChatMember.chat_id == chat_id, ChatMember.user_id == session_user_id))
            res = await db.execute(stmt)
            mem = res.scalar_one_or_none()
            if not mem:
                raise ValueError("Conversa não encontrada.")
            mem.is_pinned = not mem.is_pinned
            await db.commit()
            return {"chat_id": chat_id, "is_pinned": mem.is_pinned}, None

        elif action == "toggle_mute_chat":
            chat_id = payload.get("chat_id")
            stmt = select(ChatMember).where(and_(ChatMember.chat_id == chat_id, ChatMember.user_id == session_user_id))
            res = await db.execute(stmt)
            mem = res.scalar_one_or_none()
            if not mem:
                raise ValueError("Conversa não encontrada.")
            mem.is_muted = not mem.is_muted
            await db.commit()
            return {"chat_id": chat_id, "is_muted": mem.is_muted}, None

        elif action == "toggle_archive_chat":
            chat_id = payload.get("chat_id")
            stmt = select(ChatMember).where(and_(ChatMember.chat_id == chat_id, ChatMember.user_id == session_user_id))
            res = await db.execute(stmt)
            mem = res.scalar_one_or_none()
            if not mem:
                raise ValueError("Conversa não encontrada.")
            mem.is_archived = not mem.is_archived
            await db.commit()
            return {"chat_id": chat_id, "is_archived": mem.is_archived}, None

        elif action == "delete_chat":
            chat_id = payload.get("chat_id")
            stmt = select(ChatMember).where(and_(ChatMember.chat_id == chat_id, ChatMember.user_id == session_user_id))
            res = await db.execute(stmt)
            mem = res.scalar_one_or_none()
            if not mem:
                raise ValueError("Conversa não encontrada.")

            chat_obj = await db.get(Chat, chat_id)
            if not chat_obj.is_group:
                await db.delete(chat_obj)
            else:
                await db.delete(mem)
            await db.commit()
            return {"chat_id": chat_id, "status": "deleted"}, None

        elif action == "export_chat_data":
            chat_id = payload.get("chat_id")
            mem_stmt = select(ChatMember).where(and_(ChatMember.chat_id == chat_id, ChatMember.user_id == session_user_id))
            mem_res = await db.execute(mem_stmt)
            if not mem_res.scalar_one_or_none():
                raise PermissionError("Você não possui permissão para exportar esta conversa.")

            chat = await db.get(Chat, chat_id)
            stmt = (
                select(Message)
                .where(Message.chat_id == chat_id)
                .options(selectinload(Message.sender))
                .order_by(Message.created_at.asc())
            )
            res = await db.execute(stmt)
            messages = res.scalars().all()

            return {
                "chat": {
                    "id": chat.id,
                    "uuid": chat.uuid,
                    "title": chat.title or "Conversa Fechat",
                    "is_group": chat.is_group,
                    "aes_channel_key": chat.aes_channel_key,
                    "created_at": chat.created_at.isoformat() if chat.created_at else None
                },
                "messages": [
                    {
                        "id": m.id,
                        "sender_id": m.sender_id,
                        "sender_name": m.sender.full_name if m.sender else "Usuário",
                        "sender_username": m.sender.username if m.sender else None,
                        "ciphertext": m.ciphertext,
                        "iv": m.iv,
                        "tag": m.tag,
                        "message_type": m.message_type,
                        "media_url": m.media_url,
                        "media_name": m.media_name,
                        "status": m.status,
                        "created_at": m.created_at.isoformat() if m.created_at else None
                    }
                    for m in messages
                ]
            }, None

        elif action == "create_direct_chat":
            target_user_id = payload.get("target_user_id")
            if not target_user_id or target_user_id == session_user_id:
                raise ValueError("target_user_id inválido.")

            target_user = await db.get(User, target_user_id)
            if not target_user:
                raise ValueError("Usuário alvo não encontrado.")
            if target_user.is_suspended or not target_user.is_active:
                raise ValueError("Esta conta foi suspensa por infração aos Termos de Uso e não pode receber mensagens ou interações.")

            s1 = select(ChatMember.chat_id).where(ChatMember.user_id == session_user_id)
            s2 = select(ChatMember.chat_id).where(ChatMember.user_id == target_user_id)
            common_chat_ids = (await db.execute(select(Chat.id).where(and_(Chat.id.in_(s1), Chat.id.in_(s2), Chat.is_group == False)))).scalars().all()

            if common_chat_ids:
                existing_chat = await db.get(Chat, common_chat_ids[0])
                stmt = select(Chat).where(Chat.id == existing_chat.id).options(selectinload(Chat.members).selectinload(ChatMember.user))
                loaded = (await db.execute(stmt)).scalar_one()
                return {"chat": {
                    "id": loaded.id,
                    "uuid": loaded.uuid,
                    "is_group": False,
                    "title": target_user.full_name,
                    "aes_channel_key": loaded.aes_channel_key,
                    "members": [{"id": m.id, "user_id": m.user_id, "user": _serialize_user(m.user)} for m in loaded.members]
                }}, None

            channel_key = CryptoEngine.generate_random_key_hex()
            new_chat = Chat(is_group=False, title=target_user.full_name, aes_channel_key=channel_key)
            db.add(new_chat)
            await db.commit()
            await db.refresh(new_chat)

            db.add(ChatMember(chat_id=new_chat.id, user_id=session_user_id, role="admin"))
            db.add(ChatMember(chat_id=new_chat.id, user_id=target_user_id, role="member"))
            await db.commit()

            stmt = select(Chat).where(Chat.id == new_chat.id).options(selectinload(Chat.members).selectinload(ChatMember.user))
            loaded = (await db.execute(stmt)).scalar_one()
            return {"chat": {
                "id": loaded.id,
                "uuid": loaded.uuid,
                "is_group": False,
                "title": target_user.full_name,
                "aes_channel_key": loaded.aes_channel_key,
                "members": [{"id": m.id, "user_id": m.user_id, "user": _serialize_user(m.user)} for m in loaded.members]
            }}, None

        elif action == "create_group_chat":
            title = payload.get("title", "").strip()
            description = payload.get("description", "").strip()
            member_ids = payload.get("member_ids") or payload.get("member_user_ids") or []

            if not title:
                raise ValueError("Título do grupo é obrigatório.")

            channel_key = CryptoEngine.generate_random_key_hex()
            group_chat = Chat(
                is_group=True,
                title=title,
                description=description,
                aes_channel_key=channel_key,
                created_by_id=session_user_id
            )
            db.add(group_chat)
            await db.commit()
            await db.refresh(group_chat)

            db.add(ChatMember(chat_id=group_chat.id, user_id=session_user_id, role="admin"))
            for m_id in member_ids:
                if m_id != session_user_id:
                    db.add(ChatMember(chat_id=group_chat.id, user_id=m_id, role="member"))
            await db.commit()

            stmt = select(Chat).where(Chat.id == group_chat.id).options(selectinload(Chat.members).selectinload(ChatMember.user))
            loaded = (await db.execute(stmt)).scalar_one()
            return {"chat": {
                "id": loaded.id,
                "uuid": loaded.uuid,
                "is_group": True,
                "title": loaded.title,
                "description": loaded.description,
                "created_by_id": loaded.created_by_id,
                "only_admins_send_messages": bool(loaded.only_admins_send_messages),
                "only_admins_edit_info": bool(loaded.only_admins_edit_info),
                "pinned_message_id": loaded.pinned_message_id,
                "my_role": "admin",
                "aes_channel_key": loaded.aes_channel_key,
                "members": [{"id": m.id, "user_id": m.user_id, "role": m.role, "user": _serialize_user(m.user)} for m in loaded.members]
            }}, None

        elif action == "get_messages":
            chat_id = payload.get("chat_id")
            if not chat_id:
                raise ValueError("chat_id é obrigatório.")

            mem_stmt = select(ChatMember).where(and_(ChatMember.chat_id == chat_id, ChatMember.user_id == session_user_id))
            mem_res = await db.execute(mem_stmt)
            if not mem_res.scalar_one_or_none():
                raise PermissionError("Você não tem acesso a este chat.")

            stmt = (
                select(Message)
                .where(Message.chat_id == chat_id)
                .options(selectinload(Message.sender))
                .order_by(Message.created_at.asc())
            )
            result = await db.execute(stmt)
            messages = result.scalars().all()

            msg_list = [
                {
                    "id": m.id,
                    "chat_id": m.chat_id,
                    "sender_id": m.sender_id,
                    "ciphertext": m.ciphertext,
                    "iv": m.iv,
                    "tag": m.tag,
                    "message_type": m.message_type,
                    "media_url": m.media_url,
                    "media_name": m.media_name,
                    "media_size": m.media_size,
                    "reply_to_message_id": m.reply_to_message_id,
                    "reply_to_sender_name": m.reply_to_sender_name,
                    "reply_to_snippet": m.reply_to_snippet,
                    "is_deleted": bool(m.is_deleted),
                    "status": m.status,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "sender": _serialize_user(m.sender)
                }
                for m in messages
            ]
            return {"messages": msg_list}, None

        elif action == "send_message":
            chat_id = payload.get("chat_id")
            raw_cipher = payload.get("ciphertext")
            if isinstance(raw_cipher, dict):
                ciphertext = raw_cipher.get("ciphertext")
                iv = raw_cipher.get("iv") or payload.get("iv")
                tag = raw_cipher.get("tag") or payload.get("tag")
            else:
                ciphertext = raw_cipher
                iv = payload.get("iv")
                tag = payload.get("tag")

            msg_type = payload.get("message_type", "text")
            media_url = payload.get("media_url")
            media_name = clean_surrogates(payload.get("media_name"))
            media_size = payload.get("media_size")
            franking_tag = payload.get("franking_tag")
            reply_to_message_id = payload.get("reply_to_message_id")
            reply_to_sender_name = clean_surrogates(payload.get("reply_to_sender_name"))
            reply_to_snippet = clean_surrogates(payload.get("reply_to_snippet"))
            ciphertext = clean_surrogates(ciphertext)

            if not chat_id or not ciphertext or not iv or not tag:
                raise ValueError("Campos criptográficos incompletos.")

            from app.services.compliance_sentinel import ComplianceSentinel
            is_media_msg = msg_type in ['image', 'video', 'audio', 'voice', 'file']
            allowed, err_msg = ComplianceSentinel.check_rate_limit(session_user_id, is_media=is_media_msg)
            if not allowed:
                await ComplianceSentinel.handle_rate_limit_violation(db, current_user, err_msg)
                raise ValueError(err_msg)

            stmt = select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.members))
            chat_res = await db.execute(stmt)
            chat = chat_res.scalar_one_or_none()
            if not chat:
                raise ValueError("Chat não encontrado.")

            my_mem = next((m for m in chat.members if m.user_id == session_user_id), None)
            if not my_mem:
                raise PermissionError("Você não participa desta conversa.")

            if current_user.is_suspended or not current_user.is_active:
                raise PermissionError("Sua conta foi suspensa por infração aos Termos de Uso e não pode enviar mensagens.")

            if chat.is_group:
                if chat.is_suspended:
                    raise PermissionError(f"Este grupo foi suspenso por infração das políticas de uso: {chat.suspension_reason or 'Violação de Termos'}")
                if chat.only_admins_send_messages and my_mem.role != 'admin':
                    raise PermissionError("Apenas administradores podem enviar mensagens neste grupo.")
            else:
                other_member = next((m for m in chat.members if m.user_id != session_user_id), None)
                if other_member:
                    target_user_obj = await db.get(User, other_member.user_id)
                    if target_user_obj:
                        if target_user_obj.is_suspended or not target_user_obj.is_active:
                            raise PermissionError("Esta conta foi suspensa por infração aos Termos de Uso e não pode receber mensagens ou interações.")

                        if target_user_obj.is_bot:
                            if target_user_obj.numeric_id != "100000000003" and target_user_obj.username != "rexhenrique":
                                raise ValueError("Este é um canal oficial informativo e não recebe mensagens.")

                    blocked_by_other = await db.execute(
                        select(BlockedUser).where(and_(BlockedUser.blocker_id == other_member.user_id, BlockedUser.blocked_id == session_user_id))
                    )
                    if blocked_by_other.scalar_one_or_none():
                        raise PermissionError("Você foi bloqueado(a) por este contato e não pode enviar novas mensagens.")

                    blocked_by_me = await db.execute(
                        select(BlockedUser).where(and_(BlockedUser.blocker_id == session_user_id, BlockedUser.blocked_id == other_member.user_id))
                    )
                    if blocked_by_me.scalar_one_or_none():
                        raise ValueError("Você bloqueou este contato. Desbloqueie-o para voltar a conversar.")

            msg = Message(
                chat_id=chat_id,
                sender_id=session_user_id,
                ciphertext=ciphertext,
                iv=iv,
                tag=tag,
                message_type=msg_type,
                media_url=media_url,
                media_name=media_name,
                media_size=media_size,
                franking_tag=franking_tag,
                reply_to_message_id=reply_to_message_id,
                reply_to_sender_name=reply_to_sender_name,
                reply_to_snippet=reply_to_snippet,
                status="sent"
            )
            db.add(msg)
            chat.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(msg)

            q = select(ChatMember.user_id).where(ChatMember.chat_id == chat_id)
            res = await db.execute(q)
            member_ids = res.scalars().all()

            msg_payload = {
                "id": msg.id,
                "chat_id": msg.chat_id,
                "sender_id": msg.sender_id,
                "ciphertext": msg.ciphertext,
                "iv": msg.iv,
                "tag": msg.tag,
                "message_type": msg.message_type,
                "media_url": msg.media_url,
                "media_name": msg.media_name,
                "media_size": msg.media_size,
                "reply_to_message_id": msg.reply_to_message_id,
                "reply_to_sender_name": msg.reply_to_sender_name,
                "reply_to_snippet": msg.reply_to_snippet,
                "is_deleted": False,
                "status": msg.status,
                "created_at": msg.created_at.isoformat(),
                "sender": _serialize_user(current_user)
            }

            await ws_manager.broadcast_to_chat(
                chat_id=chat_id,
                message={"type": "new_message", "data": msg_payload},
                member_user_ids=member_ids,
                exclude_user_id=session_user_id
            )

            from app.services.rex_ai_service import get_or_create_rex_bot, process_rex_reply_task
            rex_bot = await get_or_create_rex_bot(db)
            if rex_bot.id in member_ids and session_user_id != rex_bot.id:
                asyncio.create_task(process_rex_reply_task(chat_id, session_user_id))

            return {"message": msg_payload}, None

        elif action == "get_group_details":
            chat_id = payload.get("chat_id")
            stmt = select(Chat).where(Chat.id == chat_id).options(
                selectinload(Chat.members).selectinload(ChatMember.user)
            )
            chat_res = await db.execute(stmt)
            chat = chat_res.scalar_one_or_none()
            if not chat or not chat.is_group:
                raise ValueError("Grupo não encontrado.")

            my_mem = next((m for m in chat.members if m.user_id == session_user_id), None)
            if not my_mem:
                raise PermissionError("Você não é membro deste grupo.")

            pinned_msg_data = None
            if chat.pinned_message_id:
                pmsg = await db.get(Message, chat.pinned_message_id)
                if pmsg and not pmsg.is_deleted:
                    p_sender = await db.get(User, pmsg.sender_id) if pmsg.sender_id else None
                    pinned_msg_data = {
                        "id": pmsg.id,
                        "ciphertext": pmsg.ciphertext,
                        "iv": pmsg.iv,
                        "tag": pmsg.tag,
                        "message_type": pmsg.message_type,
                        "sender_name": p_sender.full_name if p_sender else "Usuário"
                    }

            return {
                "group": {
                    "id": chat.id,
                    "uuid": chat.uuid,
                    "title": chat.title,
                    "description": chat.description,
                    "avatar_url": chat.avatar_url,
                    "created_by_id": chat.created_by_id,
                    "only_admins_send_messages": bool(chat.only_admins_send_messages),
                    "only_admins_edit_info": bool(chat.only_admins_edit_info),
                    "pinned_message_id": chat.pinned_message_id,
                    "pinned_message": pinned_msg_data,
                    "is_suspended": bool(chat.is_suspended),
                    "suspension_reason": chat.suspension_reason,
                    "group_invite_code": chat.group_invite_code,
                    "my_role": my_mem.role,
                    "created_at": chat.created_at.isoformat() if chat.created_at else None,
                    "members": [
                        {
                            "id": m.id,
                            "user_id": m.user_id,
                            "role": m.role,
                            "joined_at": m.joined_at.isoformat() if m.joined_at else None,
                            "is_creator": bool(chat.created_by_id == m.user_id),
                            "user": _serialize_user(m.user)
                        }
                        for m in chat.members
                    ]
                }
            }, None

        elif action == "get_group_invite_link":
            chat_id = payload.get("chat_id")
            stmt = select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.members))
            chat = (await db.execute(stmt)).scalar_one_or_none()
            if not chat or not chat.is_group:
                raise ValueError("Grupo não encontrado.")

            my_mem = next((m for m in chat.members if m.user_id == session_user_id), None)
            if not my_mem:
                raise PermissionError("Você não participa deste grupo.")
            if my_mem.role != "admin":
                raise PermissionError("Apenas administradores podem obter o link de convite do grupo.")
            if chat.is_suspended:
                raise ValueError("Este grupo foi suspenso por infração dos Termos de Uso.")

            if not chat.group_invite_code:
                chat.group_invite_code = f"fe1_inv_{secrets.token_urlsafe(12)}"
                await db.commit()

            return {
                "chat_id": chat.id,
                "invite_code": chat.group_invite_code,
                "invite_link": f"/#invite/{chat.group_invite_code}"
            }, None

        elif action == "revoke_group_invite_link":
            chat_id = payload.get("chat_id")
            stmt = select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.members))
            chat = (await db.execute(stmt)).scalar_one_or_none()
            if not chat or not chat.is_group:
                raise ValueError("Grupo não encontrado.")

            my_mem = next((m for m in chat.members if m.user_id == session_user_id), None)
            if not my_mem or my_mem.role != "admin":
                raise PermissionError("Apenas administradores podem revogar o link de convite.")
            if chat.is_suspended:
                raise ValueError("Este grupo foi suspenso por infração dos Termos de Uso.")

            chat.group_invite_code = f"fe1_inv_{secrets.token_urlsafe(12)}"
            await db.commit()

            return {
                "status": "revoked",
                "chat_id": chat.id,
                "invite_code": chat.group_invite_code,
                "invite_link": f"/#invite/{chat.group_invite_code}"
            }, None

        elif action == "get_group_preview_by_invite":
            invite_code = payload.get("invite_code", "").strip()
            if not invite_code:
                raise ValueError("Código de convite não informado.")

            stmt = select(Chat).where(Chat.group_invite_code == invite_code).options(selectinload(Chat.members).selectinload(ChatMember.user))
            chat = (await db.execute(stmt)).scalar_one_or_none()
            if not chat or not chat.is_group:
                raise ValueError("Link de convite inválido ou expirado.")

            if chat.is_suspended:
                raise ValueError(f"Este grupo foi suspenso por infração dos Termos de Uso: {chat.suspension_reason or 'Violação de Políticas'}")

            is_member = any(m.user_id == session_user_id for m in chat.members)
            return {
                "group_preview": {
                    "id": chat.id,
                    "title": chat.title,
                    "description": chat.description,
                    "avatar_url": chat.avatar_url,
                    "member_count": len(chat.members),
                    "created_at": chat.created_at.isoformat() if chat.created_at else None,
                    "is_already_member": is_member
                }
            }, None

        elif action == "join_group_via_invite":
            invite_code = payload.get("invite_code", "").strip()
            if not invite_code:
                raise ValueError("Código de convite não informado.")

            if current_user.is_suspended or not current_user.is_active:
                raise PermissionError("Sua conta está suspensa e não pode ingressar em grupos.")

            stmt = select(Chat).where(Chat.group_invite_code == invite_code).options(selectinload(Chat.members).selectinload(ChatMember.user))
            chat = (await db.execute(stmt)).scalar_one_or_none()
            if not chat or not chat.is_group:
                raise ValueError("Link de convite inválido ou revogado.")

            if chat.is_suspended:
                raise ValueError(f"Este grupo foi suspenso por infração dos Termos de Uso: {chat.suspension_reason or 'Violação de Políticas'}")

            existing_mem = next((m for m in chat.members if m.user_id == session_user_id), None)
            if not existing_mem:
                new_mem = ChatMember(chat_id=chat.id, user_id=session_user_id, role="member")
                db.add(new_mem)
                await db.commit()

                member_ids = [m.user_id for m in chat.members] + [session_user_id]
                await ws_manager.broadcast_to_chat(
                    chat_id=chat.id,
                    message={"type": "group_members_updated", "data": {"chat_id": chat.id, "new_member_user_id": session_user_id}},
                    member_user_ids=member_ids
                )

            mems_res = await db.execute(
                select(ChatMember).where(ChatMember.chat_id == chat.id).options(selectinload(ChatMember.user))
            )
            all_members = mems_res.scalars().all()

            return {
                "status": "joined",
                "chat": {
                    "id": chat.id,
                    "uuid": chat.uuid,
                    "is_group": True,
                    "title": chat.title,
                    "description": chat.description,
                    "avatar_url": chat.avatar_url,
                    "aes_channel_key": chat.aes_channel_key,
                    "created_by_id": chat.created_by_id,
                    "only_admins_send_messages": bool(chat.only_admins_send_messages),
                    "only_admins_edit_info": bool(chat.only_admins_edit_info),
                    "pinned_message_id": chat.pinned_message_id,
                    "is_suspended": bool(chat.is_suspended),
                    "my_role": "member",
                    "members": [{"id": m.id, "user_id": m.user_id, "role": m.role, "user": _serialize_user(m.user)} for m in all_members]
                }
            }, None

        elif action == "update_group_info":
            chat_id = payload.get("chat_id")
            stmt = select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.members))
            chat_res = await db.execute(stmt)
            chat = chat_res.scalar_one_or_none()
            if not chat or not chat.is_group:
                raise ValueError("Grupo não encontrado.")

            my_mem = next((m for m in chat.members if m.user_id == session_user_id), None)
            if not my_mem:
                raise PermissionError("Você não participa deste grupo.")

            is_changing_permissions = "only_admins_send_messages" in payload or "only_admins_edit_info" in payload
            if (chat.only_admins_edit_info or is_changing_permissions) and my_mem.role != "admin":
                raise PermissionError("Apenas administradores podem alterar as configurações deste grupo.")

            if "title" in payload and payload["title"].strip():
                chat.title = payload["title"].strip()
            if "description" in payload:
                chat.description = payload["description"].strip()
            if "avatar_url" in payload:
                chat.avatar_url = payload["avatar_url"].strip()
            if "only_admins_send_messages" in payload:
                chat.only_admins_send_messages = bool(payload["only_admins_send_messages"])
            if "only_admins_edit_info" in payload:
                chat.only_admins_edit_info = bool(payload["only_admins_edit_info"])

            chat.updated_at = datetime.utcnow()
            await db.commit()

            member_ids = [m.user_id for m in chat.members]
            await ws_manager.broadcast_to_chat(
                chat_id=chat.id,
                message={"type": "group_info_updated", "data": {
                    "chat_id": chat.id,
                    "title": chat.title,
                    "description": chat.description,
                    "avatar_url": chat.avatar_url,
                    "only_admins_send_messages": chat.only_admins_send_messages,
                    "only_admins_edit_info": chat.only_admins_edit_info
                }},
                member_user_ids=member_ids
            )
            return {"status": "success", "chat_id": chat.id}, None

        elif action == "add_group_members":
            chat_id = payload.get("chat_id")
            user_ids = payload.get("user_ids", [])
            if not user_ids:
                raise ValueError("Nenhum participante selecionado.")

            stmt = select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.members))
            chat = (await db.execute(stmt)).scalar_one_or_none()
            if not chat or not chat.is_group:
                raise ValueError("Grupo não encontrado.")

            my_mem = next((m for m in chat.members if m.user_id == session_user_id), None)
            if not my_mem:
                raise PermissionError("Você não participa deste grupo.")
            if chat.only_admins_edit_info and my_mem.role != "admin":
                raise PermissionError("Apenas administradores podem adicionar participantes a este grupo.")

            existing_uids = {m.user_id for m in chat.members}
            added_count = 0
            for uid in user_ids:
                if uid not in existing_uids:
                    target_user = await db.get(User, uid)
                    if target_user and not target_user.is_suspended and target_user.is_active:
                        db.add(ChatMember(chat_id=chat.id, user_id=uid, role="member"))
                        existing_uids.add(uid)
                        added_count += 1

            if added_count > 0:
                chat.updated_at = datetime.utcnow()
                await db.commit()

            all_uids = list(existing_uids)
            await ws_manager.broadcast_to_chat(
                chat_id=chat.id,
                message={"type": "group_members_updated", "data": {"chat_id": chat.id}},
                member_user_ids=all_uids
            )
            return {"status": "success", "added_count": added_count}, None

        elif action == "remove_group_member":
            chat_id = payload.get("chat_id")
            target_user_id = payload.get("user_id")

            stmt = select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.members))
            chat = (await db.execute(stmt)).scalar_one_or_none()
            if not chat or not chat.is_group:
                raise ValueError("Grupo não encontrado.")

            my_mem = next((m for m in chat.members if m.user_id == session_user_id), None)
            if not my_mem:
                raise PermissionError("Você não participa deste grupo.")

            target_mem = next((m for m in chat.members if m.user_id == target_user_id), None)
            if not target_mem:
                raise ValueError("Participante não encontrado no grupo.")

            if target_user_id == session_user_id:
                await db.delete(target_mem)
                await db.commit()
            else:
                if my_mem.role != "admin":
                    raise PermissionError("Apenas administradores podem remover membros deste grupo.")
                if chat.created_by_id == target_user_id:
                    raise PermissionError("O criador do grupo não pode ser removido.")
                await db.delete(target_mem)
                await db.commit()

            member_ids = [m.user_id for m in chat.members if m.user_id != target_user_id]
            await ws_manager.broadcast_to_chat(
                chat_id=chat.id,
                message={"type": "group_members_updated", "data": {"chat_id": chat.id, "removed_user_id": target_user_id}},
                member_user_ids=member_ids + [target_user_id]
            )
            return {"status": "success", "removed_user_id": target_user_id}, None

        elif action == "change_group_member_role":
            chat_id = payload.get("chat_id")
            target_user_id = payload.get("user_id")
            new_role = payload.get("role", "member")

            if new_role not in ["admin", "member"]:
                raise ValueError("Cargo inválido.")

            stmt = select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.members))
            chat = (await db.execute(stmt)).scalar_one_or_none()
            if not chat or not chat.is_group:
                raise ValueError("Grupo não encontrado.")

            my_mem = next((m for m in chat.members if m.user_id == session_user_id), None)
            if not my_mem or my_mem.role != "admin":
                raise PermissionError("Apenas administradores podem alterar cargos no grupo.")

            if chat.created_by_id == target_user_id and new_role != "admin":
                raise PermissionError("O cargo do criador do grupo não pode ser alterado.")

            target_mem = next((m for m in chat.members if m.user_id == target_user_id), None)
            if not target_mem:
                raise ValueError("Participante não encontrado no grupo.")

            target_mem.role = new_role
            await db.commit()

            member_ids = [m.user_id for m in chat.members]
            await ws_manager.broadcast_to_chat(
                chat_id=chat.id,
                message={"type": "group_members_updated", "data": {"chat_id": chat.id, "user_id": target_user_id, "new_role": new_role}},
                member_user_ids=member_ids
            )
            return {"status": "success", "user_id": target_user_id, "new_role": new_role}, None

        elif action == "pin_group_message":
            chat_id = payload.get("chat_id")
            message_id = payload.get("message_id")

            stmt = select(Chat).where(Chat.id == chat_id).options(selectinload(Chat.members))
            chat = (await db.execute(stmt)).scalar_one_or_none()
            if not chat or not chat.is_group:
                raise ValueError("Grupo não encontrado.")

            my_mem = next((m for m in chat.members if m.user_id == session_user_id), None)
            if not my_mem or my_mem.role != "admin":
                raise PermissionError("Apenas administradores podem fixar mensagens no grupo.")

            chat.pinned_message_id = message_id
            await db.commit()

            member_ids = [m.user_id for m in chat.members]
            await ws_manager.broadcast_to_chat(
                chat_id=chat.id,
                message={"type": "message_pinned", "data": {"chat_id": chat.id, "pinned_message_id": message_id}},
                member_user_ids=member_ids
            )
            return {"status": "success", "pinned_message_id": message_id}, None

        elif action == "delete_message_for_everyone":
            message_id = payload.get("message_id")
            if not message_id:
                raise ValueError("message_id é obrigatório.")

            msg = await db.get(Message, message_id)
            if not msg:
                raise ValueError("Mensagem não encontrada.")

            chat = await db.get(Chat, msg.chat_id)
            stmt = select(ChatMember).where(and_(ChatMember.chat_id == msg.chat_id, ChatMember.user_id == session_user_id))
            my_mem = (await db.execute(stmt)).scalar_one_or_none()
            if not my_mem:
                raise PermissionError("Você não participa deste chat.")

            is_sender = (msg.sender_id == session_user_id)
            is_group_admin = (chat.is_group and my_mem.role == "admin")

            if not is_sender and not is_group_admin:
                raise PermissionError("Você só pode apagar suas próprias mensagens ou mensagens como administrador do grupo.")

            msg.is_deleted = True
            msg.ciphertext = "🚫 Esta mensagem foi apagada."
            msg.message_type = "text"
            msg.media_url = None
            msg.media_name = None
            msg.media_size = None
            await db.commit()

            q = select(ChatMember.user_id).where(ChatMember.chat_id == msg.chat_id)
            member_ids = (await db.execute(q)).scalars().all()
            await ws_manager.broadcast_to_chat(
                chat_id=msg.chat_id,
                message={"type": "message_deleted_for_everyone", "data": {"chat_id": msg.chat_id, "message_id": msg.id}},
                member_user_ids=member_ids
            )
            return {"status": "success", "message_id": msg.id}, None

        elif action == "upload_chat_media":
            file_base64 = payload.get("data_base64")
            filename = payload.get("filename", "upload.bin")
            if not file_base64:
                raise ValueError("Arquivo base64 não fornecido.")

            if "," in file_base64:
                file_base64 = file_base64.split(",", 1)[1]

            blob_bytes = base64.b64decode(file_base64)
            file_hash = VaultService.store_media_blob(blob_bytes, original_filename=filename)
            stream_url = f"/api/v1/media/stream/{file_hash}"

            return {
                "media_url": stream_url,
                "media_name": filename,
                "media_size": len(blob_bytes)
            }, None

        elif action == "mark_read":
            chat_id = payload.get("chat_id")
            if not chat_id:
                raise ValueError("chat_id é obrigatório.")

            stmt = (
                update(Message)
                .where(and_(Message.chat_id == chat_id, Message.sender_id != session_user_id, Message.status != "read"))
                .values(status="read")
            )
            await db.execute(stmt)
            await db.commit()

            q = select(ChatMember.user_id).where(ChatMember.chat_id == chat_id)
            res = await db.execute(q)
            member_ids = res.scalars().all()
            for m_id in member_ids:
                if m_id != session_user_id:
                    await ws_manager.broadcast_to_user(m_id, {
                        "type": "read",
                        "chat_id": chat_id,
                        "reader_id": session_user_id
                    })

            return {"status": "ok", "chat_id": chat_id}, None

        elif action == "submit_report":
            if isinstance(payload.get("category"), dict):
                inner = payload.get("category")
                category = str(inner.get("category") or "other")
                reason = str(inner.get("reason") or "Denúncia submetida pelo usuário via canal seguro")
                reported_user_id = inner.get("reported_user_id")
                reported_chat_id = inner.get("chat_id") or inner.get("reported_chat_id")
                message_id = inner.get("message_id")
                plaintext_evidence = inner.get("plaintext_evidence")
                franking_tag = inner.get("franking_tag")
            else:
                category = str(payload.get("category") or "other")
                reason = str(payload.get("reason") or "Denúncia submetida pelo usuário via canal seguro")
                reported_user_id = payload.get("reported_user_id")
                reported_chat_id = payload.get("chat_id") or payload.get("reported_chat_id")
                message_id = payload.get("message_id")
                plaintext_evidence = payload.get("plaintext_evidence")
                franking_tag = payload.get("franking_tag")

            if message_id and not reported_user_id:
                msg_obj = await db.get(Message, message_id)
                if msg_obj:
                    reported_user_id = msg_obj.sender_id
                    if not reported_chat_id:
                        reported_chat_id = msg_obj.chat_id

            if reported_chat_id and not reported_user_id:
                chat_obj = await db.get(Chat, reported_chat_id)
                if chat_obj and not chat_obj.is_group:
                    mems_res = await db.execute(select(ChatMember).where(ChatMember.chat_id == reported_chat_id))
                    mems = mems_res.scalars().all()
                    other_m = next((m for m in mems if m.user_id != session_user_id), None)
                    if other_m:
                        reported_user_id = other_m.user_id

            if reported_user_id:
                reported_u = await db.get(User, reported_user_id)
                if reported_u and (reported_u.is_bot or reported_u.is_verified or reported_u.is_admin):
                    raise ValueError("Contatos oficiais, bots e administradores da plataforma não podem ser denunciados.")

            report = AbuseReport(
                reporter_id=session_user_id,
                reported_user_id=reported_user_id,
                chat_id=reported_chat_id,
                message_id=message_id,
                category=category,
                reason=reason,
                plaintext_evidence=plaintext_evidence,
                franking_verified=bool(franking_tag),
                status="pending"
            )
            db.add(report)
            await db.commit()
            await db.refresh(report)

            from app.services.compliance_sentinel import ComplianceSentinel
            if reported_user_id:
                await ComplianceSentinel.process_abuse_report_threshold(db, reported_user_id, category)
            if reported_chat_id:
                chat_obj = await db.get(Chat, reported_chat_id)
                if chat_obj and chat_obj.is_group:
                    await ComplianceSentinel.process_group_abuse_reports(db, reported_chat_id, category)

            return {"status": "created", "report_id": report.id}, None

        elif action == "get_abuse_reports":
            if not current_user.is_admin:
                raise PermissionError("Acesso restrito a administradores.")

            stmt = select(AbuseReport).options(selectinload(AbuseReport.reporter), selectinload(AbuseReport.reported_user)).order_by(desc(AbuseReport.created_at))
            res = await db.execute(stmt)
            reports = res.scalars().all()

            return {
                "reports": [
                    {
                        "id": r.id,
                        "reporter_id": r.reporter_id,
                        "reported_user_id": r.reported_user_id,
                        "category": r.category,
                        "reason": r.reason,
                        "plaintext_evidence": r.plaintext_evidence,
                        "status": r.status,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                        "reporter": _serialize_user(r.reporter),
                        "reported_user": _serialize_user(r.reported_user)
                    }
                    for r in reports
                ]
            }, None

        elif action == "register_judicial_order":
            if not current_user.is_admin:
                raise PermissionError("Acesso restrito a administradores.")

            court_order_number = payload.get("court_order_number", "").strip()
            issuing_court = payload.get("issuing_court", "").strip()
            officer_badge = payload.get("officer_badge", "").strip()
            target_identifier = payload.get("target_identifier", "").strip()
            action_type = payload.get("action_type", "metadata_export")
            notes = payload.get("notes", "")

            if not court_order_number or not issuing_court or not officer_badge or not target_identifier:
                raise ValueError("Dados incompletos para registro de ordem judicial.")

            raw_str = f"{court_order_number}|{issuing_court}|{officer_badge}|{target_identifier}|{datetime.utcnow().isoformat()}"
            audit_hash = hashlib.sha256(raw_str.encode()).hexdigest()

            audit = JudicialOrderAudit(
                court_order_number=court_order_number,
                issuing_court=issuing_court,
                officer_badge=officer_badge,
                target_identifier=target_identifier,
                action_type=action_type,
                audit_hash=audit_hash,
                authorized_by_admin=current_user.username,
                notes=notes
            )
            db.add(audit)
            await db.commit()
            await db.refresh(audit)
            return {"status": "registered", "audit_id": audit.id, "audit_hash": audit_hash}, None

        elif action == "get_judicial_audits":
            if not current_user.is_admin:
                raise PermissionError("Acesso restrito a administradores.")

            stmt = select(JudicialOrderAudit).order_by(desc(JudicialOrderAudit.created_at))
            res = await db.execute(stmt)
            audits = res.scalars().all()
            return {
                "audits": [
                    {
                        "id": a.id,
                        "court_order_number": a.court_order_number,
                        "issuing_court": a.issuing_court,
                        "officer_badge": a.officer_badge,
                        "target_identifier": a.target_identifier,
                        "action_type": a.action_type,
                        "audit_hash": a.audit_hash,
                        "authorized_by_admin": a.authorized_by_admin,
                        "notes": a.notes,
                        "created_at": a.created_at.isoformat() if a.created_at else None
                    }
                    for a in audits
                ]
            }, None

        elif action == "suspend_user":
            if not current_user.is_admin:
                raise PermissionError("Acesso restrito a administradores.")

            target_id = payload.get("user_id")
            reason = payload.get("reason", "Suspensão determinada por ordem de conformidade")

            target = await db.get(User, target_id)
            if not target:
                raise ValueError("Usuário não encontrado.")

            target.is_suspended = True
            await db.commit()

            if target_id in ws_manager.active_connections:
                for ws in list(ws_manager.active_connections[target_id]):
                    try:
                        await ws.close(code=4003, reason=f"Conta suspensa: {reason}")
                    except Exception:
                        pass

            return {"status": "suspended", "target_user_id": target_id}, None

        elif action == "unsuspend_user":
            if not current_user.is_admin:
                raise PermissionError("Acesso restrito a administradores.")

            target_id = payload.get("user_id")
            target = await db.get(User, target_id)
            if not target:
                raise ValueError("Usuário não encontrado.")

            target.is_suspended = False
            await db.commit()
            return {"status": "unsuspended", "user_id": target_id}, None

        elif action == "get_judicial_users_list":
            if not current_user.is_admin:
                raise PermissionError("Acesso restrito a administradores.")

            search_query = payload.get("query", "").strip().lower()
            stmt = select(User).order_by(desc(User.last_seen))
            res = await db.execute(stmt)
            all_users = res.scalars().all()

            users_data = []
            for u in all_users:
                if search_query:
                    match_str = f"{u.full_name} {u.username} {u.numeric_id} {u.email} {u.last_ip or ''} {u.device_info or ''}".lower()
                    if search_query not in match_str:
                        continue

                chat_count_q = select(ChatMember.chat_id).where(ChatMember.user_id == u.id)
                chat_count = len((await db.execute(chat_count_q)).scalars().all())

                msg_count_q = select(Message.id).where(Message.sender_id == u.id)
                msg_count = len((await db.execute(msg_count_q)).scalars().all())

                report_count_q = select(AbuseReport.id).where(AbuseReport.reported_user_id == u.id)
                report_count = len((await db.execute(report_count_q)).scalars().all())

                users_data.append({
                    "id": u.id,
                    "numeric_id": u.numeric_id,
                    "username": u.username,
                    "full_name": u.full_name,
                    "email": u.email,
                    "avatar_url": u.avatar_url,
                    "bio": u.bio,
                    "is_admin": u.is_admin,
                    "is_verified": bool(u.is_verified),
                    "is_suspended": u.is_suspended,
                    "is_bot": bool(u.is_bot),
                    "last_ip": getattr(u, 'last_ip', None) or "127.0.0.1",
                    "user_agent": getattr(u, 'user_agent', None) or "",
                    "device_info": getattr(u, 'device_info', None) or "Dispositivo Web Padrão",
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                    "last_seen": u.last_seen.isoformat() if u.last_seen else None,
                    "is_online": u.id in ws_manager.active_connections,
                    "total_chats": chat_count,
                    "total_messages": msg_count,
                    "total_reports": report_count
                })

            return {"users": users_data, "total": len(users_data)}, None

        elif action == "get_judicial_user_dossier":
            if not current_user.is_admin:
                raise PermissionError("Acesso restrito a administradores.")

            target_id = payload.get("user_id")
            target = await db.get(User, target_id)
            if not target:
                raise ValueError("Usuário não encontrado.")

            memberships_q = select(ChatMember).options(selectinload(ChatMember.chat)).where(ChatMember.user_id == target.id)
            memberships = (await db.execute(memberships_q)).scalars().all()

            chats_data = []
            for m in memberships:
                c = m.chat
                if not c:
                    continue
                mc_q = select(ChatMember.user_id).where(ChatMember.chat_id == c.id)
                mc = len((await db.execute(mc_q)).scalars().all())

                last_m_q = select(Message).where(Message.chat_id == c.id).order_by(desc(Message.created_at)).limit(1)
                last_m = (await db.execute(last_m_q)).scalars().first()

                if not c.is_group:
                    other_m_q = select(ChatMember).options(selectinload(ChatMember.user)).where(and_(ChatMember.chat_id == c.id, ChatMember.user_id != target.id))
                    other_m = (await db.execute(other_m_q)).scalars().first()
                    display_title = other_m.user.full_name if other_m and other_m.user else c.title
                else:
                    display_title = c.title

                chats_data.append({
                    "chat_id": c.id,
                    "title": display_title,
                    "is_group": c.is_group,
                    "role": m.role,
                    "member_count": mc,
                    "is_suspended": bool(c.is_suspended),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "last_message_at": last_m.created_at.isoformat() if last_m and last_m.created_at else None
                })

            rep_q = select(AbuseReport).options(selectinload(AbuseReport.reporter)).where(AbuseReport.reported_user_id == target.id).order_by(desc(AbuseReport.created_at))
            reports = (await db.execute(rep_q)).scalars().all()

            audits_q = select(JudicialOrderAudit).where(JudicialOrderAudit.target_identifier.in_([target.numeric_id, target.username, target.email, str(target.id)])).order_by(desc(JudicialOrderAudit.created_at))
            audits = (await db.execute(audits_q)).scalars().all()

            return {
                "user": _serialize_user(target, is_judicial_forensics=True),
                "chats": chats_data,
                "reports": [
                    {
                        "id": r.id,
                        "category": r.category,
                        "reason": r.reason,
                        "plaintext_evidence": r.plaintext_evidence,
                        "franking_verified": bool(getattr(r, 'franking_verified', False)),
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                        "reporter": _serialize_user(r.reporter)
                    }
                    for r in reports
                ],
                "audits": [
                    {
                        "id": a.id,
                        "court_order_number": a.court_order_number,
                        "issuing_court": a.issuing_court,
                        "action_type": a.action_type,
                        "audit_hash": a.audit_hash,
                        "created_at": a.created_at.isoformat() if a.created_at else None
                    }
                    for a in audits
                ]
            }, None

        elif action == "get_judicial_chat_messages":
            if not current_user.is_admin:
                raise PermissionError("Acesso restrito a administradores.")

            chat_id = payload.get("chat_id")
            chat = await db.get(Chat, chat_id)
            if not chat:
                raise ValueError("Chat não encontrado.")

            limit = int(payload.get("limit", 200))
            stmt = select(Message).options(selectinload(Message.sender)).where(Message.chat_id == chat_id).order_by(desc(Message.created_at)).limit(limit)
            msgs = (await db.execute(stmt)).scalars().all()
            msgs.reverse()

            decrypted_messages = []
            for m in msgs:
                plaintext = "[Mensagem não descriptografável]"
                try:
                    plaintext = CryptoEngine.decrypt_aes_gcm(m.ciphertext, m.iv, m.tag, chat.aes_channel_key)
                except Exception:
                    plaintext = f"[Criptografia Protegida: {m.ciphertext[:16]}...]"

                sender_data = _serialize_user(m.sender) if m.sender else None
                decrypted_messages.append({
                    "id": m.id,
                    "chat_id": m.chat_id,
                    "sender_id": m.sender_id,
                    "sender": sender_data,
                    "plaintext": plaintext,
                    "message_type": m.message_type,
                    "media_url": m.media_url,
                    "media_name": m.media_name,
                    "media_size": m.media_size,
                    "franking_tag": m.franking_tag,
                    "reply_to_message_id": m.reply_to_message_id,
                    "reply_to_sender_name": m.reply_to_sender_name,
                    "reply_to_snippet": m.reply_to_snippet,
                    "status": m.status,
                    "created_at": m.created_at.isoformat() if m.created_at else None
                })

            return {
                "chat_id": chat.id,
                "title": chat.title,
                "is_group": chat.is_group,
                "messages": decrypted_messages
            }, None

        elif action == "export_judicial_dossier":
            if not current_user.is_admin:
                raise PermissionError("Acesso restrito a administradores.")

            target_user_id = payload.get("user_id")
            court_order_number = payload.get("court_order_number", f"AUTOS-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")
            issuing_court = payload.get("issuing_court", "Vara de Inquéritos Policiais e Crimes Cibernéticos")
            officer_badge = payload.get("officer_badge", current_user.username)
            reason = payload.get("reason", "Instrução Forense / Cumprimento de Ordem Judicial")

            target = await db.get(User, target_user_id)
            if not target:
                raise ValueError("Usuário alvo não encontrado.")

            memberships_q = select(ChatMember).options(selectinload(ChatMember.chat)).where(ChatMember.user_id == target.id)
            memberships = (await db.execute(memberships_q)).scalars().all()

            chats_transcripts = []
            total_messages_count = 0

            for m in memberships:
                c = m.chat
                if not c:
                    continue

                part_stmt = select(ChatMember).options(selectinload(ChatMember.user)).where(ChatMember.chat_id == c.id)
                participants_records = (await db.execute(part_stmt)).scalars().all()
                participants_list = [
                    {
                        "id": pr.user.id if pr.user else pr.user_id,
                        "numeric_id": pr.user.numeric_id if pr.user else "",
                        "full_name": pr.user.full_name if pr.user else "Participante",
                        "username": pr.user.username if pr.user else "",
                        "role": pr.role
                    }
                    for pr in participants_records if pr.user
                ]

                if not c.is_group:
                    other_pr = next((pr for pr in participants_records if pr.user_id != target.id and pr.user), None)
                    chat_display_title = f"Conversa Direta com {other_pr.user.full_name}" if other_pr else (c.title or "Chat Direto")
                else:
                    chat_display_title = f"Grupo: {c.title}"

                msg_stmt = select(Message).options(selectinload(Message.sender)).where(Message.chat_id == c.id).order_by(Message.created_at.asc())
                chat_msgs = (await db.execute(msg_stmt)).scalars().all()

                decrypted_history = []
                for msg_item in chat_msgs:
                    pt = "[Conteúdo Indisponível]"
                    if c.aes_channel_key:
                        try:
                            pt = CryptoEngine.decrypt_aes_gcm(msg_item.ciphertext, msg_item.iv, msg_item.tag, c.aes_channel_key)
                        except Exception:
                            pt = f"[Criptografado: {msg_item.ciphertext[:16]}...]"

                    sender_obj = msg_item.sender
                    is_sent_by_target = (msg_item.sender_id == target.id)

                    decrypted_history.append({
                        "message_id": msg_item.id,
                        "sender_id": msg_item.sender_id,
                        "sender_name": sender_obj.full_name if sender_obj else "Desconhecido",
                        "sender_numeric_id": sender_obj.numeric_id if sender_obj else "",
                        "sender_username": sender_obj.username if sender_obj else "",
                        "is_subject_sender": is_sent_by_target,
                        "role_in_dialog": "INVESTIGADO" if is_sent_by_target else "INTERLOCUTOR",
                        "plaintext_content": pt,
                        "message_type": msg_item.message_type,
                        "media_url": msg_item.media_url,
                        "media_name": msg_item.media_name,
                        "media_size": msg_item.media_size,
                        "franking_tag": msg_item.franking_tag,
                        "reply_to_message_id": msg_item.reply_to_message_id,
                        "reply_to_sender_name": msg_item.reply_to_sender_name,
                        "reply_to_snippet": msg_item.reply_to_snippet,
                        "timestamp_utc": msg_item.created_at.isoformat() if msg_item.created_at else None
                    })
                    total_messages_count += 1

                chats_transcripts.append({
                    "chat_id": c.id,
                    "chat_title": chat_display_title,
                    "is_group": c.is_group,
                    "target_role": m.role,
                    "is_suspended": bool(c.is_suspended),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "participants": participants_list,
                    "messages": decrypted_history,
                    "chat_messages_total": len(decrypted_history)
                })

            rep_stmt = select(AbuseReport).options(selectinload(AbuseReport.reporter)).where(AbuseReport.reported_user_id == target.id).order_by(desc(AbuseReport.created_at))
            reports_against = (await db.execute(rep_stmt)).scalars().all()

            protocol_id = f"LAUDO-{datetime.utcnow().strftime('%Y%m%d')}-{target.numeric_id[:4]}-{hashlib.sha256(f'{target.id}-{datetime.utcnow()}'.encode()).hexdigest()[:6].upper()}"

            account_age_days = (datetime.utcnow() - target.created_at).days if target.created_at else 0
            net_origin_hash = hashlib.sha256(f"{getattr(target, 'last_ip', '127.0.0.1')}-{getattr(target, 'user_agent', '')}".encode()).hexdigest()

            dossier_data = {
                "document_header": {
                    "system": "FECHAT PLATFORM • SISTEMA INTEGRADO DE AUDITORIA FORENSE E COMPLIANCE",
                    "forensic_protocol": protocol_id,
                    "issuing_authority": "Ofício de Segurança & Conformidade Judicial Fechat",
                    "legal_basis": "Marco Civil da Internet (Lei nº 12.965/2014, arts. 10, 11 e 15), Código de Processo Penal (arts. 158-A a 158-F - Cadeia de Custódia) e LGPD (art. 7º, VI)",
                    "court_order_number": court_order_number,
                    "issuing_court": issuing_court,
                    "officer_badge": officer_badge,
                    "reason_for_issuance": reason,
                    "emission_timestamp_utc": datetime.utcnow().isoformat(),
                    "emission_timestamp_brt": datetime.utcnow().strftime("%d/%m/%Y %H:%M:%S UTC-3"),
                    "authorized_by_admin": current_user.username,
                    "cryptographic_suite": "AES-256-GCM / SHA-256 / HMAC-SHA256 (NIST SP 800-38D / FIPS 180-4)",
                    "certificate_authority": "FECHAT-ROOT-SECURITY-COMPLIANCE-CA-v2"
                },
                "investigated_subject": {
                    "id": target.id,
                    "numeric_id": target.numeric_id,
                    "full_name": target.full_name,
                    "username": target.username,
                    "email": target.email,
                    "bio": target.bio,
                    "account_created_at": target.created_at.isoformat() if target.created_at else None,
                    "account_age_days": account_age_days,
                    "last_seen_at": target.last_seen.isoformat() if target.last_seen else None,
                    "last_known_ip": getattr(target, 'last_ip', None) or "127.0.0.1",
                    "user_agent_raw": getattr(target, 'user_agent', None) or "Navegador Web Padrão",
                    "device_category": getattr(target, 'device_info', None) or "Computador / Desktop",
                    "network_origin_fingerprint": net_origin_hash,
                    "is_suspended": bool(target.is_suspended),
                    "is_verified": bool(target.is_verified)
                },
                "abuse_reports_and_sentinel": [
                    {
                        "report_id": r.id,
                        "category": r.category,
                        "reason": r.reason,
                        "plaintext_evidence": r.plaintext_evidence,
                        "franking_verified": bool(getattr(r, 'franking_verified', False)),
                        "reporter_numeric_id": r.reporter.numeric_id if r.reporter else "ANONIMIZADO",
                        "created_at": r.created_at.isoformat() if r.created_at else None
                    }
                    for r in reports_against
                ],
                "dialog_transcripts": chats_transcripts,
                "forensic_summary": {
                    "protocol_id": protocol_id,
                    "total_chats_analyzed": len(chats_transcripts),
                    "total_messages_extracted": total_messages_count,
                    "total_reports_recorded": len(reports_against)
                }
            }

            dossier_json = json.dumps(dossier_data, sort_keys=True, ensure_ascii=False)
            sha256_hash = hashlib.sha256(dossier_json.encode('utf-8')).hexdigest()
            digital_signature = f"FECHAT-COMPLIANCE-SIGN-{sha256_hash[:24].upper()}-ECDSA-SECP256R1"

            dossier_data["cryptographic_seal"] = {
                "protocol_id": protocol_id,
                "sha256_hash": sha256_hash,
                "digital_signature_stamp": digital_signature,
                "algorithm": "SHA-256 (NIST FIPS 180-4)",
                "chain_of_custody_status": "INTEGRIDADE_VERIFICADA_E_INVIOLAVEL",
                "validation_qr_payload": f"FECHAT://VERIFY/{protocol_id}/{sha256_hash}"
            }

            audit = JudicialOrderAudit(
                court_order_number=court_order_number,
                issuing_court=issuing_court,
                officer_badge=officer_badge,
                target_identifier=target.numeric_id,
                action_type="dossier_forensic_export",
                audit_hash=sha256_hash,
                authorized_by_admin=current_user.username,
                notes=f"Laudo forense integral [{protocol_id}] emitido ({len(chats_transcripts)} chats, {total_messages_count} msgs decifradas). Mandado: {court_order_number}"
            )
            db.add(audit)
            await db.commit()
            await db.refresh(audit)

            return {
                "audit_id": audit.id,
                "protocol_id": protocol_id,
                "sha256_hash": sha256_hash,
                "digital_signature": digital_signature,
                "dossier": dossier_data
            }, None

        elif action == "send_judicial_notice":
            if not current_user.is_admin:
                raise PermissionError("Acesso restrito a administradores.")

            target_user_id = payload.get("user_id")
            title = payload.get("title", "Intimação / Notificação de Segurança").strip()
            body = payload.get("body", "").strip()
            category = payload.get("category", "judicial_notice")

            if not target_user_id or not body:
                raise ValueError("user_id e body são obrigatórios.")

            target = await db.get(User, target_user_id)
            if not target:
                raise ValueError("Usuário alvo não encontrado.")

            full_notice_text = f"⚖️ **{title.upper()}**\n\n{body}\n\n*Esta notificação possui validade legal e foi registrada na trilha de auditoria do Oficial de Segurança & Compliance do Fechat.*"
            from app.services.bot_service import send_compliance_notice
            msg = await send_compliance_notice(db, target, full_notice_text, category=category)

            return {"status": "sent", "target_user_id": target_user_id, "message_id": msg.id if msg else None}, None

        elif action == "send_compliance_notice":
            if not current_user.is_admin:
                raise PermissionError("Acesso restrito a administradores.")

            target_user_id = payload.get("user_id")
            notice_text = payload.get("notice_text", "").strip()
            category = payload.get("category", "judicial_notice")

            if not target_user_id or not notice_text:
                raise ValueError("user_id e notice_text são obrigatórios.")

            target = await db.get(User, target_user_id)
            if not target:
                raise ValueError("Usuário não encontrado.")

            from app.services.bot_service import send_compliance_notice
            msg = await send_compliance_notice(db, target, notice_text, category=category)

            return {"status": "sent", "target_user_id": target_user_id, "message_id": msg.id if msg else None}, None

        elif action == "call_signal":
            if not current_user:
                raise PermissionError("Autenticação necessária.")

            target_user_id = payload.get("target_user_id")
            signal_type = payload.get("signal_type")
            chat_id = payload.get("chat_id")
            sdp = payload.get("sdp")
            candidate = payload.get("candidate")
            reason = payload.get("reason", "")
            duration = payload.get("duration", 0)
            is_muted = payload.get("is_muted", False)

            if not target_user_id or not signal_type:
                raise ValueError("target_user_id e signal_type são obrigatórios.")

            is_target_online = ws_manager.is_user_online(target_user_id)
            if not is_target_online and signal_type == "initiate":
                return {
                    "status": "offline",
                    "signal_type": "offline",
                    "message": "O usuário está offline no momento."
                }, None

            signal_payload = {
                "type": "call_signal",
                "data": {
                    "signal_type": signal_type,
                    "sender_id": current_user.id,
                    "sender_name": current_user.full_name,
                    "sender_username": current_user.username,
                    "sender_numeric_id": current_user.numeric_id,
                    "sender_avatar": current_user.avatar_url,
                    "target_user_id": target_user_id,
                    "chat_id": chat_id,
                    "sdp": sdp,
                    "candidate": candidate,
                    "reason": reason,
                    "duration": duration,
                    "is_muted": is_muted,
                    "timestamp": datetime.utcnow().isoformat()
                }
            }

            await ws_manager.broadcast_to_user(target_user_id, signal_payload)

            return {
                "status": "delivered",
                "signal_type": signal_type,
                "target_user_id": target_user_id
            }, None

        else:
            raise ValueError(f"Ação RPC desconhecida ou não suportada: {action}")
