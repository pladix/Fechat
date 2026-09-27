from datetime import datetime, timedelta
from typing import Optional, Union
import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.config import settings
from app.database import get_db
from app.models.user import User

import bcrypt
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

import os
import json
import base64
import time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.services.crypto_service import CryptoEngine

TOKEN_AES_KEY = CryptoEngine.derive_key(settings.SECRET_KEY, salt=b"fechat_jwe_token_salt_2026")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:

    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire.timestamp(),
        "iat": datetime.utcnow().timestamp(),
        "nonce": os.urandom(8).hex()
    })

    plaintext = json.dumps(to_encode).encode('utf-8')
    aesgcm = AESGCM(TOKEN_AES_KEY)
    iv = os.urandom(12)

    encrypted_raw = aesgcm.encrypt(iv, plaintext, None)
    tag = encrypted_raw[-16:]
    ciphertext = encrypted_raw[:-16]

    token_str = "fe1." + ".".join([
        base64.urlsafe_b64encode(iv).decode('utf-8').rstrip('='),
        base64.urlsafe_b64encode(tag).decode('utf-8').rstrip('='),
        base64.urlsafe_b64encode(ciphertext).decode('utf-8').rstrip('=')
    ])
    return token_str

def decode_access_token(token: str) -> dict:

    if not token or not token.startswith("fe1."):
        raise ValueError("Formato de token criptográfico inválido.")

    parts = token.split(".")
    if len(parts) != 4:
        raise ValueError("Token corrompido.")

    def pad_b64(s: str) -> bytes:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

    iv = pad_b64(parts[1])
    tag = pad_b64(parts[2])
    ciphertext = pad_b64(parts[3])

    aesgcm = AESGCM(TOKEN_AES_KEY)
    decrypted_bytes = aesgcm.decrypt(iv, ciphertext + tag, None)
    payload = json.loads(decrypted_bytes.decode('utf-8'))

    if payload.get("exp") and time.time() > payload["exp"]:
        raise ValueError("Token expirado.")

    return payload

async def get_user_by_identifier(db: AsyncSession, identifier: str) -> Optional[User]:

    cleaned_id = "".join(ch for ch in identifier if ch.isdigit())
    query = select(User).where(
        or_(
            User.email == identifier.strip().lower(),
            User.username == identifier.strip().lower(),
            User.numeric_id == identifier.strip(),
            User.numeric_id == cleaned_id
        )
    )
    result = await db.execute(query)
    return result.scalars().first()

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sua sessão expirou ou token criptográfico é inválido. Faça login novamente.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)
    except Exception:
        raise credentials_exception

    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    user = result.scalars().first()
    if user is None:
        raise credentials_exception
    if user.is_suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta conta foi suspensa temporariamente por violação dos termos de segurança."
        )
    return user

async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores autorizados e setor de conformidade."
        )
    return current_user
