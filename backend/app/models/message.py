from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    ciphertext = Column(Text, nullable=False)
    iv = Column(String(32), nullable=False)
    tag = Column(String(32), nullable=False)

    message_type = Column(String(20), default="text")
    media_url = Column(String(255), nullable=True)
    media_name = Column(String(255), nullable=True)
    media_size = Column(Integer, nullable=True)

    status = Column(String(20), default="sent")
    read_at = Column(DateTime, nullable=True)

    franking_tag = Column(String(64), nullable=True)

    reply_to_message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    reply_to_sender_name = Column(String(100), nullable=True)
    reply_to_snippet = Column(Text, nullable=True)

    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    chat = relationship("Chat", back_populates="messages", foreign_keys=[chat_id])
    sender = relationship("User", back_populates="sent_messages", foreign_keys=[sender_id])
