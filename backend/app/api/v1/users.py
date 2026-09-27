from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserOut, UserPublic, UserUpdate
from app.services.auth_service import get_current_user, get_user_by_identifier

router = APIRouter(prefix="/users", tags=["Usuários"])

@router.get("/search", response_model=List[UserPublic])
async def search_users(
    query: str = Query(..., min_length=2, description="Buscar por ID de 12 dígitos, @username ou e-mail"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    cleaned_id = "".join(ch for ch in query if ch.isdigit())
    search_pattern = f"%{query.strip().lower()}%"

    conditions = [
        User.username.ilike(search_pattern),
        User.full_name.ilike(search_pattern),
        User.email.ilike(search_pattern)
    ]
    if len(cleaned_id) >= 4:
        conditions.append(User.numeric_id.like(f"%{cleaned_id}%"))

    stmt = select(User).where(
        or_(*conditions),
        User.id != current_user.id,
        User.is_active == True,
        User.is_suspended == False
    ).limit(20)

    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/{user_id}", response_model=UserPublic)
async def get_user_public_profile(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    stmt = select(User).where(User.id == user_id, User.is_active == True)
    res = await db.execute(stmt)
    user = res.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    return user

@router.put("/profile", response_model=UserOut)
async def update_profile(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    if update_data.full_name is not None:
        current_user.full_name = update_data.full_name.strip()
    if update_data.bio is not None:
        current_user.bio = update_data.bio.strip()
    if update_data.language is not None:
        current_user.language = update_data.language
    if update_data.theme is not None:
        current_user.theme = update_data.theme
    if update_data.avatar_url is not None:
        current_user.avatar_url = update_data.avatar_url
    if update_data.public_encryption_key is not None:
        current_user.public_encryption_key = update_data.public_encryption_key

    await db.commit()
    await db.refresh(current_user)
    return current_user

from app.models.contact import Contact, BlockedUser
from app.services.ws_manager import ws_manager
from sqlalchemy import delete, and_

@router.get("/{user_id}/block-status")
async def get_user_block_status(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    b_me_q = select(BlockedUser).where(
        BlockedUser.blocker_id == current_user.id,
        BlockedUser.blocked_id == user_id
    )
    is_blocked_by_me = (await db.execute(b_me_q)).scalars().first() is not None

    b_them_q = select(BlockedUser).where(
        BlockedUser.blocker_id == user_id,
        BlockedUser.blocked_id == current_user.id
    )
    am_i_blocked = (await db.execute(b_them_q)).scalars().first() is not None

    return {
        "is_blocked_by_me": is_blocked_by_me,
        "am_i_blocked": am_i_blocked
    }

@router.post("/{user_id}/block")
async def block_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Você não pode bloquear a si mesmo.")

    check_q = select(BlockedUser).where(
        BlockedUser.blocker_id == current_user.id,
        BlockedUser.blocked_id == user_id
    )
    if not (await db.execute(check_q)).scalars().first():
        db.add(BlockedUser(blocker_id=current_user.id, blocked_id=user_id))

    c_q = select(Contact).where(
        Contact.user_id == current_user.id,
        Contact.contact_user_id == user_id
    )
    contact = (await db.execute(c_q)).scalars().first()
    if contact:
        contact.is_blocked = True

    await db.commit()

    await ws_manager.send_personal_message({
        "type": "block_update",
        "data": { "target_user_id": user_id, "is_blocked_by_me": True }
    }, current_user.id)
    await ws_manager.send_personal_message({
        "type": "block_update",
        "data": { "blocker_user_id": current_user.id, "am_i_blocked": True }
    }, user_id)

    return {"message": "Usuário bloqueado com sucesso.", "is_blocked": True}

@router.post("/{user_id}/unblock")
async def unblock_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    del_q = delete(BlockedUser).where(
        BlockedUser.blocker_id == current_user.id,
        BlockedUser.blocked_id == user_id
    )
    await db.execute(del_q)

    c_q = select(Contact).where(
        Contact.user_id == current_user.id,
        Contact.contact_user_id == user_id
    )
    contact = (await db.execute(c_q)).scalars().first()
    if contact:
        contact.is_blocked = False

    await db.commit()

    await ws_manager.send_personal_message({
        "type": "block_update",
        "data": { "target_user_id": user_id, "is_blocked_by_me": False }
    }, current_user.id)
    await ws_manager.send_personal_message({
        "type": "block_update",
        "data": { "blocker_user_id": current_user.id, "am_i_blocked": False }
    }, user_id)

    return {"message": "Usuário desbloqueado com sucesso.", "is_blocked": False}
