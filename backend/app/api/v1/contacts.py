from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.contact import Contact
from app.schemas.compliance import ContactCreate, ContactOut
from app.services.auth_service import get_current_user, get_user_by_identifier

router = APIRouter(prefix="/contacts", tags=["Contatos"])

@router.get("", response_model=List[ContactOut])
async def list_contacts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    stmt = (
        select(Contact)
        .where(Contact.user_id == current_user.id)
        .options(selectinload(Contact.contact_user))
        .order_by(Contact.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
async def add_contact(
    payload: ContactCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    target_user = await get_user_by_identifier(db, payload.identifier)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhuma pessoa foi encontrada com este ID, usuário ou e-mail."
        )

    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode adicionar seu próprio perfil aos contatos."
        )

    check_stmt = select(Contact).where(
        Contact.user_id == current_user.id,
        Contact.contact_user_id == target_user.id
    )
    existing = (await db.execute(check_stmt)).scalars().first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta pessoa já está na sua lista de contatos."
        )

    new_contact = Contact(
        user_id=current_user.id,
        contact_user_id=target_user.id,
        nickname=payload.nickname
    )
    db.add(new_contact)
    await db.commit()

    stmt = select(Contact).where(Contact.id == new_contact.id).options(selectinload(Contact.contact_user))
    res = await db.execute(stmt)
    return res.scalars().first()

@router.put("/{contact_id}/toggle-block")
async def toggle_block_contact(
    contact_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    stmt = select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    contact = (await db.execute(stmt)).scalars().first()
    if not contact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contato não encontrado.")

    contact.is_blocked = not contact.is_blocked
    await db.commit()
    return {
        "message": "Status de bloqueio atualizado.",
        "is_blocked": contact.is_blocked
    }

@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):

    stmt = delete(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    await db.execute(stmt)
    await db.commit()
    return None
