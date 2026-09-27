from typing import Optional
from pydantic import BaseModel, EmailStr

class Token(BaseModel):
    access_token: str
    token_type: str
    user: "UserOut"

class LoginRequest(BaseModel):
    login: str
    password: str

from app.schemas.user import UserOut
Token.model_rebuild()
