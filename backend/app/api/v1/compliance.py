from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.config import settings
from app.models.user import User
from app.models.compliance import AbuseReport, JudicialOrderAudit
from app.models.message import Message
from app.schemas.compliance import (
    AbuseReportCreate, AbuseReportOut,
    JudicialOrderCreate, JudicialOrderOut
)
from app.services.auth_service import get_current_user, get_admin_user, get_user_by_identifier
from app.services.compliance_service import ComplianceService
from app.services.crypto_service import CryptoEngine

router = APIRouter(prefix="/compliance", tags=["Conformidade, Denúncias e Ordens Judiciais"])

@router.post("/report", response_model=AbuseReportOut, status_code=status.HTTP_201_CREATED)
async def submit_abuse_report(
    report_in: AbuseReportCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    reported_user_id = report_in.reported_user_id
    if not reported_user_id and report_in.reported_numeric_id:
        target = await get_user_by_identifier(db, report_in.reported_numeric_id)
        if target:
            reported_user_id = target.id

    franking_verified = False
    if report_in.franking_tag and report_in.plaintext_evidence and reported_user_id:
        franking_verified = True

    new_report = AbuseReport(
        reporter_id=current_user.id,
        reported_user_id=reported_user_id,
        chat_id=report_in.chat_id,
        message_id=report_in.message_id,
        category=report_in.category,
        reason=report_in.reason,
        plaintext_evidence=report_in.plaintext_evidence,
        franking_verified=franking_verified,
        status="pending",
        created_at=datetime.utcnow()
    )
    db.add(new_report)
    await db.commit()

    stmt = (
        select(AbuseReport)
        .where(AbuseReport.id == new_report.id)
        .options(selectinload(AbuseReport.reporter), selectinload(AbuseReport.reported_user))
    )
    res = await db.execute(stmt)
    return res.scalars().first()

@router.get("/admin/reports", response_model=List[AbuseReportOut])
async def list_abuse_reports(
    status_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):

    stmt = select(AbuseReport).options(
        selectinload(AbuseReport.reporter),
        selectinload(AbuseReport.reported_user)
    ).order_by(desc(AbuseReport.created_at))

    if status_filter:
        stmt = stmt.where(AbuseReport.status == status_filter)
    if category_filter:
        stmt = stmt.where(AbuseReport.category == category_filter)

    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("/admin/judicial-orders", response_model=JudicialOrderOut, status_code=status.HTTP_201_CREATED)
async def register_judicial_order(
    order_in: JudicialOrderCreate,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):

    audit_entry = await ComplianceService.log_judicial_action(
        db=db,
        court_order_number=order_in.court_order_number,
        issuing_court=order_in.issuing_court,
        officer_badge=order_in.officer_badge,
        target_identifier=order_in.target_identifier,
        action_type=order_in.action_type,
        authorized_by_admin=admin_user.username,
        notes=order_in.notes
    )

    if order_in.action_type == "account_suspension":
        target = await get_user_by_identifier(db, order_in.target_identifier)
        if target:
            await ComplianceService.suspend_user_account(db, target.id, reason=f"Ordem Judicial {order_in.court_order_number}")

    return audit_entry

@router.get("/admin/judicial-orders", response_model=List[JudicialOrderOut])
async def list_judicial_audit_log(
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):

    stmt = select(JudicialOrderAudit).order_by(desc(JudicialOrderAudit.created_at))
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("/admin/suspend-user/{user_id}")
async def suspend_user_action(
    user_id: int,
    reason: str,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):

    await ComplianceService.suspend_user_account(db, user_id, reason)
    return {"message": f"Usuário {user_id} suspenso com sucesso por motivo de segurança e moderação."}
