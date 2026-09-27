from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    numeric_id = Column(String(20), unique=True, index=True, nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    avatar_url = Column(String(255), nullable=True)
    bio = Column(String(200), default="Olá! Estou usando o Fechat.")
    language = Column(String(10), default="pt_BR")
    theme = Column(String(20), default="dark")
    public_encryption_key = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    is_suspended = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)
    is_bot = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    last_username_change = Column(DateTime, nullable=True)

    last_ip = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    device_info = Column(String(100), nullable=True)

    sent_messages = relationship("Message", back_populates="sender", foreign_keys="Message.sender_id")
    chat_memberships = relationship("ChatMember", back_populates="user")
    contacts = relationship("Contact", back_populates="owner", foreign_keys="Contact.user_id")
