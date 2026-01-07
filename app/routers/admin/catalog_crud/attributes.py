from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.database import get_async_session
from app.utils.strings import slugify
from app.utils.templates import templates
from app.utils.deps import require_admin_or_404

from app.models.characteristic import GlobalCharacteristic


router = APIRouter(dependencies=[Depends(require_admin_or_404)])


@router.get("/admin/attributes", response_class=HTMLResponse)
async def attributes_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(GlobalCharacteristic).order_by(GlobalCharacteristic.name))
    attributes = result.scalars().all()
    return templates.TemplateResponse(
        "admin/attributes/index.html",
        {"request": request, "attributes": attributes},
    )


@router.get("/admin/attributes/new", response_class=HTMLResponse)
async def attribute_create_page(request: Request):
    return templates.TemplateResponse(
        "admin/attributes/create.html",
        {"request": request},
    )


@router.post("/admin/attributes/new")
async def attribute_create(
    name: str = Form(...),
    value_type: str = Form("string"),
    unit: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    value_type = (value_type or "string").strip().lower()
    if value_type not in {"string", "number"}:
        raise HTTPException(status_code=400, detail="value_type must be 'string' or 'number'")

    attr = GlobalCharacteristic(
        name=name.strip(),
        slug=slugify(name),
        value_type=value_type,
        unit=(unit.strip() if unit and unit.strip() else None),
    )
    session.add(attr)
    await session.commit()
    return RedirectResponse("/admin/attributes", status_code=303)


@router.get("/admin/attributes/{attribute_id}/edit", response_class=HTMLResponse)
async def attribute_edit_page(
    attribute_id: int,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(GlobalCharacteristic).where(GlobalCharacteristic.id == attribute_id))
    attr = result.scalar_one_or_none()
    if not attr:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "admin/attributes/edit.html",
        {"request": request, "attribute": attr},
    )


@router.post("/admin/attributes/{attribute_id}/edit")
async def attribute_edit(
    attribute_id: int,
    name: str = Form(...),
    value_type: str = Form("string"),
    unit: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(select(GlobalCharacteristic).where(GlobalCharacteristic.id == attribute_id))
    attr = result.scalar_one_or_none()
    if not attr:
        raise HTTPException(status_code=404)

    value_type = (value_type or "string").strip().lower()
    if value_type not in {"string", "number"}:
        raise HTTPException(status_code=400, detail="value_type must be 'string' or 'number'")

    attr.name = name.strip()
    attr.slug = slugify(name)
    attr.value_type = value_type
    attr.unit = (unit.strip() if unit and unit.strip() else None)

    await session.commit()
    return RedirectResponse("/admin/attributes", status_code=303)


@router.post("/admin/attributes/{attribute_id}/delete")
async def attribute_delete(attribute_id: int, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(GlobalCharacteristic).where(GlobalCharacteristic.id == attribute_id))
    attr = result.scalar_one_or_none()
    if not attr:
        raise HTTPException(status_code=404)

    await session.delete(attr)
    await session.commit()
    return RedirectResponse("/admin/attributes", status_code=303)
