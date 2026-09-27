import os
import shutil
import secrets
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.config import settings
from app.models.user import User
from app.models.chat import Chat, ChatMember
from app.models.message import Message
from app.schemas.chat import ChatCreate, ChatOut, MessageCreate, MessageOut
from app.services.auth_service import get_current_user
from app.services.crypto_service import CryptoEngine
from app.services.ws_manager import ws_manager

router = APIRouter(prefix="/chats", tags=["Conversas e Grupos"])

@router.get("", response_model=List[ChatOut])
async def list_user_chats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    subquery = select(ChatMember.chat_id).where(ChatMember.user_id == current_user.id)
    chat_ids_res = await db.execute(subquery)
    chat_ids = chat_ids_res.scalars().all()

    if not chat_ids:
        return []

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

        chat_dict = {
            "id": chat.id,
            "uuid": chat.uuid,
            "is_group": chat.is_group,
            "title": chat.title,
            "description": chat.description,
            "avatar_url": chat.avatar_url,
            "group_invite_code": chat.group_invite_code,
            "aes_channel_key": chat.aes_channel_key,
            "created_by_id": chat.created_by_id,
            "created_at": chat.created_at,
            "updated_at": chat.updated_at,
            "members": chat.members,
            "last_message": last_msg,
            "unread_count": 0
        }
        chat_list.append(chat_dict)

    return chat_list

@router.post("", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
async def create_or_get_chat(
    payload: ChatCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    if not payload.is_group:
        if not payload.target_user_id:
            raise HTTPException(status_code=400, detail="É necessário informar a pessoa destinatária.")

        target_res = await db.execute(select(User).where(User.id == payload.target_user_id))
        target_user = target_res.scalars().first()
        if not target_user:
            raise HTTPException(status_code=404, detail="Usuário de destino não encontrado.")

        user_chats_q = select(ChatMember.chat_id).where(ChatMember.user_id == current_user.id)
        user_chats = (await db.execute(user_chats_q)).scalars().all()
        if user_chats:
            target_chats_q = (
                select(ChatMember.chat_id)
                .join(Chat, Chat.id == ChatMember.chat_id)
                .where(
                    ChatMember.chat_id.in_(user_chats),
                    ChatMember.user_id == target_user.id,
                    Chat.is_group == False
                )
            )
            common_chat_id = (await db.execute(target_chats_q)).scalars().first()
            if common_chat_id:
                full_chat_stmt = (
                    select(Chat)
                    .where(Chat.id == common_chat_id)
                    .options(
                        selectinload(Chat.members).selectinload(ChatMember.user),
                        selectinload(Chat.messages).selectinload(Message.sender)
                    )
                )
                res = await db.execute(full_chat_stmt)
                existing_chat = res.scalars().first()
                if existing_chat:
                    return existing_chat

        channel_key = CryptoEngine.generate_random_key_hex()
        new_chat = Chat(
            is_group=False,
            aes_channel_key=channel_key,
            created_by_id=current_user.id
        )
        db.add(new_chat)
        await db.flush()

        member1 = ChatMember(chat_id=new_chat.id, user_id=current_user.id, role="admin")
        member2 = ChatMember(chat_id=new_chat.id, user_id=target_user.id, role="member")
        db.add_all([member1, member2])
        await db.commit()

    else:
        if not payload.title or not payload.title.strip():
            raise HTTPException(status_code=400, detail="O nome do grupo é obrigatório.")

        invite_code = secrets.token_urlsafe(8)
        channel_key = CryptoEngine.generate_random_key_hex()

        new_chat = Chat(
            is_group=True,
            title=payload.title.strip(),
            description=payload.description,
            group_invite_code=invite_code,
            aes_channel_key=channel_key,
            created_by_id=current_user.id
        )
        db.add(new_chat)
        await db.flush()

        creator_member = ChatMember(chat_id=new_chat.id, user_id=current_user.id, role="admin")
        db.add(creator_member)

        if payload.member_ids:
            for m_id in set(payload.member_ids):
                if m_id != current_user.id:
                    db.add(ChatMember(chat_id=new_chat.id, user_id=m_id, role="member"))

        await db.commit()

    stmt = (
        select(Chat)
        .where(Chat.id == new_chat.id)
        .options(
            selectinload(Chat.members).selectinload(ChatMember.user),
            selectinload(Chat.messages).selectinload(Message.sender)
        )
    )
    res = await db.execute(stmt)
    return res.scalars().first()

@router.get("/{chat_id}/messages", response_model=List[MessageOut])
async def get_chat_messages(
    chat_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    mem_check = await db.execute(
        select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == current_user.id)
    )
    if not mem_check.scalars().first():
        raise HTTPException(status_code=403, detail="Você não faz parte desta conversa.")

    stmt = (
        select(Message)
        .where(Message.chat_id == chat_id, Message.is_deleted == False)
        .options(selectinload(Message.sender))
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def send_message(
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    members_res = await db.execute(
        select(ChatMember).where(ChatMember.chat_id == payload.chat_id)
    )
    members = members_res.scalars().all()
    member_user_ids = [m.user_id for m in members]

    if current_user.id not in member_user_ids:
        raise HTTPException(status_code=403, detail="Você não tem permissão para enviar mensagens neste chat.")

    chat_obj = await db.get(Chat, payload.chat_id)
    if not chat_obj:
        raise HTTPException(status_code=404, detail="Chat não encontrado.")

    if not chat_obj.is_group:
        other_user_id = next((uid for uid in member_user_ids if uid != current_user.id), None)
        if other_user_id:
            other_user_obj = await db.get(User, other_user_id)
            if other_user_obj and (other_user_obj.is_suspended or not other_user_obj.is_active):
                raise HTTPException(
                    status_code=403,
                    detail="Esta conta foi suspensa por infração aos Termos de Uso e não pode receber mensagens ou interações."
                )

            from app.models.contact import BlockedUser
            blocked_by_them = (await db.execute(
                select(BlockedUser).where(BlockedUser.blocker_id == other_user_id, BlockedUser.blocked_id == current_user.id)
            )).scalars().first()
            if blocked_by_them:
                raise HTTPException(
                    status_code=403,
                    detail="Você foi bloqueado(a) por este contato e não pode enviar mensagens."
                )

            blocked_by_me = (await db.execute(
                select(BlockedUser).where(BlockedUser.blocker_id == current_user.id, BlockedUser.blocked_id == other_user_id)
            )).scalars().first()
            if blocked_by_me:
                raise HTTPException(
                    status_code=400,
                    detail="Você bloqueou este contato. Desbloqueie-o para voltar a conversar."
                )

    initial_status = "sent"
    for uid in member_user_ids:
        if uid != current_user.id and ws_manager.is_user_online(uid):
            initial_status = "delivered"
            break

    new_msg = Message(
        chat_id=payload.chat_id,
        sender_id=current_user.id,
        ciphertext=payload.ciphertext,
        iv=payload.iv,
        tag=payload.tag,
        message_type=payload.message_type,
        media_url=payload.media_url,
        media_name=payload.media_name,
        media_size=payload.media_size,
        status=initial_status,
        franking_tag=payload.franking_tag,
        created_at=datetime.utcnow()
    )
    db.add(new_msg)

    if chat_obj:
        chat_obj.updated_at = datetime.utcnow()

    await db.commit()

    stmt = select(Message).where(Message.id == new_msg.id).options(selectinload(Message.sender))
    msg_loaded = (await db.execute(stmt)).scalars().first()

    ws_payload = {
        "type": "new_message",
        "data": {
            "id": msg_loaded.id,
            "chat_id": msg_loaded.chat_id,
            "sender_id": msg_loaded.sender_id,
            "sender": {
                "id": current_user.id,
                "numeric_id": current_user.numeric_id,
                "username": current_user.username,
                "full_name": current_user.full_name,
                "avatar_url": current_user.avatar_url
            },
            "ciphertext": msg_loaded.ciphertext,
            "iv": msg_loaded.iv,
            "tag": msg_loaded.tag,
            "message_type": msg_loaded.message_type,
            "media_url": msg_loaded.media_url,
            "media_name": msg_loaded.media_name,
            "media_size": msg_loaded.media_size,
            "status": msg_loaded.status,
            "franking_tag": msg_loaded.franking_tag,
            "created_at": msg_loaded.created_at.isoformat()
        }
    }
    await ws_manager.broadcast_to_chat(
        chat_id=payload.chat_id,
        message=ws_payload,
        member_user_ids=member_user_ids
    )

    return msg_loaded

@router.post("/{chat_id}/mark-read")
async def mark_chat_messages_as_read(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    from sqlalchemy import update
    now = datetime.utcnow()

    stmt = (
        update(Message)
        .where(
            Message.chat_id == chat_id,
            Message.sender_id != current_user.id,
            Message.status != "read"
        )
        .values(status="read", read_at=now)
    )
    await db.execute(stmt)
    await db.commit()

    members_res = await db.execute(select(ChatMember.user_id).where(ChatMember.chat_id == chat_id))
    member_user_ids = members_res.scalars().all()

    read_event = {
        "type": "messages_read",
        "data": {
            "chat_id": chat_id,
            "reader_id": current_user.id,
            "read_at": now.isoformat()
        }
    }
    await ws_manager.broadcast_to_chat(chat_id, read_event, member_user_ids, exclude_user_id=current_user.id)
    return {"message": "Mensagens marcadas como lidas.", "status": "read"}

from app.services.vault_service import MediaVaultService

@router.post("/upload-media")
async def upload_chat_media(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):

    file_bytes = await file.read()
    hash_id, stream_url, file_size, mime_type = await MediaVaultService.save_file_to_vault(
        file_bytes=file_bytes,
        original_filename=file.filename,
        custom_mime=file.content_type
    )

    return {
        "media_url": stream_url,
        "hash_id": hash_id,
        "media_name": file.filename,
        "media_size": file_size,
        "mime_type": mime_type
    }
