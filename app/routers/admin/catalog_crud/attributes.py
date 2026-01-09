from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.utils.database import get_async_session
from app.utils.strings import slugify, ensure_unique_slug
from app.utils.templates import templates
from app.utils.deps import require_admin_or_404

from app.models.characteristic import GlobalCharacteristic, CharacteristicType

router = APIRouter(dependencies=[Depends(require_admin_or_404)])


@router.get("/admin/attributes", response_class=HTMLResponse)
async def attributes_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(GlobalCharacteristic).order_by(GlobalCharacteristic.name))
    attributes = result.scalars().all()
    return templates.TemplateResponse("admin/attributes/index.html", {"request": request, "attributes": attributes})


@router.get("/admin/attributes/new", response_class=HTMLResponse)
async def attribute_create_page(request: Request):
    return templates.TemplateResponse(
        "admin/attributes/create.html",
        {
            "request": request,
            "error": None,
            "name_value": "",
            "value_type_value": "string",
            "unit_value": "",
        },
    )


@router.post("/admin/attributes/new", response_class=HTMLResponse)
async def attribute_create(
    request: Request,
    name: str = Form(...),
    value_type: str = Form("string"),
    unit: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    name_clean = (name or "").strip()
    value_type_clean = (value_type or "string").strip().lower()
    unit_clean = (unit.strip() if unit and unit.strip() else None)

    if not name_clean:
        return templates.TemplateResponse(
            "admin/attributes/create.html",
            {
                "request": request,
                "error": "Название обязательно.",
                "name_value": "",
                "value_type_value": value_type_clean,
                "unit_value": unit or "",
            },
            status_code=400,
        )

    if value_type_clean not in {"string", "number"}:
        raise HTTPException(status_code=400, detail="value_type must be 'string' or 'number'")

    # 1) Предварительная проверка (чтобы не падать в 500)
    exists_stmt = select(GlobalCharacteristic.id).where(
        func.lower(GlobalCharacteristic.name) == name_clean.lower()
    )
    if (await session.execute(exists_stmt)).first():
        return templates.TemplateResponse(
            "admin/attributes/create.html",
            {
                "request": request,
                "error": "Такая характеристика уже существует.",
                "name_value": name_clean,
                "value_type_value": value_type_clean,
                "unit_value": unit or "",
            },
            status_code=400,
        )

    # 2) Уникальный slug
    base = slugify(name_clean)
    slug = await ensure_unique_slug(session, GlobalCharacteristic, base)

    attr = GlobalCharacteristic(
        name=name_clean,
        slug=slug,
        value_type=CharacteristicType(value_type_clean),
        unit=unit_clean,
    )
    session.add(attr)

    # 3) На всякий случай ловим IntegrityError (гонки/параллельные запросы)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return templates.TemplateResponse(
            "admin/attributes/create.html",
            {
                "request": request,
                "error": "Такая характеристика уже существует.",
                "name_value": name_clean,
                "value_type_value": value_type_clean,
                "unit_value": unit or "",
            },
            status_code=400,
        )

    return RedirectResponse("/admin/attributes", status_code=303)


@router.get("/admin/attributes/{attribute_id}/edit", response_class=HTMLResponse)
async def attribute_edit_page(
    attribute_id: int,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    attr = (await session.execute(select(GlobalCharacteristic).where(GlobalCharacteristic.id == attribute_id))).scalar_one_or_none()
    if not attr:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "admin/attributes/edit.html",
        {"request": request, "attribute": attr, "error": None},
    )


@router.post("/admin/attributes/{attribute_id}/edit", response_class=HTMLResponse)
async def attribute_edit(
    attribute_id: int,
    request: Request,
    name: str = Form(...),
    value_type: str = Form("string"),
    unit: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    attr = (await session.execute(select(GlobalCharacteristic).where(GlobalCharacteristic.id == attribute_id))).scalar_one_or_none()
    if not attr:
        raise HTTPException(status_code=404)

    name_clean = (name or "").strip()
    value_type_clean = (value_type or "string").strip().lower()
    unit_clean = (unit.strip() if unit and unit.strip() else None)

    if not name_clean:
        return templates.TemplateResponse(
            "admin/attributes/edit.html",
            {"request": request, "attribute": attr, "error": "Название обязательно."},
            status_code=400,
        )

    if value_type_clean not in {"string", "number"}:
        raise HTTPException(status_code=400, detail="value_type must be 'string' or 'number'")

    # Проверка дубля имени (кроме самой себя)
    exists_stmt = select(GlobalCharacteristic.id).where(
        func.lower(GlobalCharacteristic.name) == name_clean.lower(),
        GlobalCharacteristic.id != attribute_id,
    )
    if (await session.execute(exists_stmt)).first():
        # чтобы форма показала введённые значения
        attr.name = name_clean
        attr.value_type = CharacteristicType(value_type_clean)
        attr.unit = unit_clean
        return templates.TemplateResponse(
            "admin/attributes/edit.html",
            {"request": request, "attribute": attr, "error": "Такая характеристика уже существует."},
            status_code=400,
        )

    base = slugify(name_clean)
    slug = await ensure_unique_slug(session, GlobalCharacteristic, base, exclude_id=attribute_id)

    attr.name = name_clean
    attr.slug = slug
    attr.value_type = CharacteristicType(value_type_clean)
    attr.unit = unit_clean

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return templates.TemplateResponse(
            "admin/attributes/edit.html",
            {"request": request, "attribute": attr, "error": "Такая характеристика уже существует."},
            status_code=400,
        )

    return RedirectResponse("/admin/attributes", status_code=303)

@router.post("/admin/attributes/{attribute_id}/delete")
async def attribute_delete(
    attribute_id: int,
    session: AsyncSession = Depends(get_async_session),
):
    attr = (
        await session.execute(
            select(GlobalCharacteristic).where(GlobalCharacteristic.id == attribute_id)
        )
    ).scalar_one_or_none()
    if not attr:
        raise HTTPException(status_code=404)

    await session.delete(attr)
    await session.commit()
    return RedirectResponse("/admin/attributes", status_code=303)
