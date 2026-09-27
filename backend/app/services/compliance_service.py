import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.compliance import JudicialOrderAudit, AbuseReport
from app.models.user import User

class ComplianceService:
    @staticmethod
    def calculate_audit_hash(court_order_number: str, authority: str, target: str, action: str, timestamp_str: str) -> str:

        data_str = f"{court_order_number}|{authority}|{target}|{action}|{timestamp_str}"
        return hashlib.sha256(data_str.encode('utf-8')).hexdigest()

    @classmethod
    async def log_judicial_action(
        cls,
        db: AsyncSession,
        court_order_number: str,
        issuing_court: str,
        officer_badge: str,
        target_identifier: str,
        action_type: str,
        authorized_by_admin: str,
        notes: Optional[str] = None
    ) -> JudicialOrderAudit:
        now = datetime.utcnow()
        audit_hash = cls.calculate_audit_hash(
            court_order_number,
            issuing_court,
            target_identifier,
            action_type,
            now.isoformat()
        )

        audit_entry = JudicialOrderAudit(
            court_order_number=court_order_number,
            issuing_court=issuing_court,
            officer_badge=officer_badge,
            target_identifier=target_identifier,
            action_type=action_type,
            audit_hash=audit_hash,
            authorized_by_admin=authorized_by_admin,
            notes=notes,
            created_at=now
        )
        db.add(audit_entry)
        await db.commit()
        await db.refresh(audit_entry)
        return audit_entry

    @classmethod
    async def suspend_user_account(cls, db: AsyncSession, user_id: int, reason: str) -> bool:

        stmt = update(User).where(User.id == user_id).values(is_suspended=True, is_active=False)
        await db.execute(stmt)
        await db.commit()
        return True
