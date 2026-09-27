import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.compliance import AbuseReport
from app.services.bot_service import send_compliance_notice
from app.services.ws_manager import ws_manager

class ComplianceSentinel:

    _message_timestamps: Dict[int, List[float]] = defaultdict(list)
    _media_timestamps: Dict[int, List[float]] = defaultdict(list)
    _throttle_until: Dict[int, float] = defaultdict(float)

    @classmethod
    def check_rate_limit(cls, user_id: int, is_media: bool = False) -> Tuple[bool, str]:

        now = time.time()

        if now < cls._throttle_until[user_id]:
            wait_sec = int(cls._throttle_until[user_id] - now) + 1
            return False, f"Uso temporariamente suspenso por atividade anômala de spam. Aguarde {wait_sec}s."

        cls._message_timestamps[user_id] = [t for t in cls._message_timestamps[user_id] if now - t < 4.0]

        recent_3s = [t for t in cls._message_timestamps[user_id] if now - t < 3.0]
        if len(recent_3s) >= 16:
            cls._throttle_until[user_id] = now + 5.0
            return False, "Comportamento de envio muito rápido detectado. O envio foi pausado por 5 segundos."

        cls._message_timestamps[user_id].append(now)

        if is_media:
            cls._media_timestamps[user_id] = [t for t in cls._media_timestamps[user_id] if now - t < 4.0]
            recent_media = [t for t in cls._media_timestamps[user_id] if now - t < 3.0]
            if len(recent_media) >= 10:
                cls._throttle_until[user_id] = now + 6.0
                return False, "Envio excessivo de arquivos/mídias em curto intervalo detectado."
            cls._media_timestamps[user_id].append(now)

        return True, ""

    @classmethod
    async def handle_rate_limit_violation(cls, db: AsyncSession, user: User, violation_reason: str):

        notice_text = (
            f"⚠️ Alerta de Segurança e Uso Indevido\n\n"
            f"Olá, {user.full_name}.\n"
            f"Nosso sistema de proteção detectou um padrão anômalo na sua conta: {violation_reason}\n\n"
            f"📌 O envio em massa ou automatizado viola nossos Termos de Segurança. A repetição contínua poderá resultar em suspensão definitiva e comunicação aos órgãos competentes."
        )
        await send_compliance_notice(db, user, notice_text, category="spam_warning")

    @classmethod
    async def _calculate_reporter_credibility(cls, db: AsyncSession, reporter_id: int) -> float:

        from app.models.message import Message
        reporter = await db.get(User, reporter_id)
        if not reporter or reporter.is_suspended:
            return 0.05
        if reporter.is_bot:
            return 0.0
        if reporter.is_admin:
            return 1.5
        if reporter.is_verified:
            return 1.2

        now = datetime.utcnow()
        age_days = (now - reporter.created_at).days if reporter.created_at else 0

        if age_days < 1:
            age_factor = 0.20
        elif age_days < 7:
            age_factor = 0.40
        elif age_days < 30:
            age_factor = 0.75
        else:
            age_factor = 1.0

        msg_count_stmt = select(func.count()).select_from(Message).where(Message.sender_id == reporter.id)
        msg_count = (await db.execute(msg_count_stmt)).scalar() or 0
        activity_factor = 1.0 if msg_count >= 5 else (0.6 if msg_count >= 1 else 0.35)

        return round(max(0.08, age_factor * activity_factor), 3)

    @classmethod
    def _calculate_evidence_score(cls, report: AbuseReport) -> float:

        base_category_weights = {
            "csam": 35.0,
            "cybercrime_threat": 30.0,
            "fraud": 22.0,
            "harassment": 16.0,
            "other": 10.0
        }
        base = base_category_weights.get(report.category, 10.0)

        multiplier = 1.0
        if report.plaintext_evidence and len(report.plaintext_evidence.strip()) >= 5:
            multiplier += 0.8
        if report.franking_verified:
            multiplier += 0.7
        if report.reason and len(report.reason.strip()) >= 15:
            multiplier += 0.4

        return base * multiplier

    @classmethod
    async def process_abuse_report_threshold(cls, db: AsyncSession, reported_user_id: int, category: str):

        user = await db.get(User, reported_user_id)
        if not user or user.is_suspended:
            return

        stmt = (
            select(AbuseReport)
            .where(AbuseReport.reported_user_id == reported_user_id)
            .order_by(AbuseReport.created_at.desc())
        )
        res = await db.execute(stmt)
        reports = res.scalars().all()

        if not reports:
            return

        reporters_seen = set()
        total_risk_score = 0.0
        new_accounts_count = 0

        for r in reports:
            if r.reporter_id in reporters_seen:
                continue
            reporters_seen.add(r.reporter_id)

            credibility = await cls._calculate_reporter_credibility(db, r.reporter_id)
            evidence_score = cls._calculate_evidence_score(r)

            if credibility < 0.5:
                new_accounts_count += 1

            total_risk_score += (credibility * evidence_score)

        if len(reporters_seen) >= 3 and (new_accounts_count / len(reporters_seen)) >= 0.7:
            total_risk_score *= 0.65

        total_risk_score = min(100.0, round(total_risk_score, 1))

        if total_risk_score >= 85.0:
            user.is_suspended = True
            await db.commit()

            notice_text = (
                f"⚖️ Notificação Judicial e Suspensão de Conta\n\n"
                f"Olá, {user.full_name}.\n"
                f"Sua conta atingiu pontuação crítica de risco de conformidade ({total_risk_score}/100) após denúncias verificadas de múltiplos usuários independentes por infração das diretrizes da plataforma.\n\n"
                f"🛡️ Todos os metadados de auditoria e conexões estão devidamente preservados."
            )
            await send_compliance_notice(db, user, notice_text, category="legal_order")

            if user.id in ws_manager.active_connections:
                for ws in list(ws_manager.active_connections[user.id]):
                    try:
                        await ws.close(code=4003, reason="Conta suspensa por violação de segurança e termos de uso.")
                    except Exception:
                        pass

        elif total_risk_score >= 50.0:
            notice_text = (
                f"⚠️ Notificação Oficial de Segurança & Diretrizes de Uso\n\n"
                f"Olá, {user.full_name}.\n"
                f"Nosso sistema de moderação registrou denúncias de usuários com índice de risco moderado ({total_risk_score}/100) associadas à sua conta.\n\n"
                f"📌 Recomendamos a leitura e cumprimento dos nossos Termos de Uso. O acúmulo contínuo de denúncias verificadas poderá resultar na suspensão definitiva do seu acesso."
            )
            await send_compliance_notice(db, user, notice_text, category="warning")

    @classmethod
    async def process_group_abuse_reports(cls, db: AsyncSession, chat_id: int, category: str):

        from app.models.chat import Chat, ChatMember
        chat = await db.get(Chat, chat_id)
        if not chat or not chat.is_group or chat.is_suspended:
            return

        mems_stmt = select(func.count()).select_from(ChatMember).where(ChatMember.chat_id == chat.id)
        member_count = (await db.execute(mems_stmt)).scalar() or 1

        stmt = (
            select(AbuseReport)
            .where(AbuseReport.chat_id == chat_id)
            .order_by(AbuseReport.created_at.desc())
        )
        res = await db.execute(stmt)
        reports = res.scalars().all()

        if not reports:
            return

        reporters_seen = set()
        total_risk_score = 0.0
        new_accounts_count = 0

        for r in reports:
            if r.reporter_id in reporters_seen:
                continue
            reporters_seen.add(r.reporter_id)

            credibility = await cls._calculate_reporter_credibility(db, r.reporter_id)
            evidence_score = cls._calculate_evidence_score(r)

            if credibility < 0.5:
                new_accounts_count += 1

            total_risk_score += (credibility * evidence_score)

        if len(reporters_seen) >= 3 and (new_accounts_count / len(reporters_seen)) >= 0.7:
            total_risk_score *= 0.60

        suspension_threshold = 85.0 if member_count <= 5 else (100.0 if member_count <= 20 else 125.0)

        total_risk_score = round(total_risk_score, 1)

        if total_risk_score >= suspension_threshold:
            chat.is_suspended = True
            chat.suspension_reason = f"Grupo suspenso por infração reiterada das diretrizes (Risk Score: {total_risk_score}/{suspension_threshold})."
            await db.commit()

            stmt_mems = select(ChatMember.user_id).where(ChatMember.chat_id == chat.id)
            mems = (await db.execute(stmt_mems)).scalars().all()
            await ws_manager.broadcast_to_chat(
                chat_id=chat.id,
                message={
                    "type": "group_suspended",
                    "data": {
                        "chat_id": chat.id,
                        "is_suspended": True,
                        "suspension_reason": chat.suspension_reason
                    }
                },
                member_user_ids=mems
            )

