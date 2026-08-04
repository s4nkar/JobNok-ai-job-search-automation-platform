"""Email template CRUD endpoints."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_user_id
from app.modules.templates.schemas import TemplateIn, TemplateUpdate
from app.modules.templates import service

router = APIRouter()


@router.get("")
async def list_templates(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    return await service.list_templates(db, user_id)


@router.post("", status_code=201)
async def create_template(request: Request, body: TemplateIn, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    return await service.create_template(db, user_id, body)


@router.put("/{template_id}")
async def update_template(
    request: Request, template_id: str, body: TemplateUpdate, db: AsyncSession = Depends(get_db)
):
    user_id = get_user_id(request)
    return await service.update_template(db, user_id, template_id, body)


@router.delete("/{template_id}", status_code=204)
async def delete_template(request: Request, template_id: str, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    await service.delete_template(db, user_id, template_id)
