from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.schemas.user import UserPublic

class MessageCreate(BaseModel):
    chat_id: int
    ciphertext: str
    iv: str
    tag: str
    message_type: str = "text"
    media_url: Optional[str] = None
    media_name: Optional[str] = None
    media_size: Optional[int] = None
    franking_tag: Optional[str] = None

class MessageOut(BaseModel):
    id: int
    chat_id: int
    sender_id: Optional[int]
    sender: Optional[UserPublic]
    ciphertext: str
    iv: str
    tag: str
    message_type: str
    media_url: Optional[str]
    media_name: Optional[str] = None
    media_size: Optional[int] = None
    status: str = "sent"
    read_at: Optional[datetime] = None
    franking_tag: Optional[str] = None
    is_deleted: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ChatMemberOut(BaseModel):
    id: int
    user_id: int
    role: str
    is_muted: bool
    is_pinned: bool
    user: UserPublic

    class Config:
        from_attributes = True

class ChatCreate(BaseModel):
    is_group: bool = False
    target_user_id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    member_ids: Optional[List[int]] = []

class ChatOut(BaseModel):
    id: int
    uuid: str
    is_group: bool
    title: Optional[str]
    description: Optional[str]
    avatar_url: Optional[str]
    group_invite_code: Optional[str]
    aes_channel_key: Optional[str]
    created_by_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    members: List[ChatMemberOut] = []
    last_message: Optional[MessageOut] = None
    unread_count: int = 0

    class Config:
        from_attributes = True
