import os
import shutil
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.database import get_db
from app.config import settings
from app.models.user import User
from app.schemas.auth import Token, LoginRequest
from app.schemas.user import UserRegister, UserOut
from app.services.auth_service import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    get_user_by_identifier
)
from app.services.id_generator import generate_numeric_id

from app.services.crypto_service import CryptoEngine

router = APIRouter(prefix="/auth", tags=["Autenticação"])

@router.get("/shield-handshake")
async def get_shield_handshake():

    return {
        "shield_cipher": "AES-256-GCM",
        "shield_key": CryptoEngine.get_wire_key_hex(),
        "timestamp": datetime.utcnow().timestamp()
    }

@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserRegister, db: AsyncSession = Depends(get_db)):

    check_query = select(User).where(
        or_(
            User.email == user_in.email.lower(),
            User.username == user_in.username.lower()
        )
    )
    res = await db.execute(check_query)
    if res.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este nome de usuário ou e-mail já está em uso por outro membro."
        )

    numeric_id = generate_numeric_id()
    while True:
        dup_check = await db.execute(select(User).where(User.numeric_id == numeric_id))
        if not dup_check.scalars().first():
            break
        numeric_id = generate_numeric_id()

    new_user = User(
        numeric_id=numeric_id,
        username=user_in.username.lower().strip(),
        email=user_in.email.lower().strip(),
        full_name=user_in.full_name.strip(),
        password_hash=get_password_hash(user_in.password),
        bio=user_in.bio or "Olá! Estou usando o Fechat.",
        language=user_in.language or "pt_BR",
        avatar_url=user_in.avatar_url,
        is_active=True
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    from app.services.bot_service import send_bot_welcome_message
    await send_bot_welcome_message(db, new_user)
    from app.services.rex_ai_service import ensure_rex_chat_for_user
    await ensure_rex_chat_for_user(db, new_user)

    access_token = create_access_token(data={"sub": str(new_user.id)})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": new_user
    }

@router.post("/login", response_model=Token)
async def login(login_data: LoginRequest, db: AsyncSession = Depends(get_db)):

    user = await get_user_by_identifier(db, login_data.login)
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais incorretas. Verifique seu ID/e-mail/usuário e senha."
        )
    if user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta conta foi suspensa temporariamente por violação dos termos de segurança."
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@router.get("/me", response_model=UserOut)
async def get_my_profile(current_user: User = Depends(get_current_user)):

    return current_user

from app.services.vault_service import MediaVaultService

@router.post("/upload-avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de imagem inválido. Use JPG, PNG, WEBP ou GIF Animado."
        )

    file_bytes = await file.read()
    hash_id, stream_url, _, _ = await MediaVaultService.save_file_to_vault(
        file_bytes=file_bytes,
        original_filename=file.filename,
        custom_mime=file.content_type
    )

    current_user.avatar_url = stream_url
    await db.commit()
    await db.refresh(current_user)

    return {"avatar_url": stream_url, "hash_id": hash_id, "message": "Foto de perfil criptografada e salva com sucesso!"}
