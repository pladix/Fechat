from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

import re
from pydantic import validator

class UserRegister(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=70)
    username: str = Field(..., min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(..., min_length=6)
    bio: Optional[str] = Field("Olá! Estou usando o Fechat.", max_length=150)
    language: Optional[str] = "pt_BR"
    avatar_url: Optional[str] = None

    @validator("username")
    def validate_username(cls, v):
        v = v.strip().lower()
        if not re.match(r'^[a-zA-Z0-9_.]{3,30}$', v):
            raise ValueError("O nome de usuário deve conter apenas letras, números, ponto (.) ou underline (_), com 3 a 30 caracteres.")
        return v

class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=70)
    username: Optional[str] = Field(None, min_length=3, max_length=30)
    bio: Optional[str] = Field(None, max_length=150)
    avatar_url: Optional[str] = None
    language: Optional[str] = None
    theme: Optional[str] = None
    public_encryption_key: Optional[str] = None

    @validator("username")
    def validate_username(cls, v):
        if v is not None:
            v = v.strip().lower()
            if not re.match(r'^[a-zA-Z0-9_.]{3,30}$', v):
                raise ValueError("O nome de usuário deve conter apenas letras, números, ponto (.) ou underline (_), com 3 a 30 caracteres.")
        return v

class UserOut(BaseModel):
    id: int
    numeric_id: str
    username: str
    email: str
    full_name: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    language: str
    theme: str
    public_encryption_key: Optional[str] = None
    is_active: bool
    is_admin: bool
    is_suspended: bool
    is_verified: bool = False
    is_bot: bool = False
    created_at: datetime
    last_seen: Optional[datetime] = None

    class Config:
        from_attributes = True

class UserPublic(BaseModel):
    id: int
    numeric_id: str
    username: str
    full_name: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    is_verified: bool = False
    is_bot: bool = False
    public_encryption_key: Optional[str] = None
    last_seen: Optional[datetime] = None

    class Config:
        from_attributes = True
