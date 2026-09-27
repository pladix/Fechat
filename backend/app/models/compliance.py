from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class AbuseReport(Base):

    __tablename__ = "abuse_reports"

    id = Column(Integer, primary_key=True, index=True)
    reporter_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reported_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="SET NULL"), nullable=True)

    category = Column(String(50), nullable=False)
    reason = Column(Text, nullable=False)

    plaintext_evidence = Column(Text, nullable=True)
    franking_verified = Column(Boolean, default=False)

    status = Column(String(30), default="pending")
    moderator_notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    reporter = relationship("User", foreign_keys=[reporter_id])
    reported_user = relationship("User", foreign_keys=[reported_user_id])

class JudicialOrderAudit(Base):

    __tablename__ = "judicial_order_audits"

    id = Column(Integer, primary_key=True, index=True)
    court_order_number = Column(String(100), nullable=False, index=True)
    issuing_court = Column(String(150), nullable=False)
    officer_badge = Column(String(100), nullable=False)
    target_identifier = Column(String(100), nullable=False)
    action_type = Column(String(50), nullable=False)

    audit_hash = Column(String(64), nullable=False)
    authorized_by_admin = Column(String(100), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
