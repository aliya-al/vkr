from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_characteristic_value import ProductCharacteristicValue
from app.services.excel_product_import import (
    ImportErrorItem,
    generate_step1_template,
    parse_step1_build_step2,
    parse_step2,
)
from app.utils.database import get_async_session
from app.utils.strings import ensure_unique_slug, slugify
from app.utils.templates import templates

router = APIRouter()


@router.get("/admin/import/products", response_class=HTMLResponse)
async def products_import_page(request: Request):
    return templates.TemplateResponse(
        "admin/imports/products.html",
        {
            "request": request,
            "errors": [],
            "success_count": None,
        },
    )


@router.get("/admin/import/products/step1-template")
async def download_step1_template(session: AsyncSession = Depends(get_async_session)):
    payload = await generate_step1_template(session)
    return StreamingResponse(
        iter([payload]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Products_Step1.xlsx"'},
    )


@router.post("/admin/import/products/step1", response_class=HTMLResponse)
async def upload_step1(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
):
    source = await file.read()
    step2_payload, errors = await parse_step1_build_step2(session, source)

    if errors:
        return templates.TemplateResponse(
            "admin/imports/products.html",
            {
                "request": request,
                "errors": errors,
                "success_count": None,
            },
            status_code=400,
        )

    assert step2_payload is not None
    return StreamingResponse(
        iter([step2_payload]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Products_Step2.xlsx"'},
    )


@router.post("/admin/import/products/step2", response_class=HTMLResponse)
async def upload_step2(
    request: Request,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
):
    source = await file.read()
    _, _, parsed_rows, parse_errors = parse_step2(source)

    if parse_errors:
        return templates.TemplateResponse(
            "admin/imports/products.html",
            {
                "request": request,
                "errors": parse_errors,
                "success_count": None,
            },
            status_code=400,
        )

    errors: list[ImportErrorItem] = []
    created_count = 0

    try:
        for parsed_row in parsed_rows:
            base = parsed_row.base_row

            duplicate_q = await session.execute(
                select(Product.id).where(
                    Product.category_id == base.category_id,
                    Product.name == base.name,
                )
            )
            if duplicate_q.scalar_one_or_none() is not None:
                errors.append(
                    ImportErrorItem(parsed_row.sheet_name, parsed_row.row_number, "Название товара", "Товар с таким названием уже есть в этой категории.")
                )
                continue

            product = Product(
                name=base.name,
                description=base.description,
                category_id=base.category_id,
                price=base.price,
                volume_m3=base.volume_m3,
                weight_kg=base.weight_kg,
                is_active=False,
                discount_percent=base.discount_percent,
            )
            product.slug = await ensure_unique_slug(session, Product, base_slug=slugify(base.name))
            session.add(product)
            await session.flush()

            for characteristic_id, (value_string, value_number) in parsed_row.characteristic_values.items():
                if value_string is None and value_number is None:
                    continue
                session.add(
                    ProductCharacteristicValue(
                        product_id=product.id,
                        characteristic_id=characteristic_id,
                        value_string=value_string,
                        value_number=value_number,
                    )
                )

            created_count += 1

        if errors:
            await session.rollback()
            return templates.TemplateResponse(
                "admin/imports/products.html",
                {
                    "request": request,
                    "errors": errors,
                    "success_count": None,
                },
                status_code=400,
            )

        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return templates.TemplateResponse(
        "admin/imports/products.html",
        {
            "request": request,
            "errors": [],
            "success_count": created_count,
        },
    )
