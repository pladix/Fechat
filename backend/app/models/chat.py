import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()))
    is_group = Column(Boolean, default=False)
    title = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    avatar_url = Column(String(255), nullable=True)
    group_invite_code = Column(String(32), unique=True, nullable=True)
    aes_channel_key = Column(String(128), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    only_admins_send_messages = Column(Boolean, default=False)
    only_admins_edit_info = Column(Boolean, default=False)
    pinned_message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    is_suspended = Column(Boolean, default=False)
    suspension_reason = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    members = relationship("ChatMember", back_populates="chat", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan", foreign_keys="[Message.chat_id]")

class ChatMember(Base):
    __tablename__ = "chat_members"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), default="member")
    is_muted = Column(Boolean, default=False)
    is_pinned = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_read_message_id = Column(Integer, default=0)

    chat = relationship("Chat", back_populates="members")
    user = relationship("User", back_populates="chat_memberships")
