from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.schemas.user import UserPublic

class ContactCreate(BaseModel):
    identifier: str
    nickname: Optional[str] = None

class ContactOut(BaseModel):
    id: int
    user_id: int
    contact_user_id: int
    nickname: Optional[str]
    is_blocked: bool
    created_at: datetime
    contact_user: UserPublic

    class Config:
        from_attributes = True

class AbuseReportCreate(BaseModel):
    reported_user_id: Optional[int] = None
    reported_numeric_id: Optional[str] = None
    chat_id: Optional[int] = None
    message_id: Optional[int] = None
    category: str
    reason: str
    plaintext_evidence: Optional[str] = None
    franking_tag: Optional[str] = None

class AbuseReportOut(BaseModel):
    id: int
    reporter_id: Optional[int]
    reported_user_id: Optional[int]
    message_id: Optional[int]
    chat_id: Optional[int]
    category: str
    reason: str
    plaintext_evidence: Optional[str]
    franking_verified: bool
    status: str
    moderator_notes: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]
    reporter: Optional[UserPublic]
    reported_user: Optional[UserPublic]

    class Config:
        from_attributes = True

class JudicialOrderCreate(BaseModel):
    court_order_number: str
    issuing_court: str
    officer_badge: str
    target_identifier: str
    action_type: str
    authorized_by_admin: str
    notes: Optional[str] = None

class JudicialOrderOut(BaseModel):
    id: int
    court_order_number: str
    issuing_court: str
    officer_badge: str
    target_identifier: str
    action_type: str
    audit_hash: str
    authorized_by_admin: str
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
