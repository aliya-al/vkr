                                            
import uuid
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, Body
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, text, update, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from types import SimpleNamespace

from app.models.brand import Brand
from app.models.category import Category
from app.models.category_characteristic import CategoryCharacteristic
from app.models.characteristic import GlobalCharacteristic, CharacteristicType
from app.models.product import Product
from app.models.product_characteristic_value import ProductCharacteristicValue
from app.models.product_image import ProductImage
from app.utils.database import get_async_session
from app.utils.delete_product_image import delete_product_image_if_local
from app.utils.templates import templates
from app.utils.strings import slugify, ensure_unique_slug
from app.utils.deps import require_admin_or_404
from app.utils.uploads import upload_dir, upload_web_prefix


router = APIRouter(dependencies=[Depends(require_admin_or_404)])

                                                                    
_PRODUCTS_UPLOAD_DIR = upload_dir("products")
_PRODUCTS_WEB_PREFIX = upload_web_prefix("products")

                        
_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

                                                            
_CHUNK_SIZE = 1024 * 1024       

MAX_EXTRA_IMAGES = 5

def _ext_or_empty(filename: str) -> str:
    """Достаём расширение и проверяем, что оно разрешено."""
    ext = Path(filename).suffix.lower()
    return ext if ext in _ALLOWED_EXT else ""


async def _save_product_image(file: UploadFile) -> str:
    """
    Асинхронно сохранить картинку чанками и вернуть web-path.
    не блокируем event loop и не читаем файл целиком в память.
    """
    _PRODUCTS_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    ext = _ext_or_empty(file.filename or "")
    if not ext:
        raise ValueError("Неподдерживаемый формат изображения.")

    name = f"{uuid.uuid4().hex}{ext}"
    dst = _PRODUCTS_UPLOAD_DIR / name

    try:
        async with await anyio.open_file(dst, "wb") as out:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                await out.write(chunk)
    finally:
        try:
            await file.close()
        except Exception:
            pass

    return f"{_PRODUCTS_WEB_PREFIX}/{name}"


def _only_leaf_categories(
    categories: list[Category], current_category_id: uuid.UUID | None = None
) -> list[Category]:
    leaves: list[Category] = []
    current_category: Category | None = None

    for category in categories:
        if not category.children:
            leaves.append(category)
        if current_category_id and category.id == current_category_id:
            current_category = category

    if current_category and current_category not in leaves:
        leaves.append(current_category)

    return leaves


async def _get_form_choices(session: AsyncSession, current_category_id: uuid.UUID | None = None):
    """Подгружаем категории и бренды для форм create/edit."""
    categories_result = await session.execute(
        select(Category).options(selectinload(Category.children)).order_by(Category.name)
    )
    brands_result = await session.execute(select(Brand).order_by(Brand.name))

    categories = _only_leaf_categories(categories_result.scalars().all(), current_category_id)
    brands = brands_result.scalars().all()
    return categories, brands


def _sort_images(images: list[ProductImage]) -> list[ProductImage]:
    """Сортировка для отображения/логики: сначала главное (is_main=True), затем по id."""
    return sorted(images, key=lambda x: (not bool(getattr(x, "is_main", False)), x.id))


def _pick_next_main_after_delete(remaining: list[ProductImage], deleted_main_id: int | None) -> ProductImage | None:
    """Выбор нового главного, когда главное удалили."""
    if not remaining:
        return None

    remaining_sorted = sorted(remaining, key=lambda x: x.id)

    if deleted_main_id is not None:
        for img in remaining_sorted:
            if img.id > deleted_main_id:
                return img

    return remaining_sorted[0]

async def _get_subtree_category_ids(session: AsyncSession, root_id: uuid.UUID) -> list[uuid.UUID]:
    """Вернуть id категории root + всех её потомков."""
    q = text(
        """
        WITH RECURSIVE subcats AS (
            SELECT id
            FROM categories
            WHERE id = :root_id
            UNION
            SELECT c.id
            FROM categories c
            JOIN subcats s ON c.parent_id = s.id
        )
        SELECT id FROM subcats;
        """
    )
    rows = (await session.execute(q, {"root_id": root_id})).all()
    return [r[0] for r in rows]


async def _load_category_characteristics(session: AsyncSession, category_id: uuid.UUID):
    result = await session.execute(
        select(
            GlobalCharacteristic.id,
            GlobalCharacteristic.name,
            GlobalCharacteristic.value_type,
            GlobalCharacteristic.unit,
        )
        .select_from(CategoryCharacteristic)
        .join(GlobalCharacteristic, GlobalCharacteristic.id == CategoryCharacteristic.characteristic_id)
        .where(CategoryCharacteristic.category_id == category_id)
        .order_by(GlobalCharacteristic.name)
    )
    rows = result.all()
    return [
        SimpleNamespace(id=r.id, name=r.name, value_type=r.value_type, unit=r.unit)
        for r in rows
    ]



def _parse_number(raw: str) -> float:
    """Число принимаем и с запятой (на всякий)."""
    raw = raw.strip().replace(",", ".")
    return float(raw)


def _parse_characteristics_from_form(
    form: dict,
    characteristics: list,
) -> tuple[dict[int, tuple[str | None, float | None]], str | None]:
    """
    Возвращает:
      - распарсенные значения {characteristic_id: (value_string, value_number)}
      - текст ошибки (если есть)
    """
    parsed: dict[int, tuple[str | None, float | None]] = {}

    for ch in characteristics:
        raw = form.get(f"ch_{ch.id}")
        raw_str = str(raw).strip() if raw is not None else ""

        if not raw_str:
            parsed[ch.id] = (None, None)
            continue

        if ch.value_type == CharacteristicType.number:
            try:
                num = _parse_number(raw_str)
            except Exception:
                return {}, f"Некорректное число для характеристики «{ch.name}»."
            parsed[ch.id] = (None, num)
        else:
            parsed[ch.id] = (raw_str, None)

    return parsed, None

def _format_product_characteristics(values: list[ProductCharacteristicValue]) -> str:
    """
    Для списка товаров: "Цвет: красный; Толщина: 2 мм"
    """
    items: list[str] = []

                                                                  
    def _key(v: ProductCharacteristicValue) -> str:
        ch = getattr(v, "characteristic", None)
        return (getattr(ch, "name", "") or "").lower()

    for v in sorted(values or [], key=_key):
        ch = getattr(v, "characteristic", None)
        if not ch:
            continue

        if ch.value_type == CharacteristicType.number:
            if v.value_number is None:
                continue
                               
            s = f"{v.value_number}".rstrip("0").rstrip(".")
            if ch.unit:
                s = f"{s} {ch.unit}"
            items.append(f"{ch.name}: {s}")
        else:
            if not v.value_string:
                continue
            items.append(f"{ch.name}: {v.value_string}")

    return "; ".join(items)


@router.get("/admin/products", response_class=HTMLResponse)
async def products_list(request: Request, session: AsyncSession = Depends(get_async_session)):
                                                                            
    cats_res = await session.execute(
        select(Category).where(Category.parent_id.is_(None)).order_by(Category.name)
    )
    parent_categories = cats_res.scalars().all()

                                                     
    selected_raw = request.query_params.getlist("cat")
    selected_parent_ids: list[uuid.UUID] = []
    for s in selected_raw:
        try:
            selected_parent_ids.append(uuid.UUID(str(s)))
        except Exception:
            pass

    raw_activity = (request.query_params.get("activity") or "all").lower()
    activity = raw_activity if raw_activity in {"all", "active", "inactive"} else "all"

    raw_photos = (request.query_params.get("photos") or "all").lower()
    photos = raw_photos if raw_photos in {"all", "with", "without"} else "all"

                                                                                  
                                                                                   
    filter_category_ids: set[uuid.UUID] = set()
    if selected_parent_ids:
        for pid in selected_parent_ids:
            for cid in await _get_subtree_category_ids(session, pid):
                filter_category_ids.add(cid)

    stmt = (
        select(Product)
        .options(
            selectinload(Product.category),
            selectinload(Product.brand),
            selectinload(Product.images),
            selectinload(Product.characteristics_values).selectinload(ProductCharacteristicValue.characteristic),
        )
        .order_by(Product.name)
    )

    if filter_category_ids:
        stmt = stmt.where(Product.category_id.in_(filter_category_ids))

    if activity == "active":
        stmt = stmt.where(Product.is_active.is_(True))
    elif activity == "inactive":
        stmt = stmt.where(Product.is_active.is_(False))

    has_photo = exists(
        select(ProductImage.id).where(ProductImage.product_id == Product.id)
    )
    if photos == "with":
        stmt = stmt.where(has_photo)
    elif photos == "without":
        stmt = stmt.where(~has_photo)

    result = await session.execute(stmt)
    products = result.scalars().all()

                                       
    characteristics_text: dict[uuid.UUID, str] = {}
    for p in products:
        characteristics_text[p.id] = _format_product_characteristics(list(p.characteristics_values or []))

    return templates.TemplateResponse(
        "admin/products/index.html",
        {
            "request": request,
            "products": products,
            "characteristics_text": characteristics_text,
            "parent_categories": parent_categories,
            "activity": activity,
            "photos": photos,
        },
    )
@router.post("/admin/products/{product_id}/inline", dependencies=[Depends(require_admin_or_404)])

async def product_inline_update(
    product_id: uuid.UUID,
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        is_active = bool(payload.get("is_active"))
    except Exception:
        return {"ok": False, "error": "Неверные данные."}

    await session.execute(
        update(Product)
        .where(Product.id == product_id)
        .values(is_active=is_active)
    )
    await session.commit()
    return {"ok": True, "is_active": is_active}

@router.get("/admin/products/new", response_class=HTMLResponse)
async def product_create_page(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    category_id: str | None = None,
):
    categories, brands = await _get_form_choices(session)

    selected_category: Category | None = None
    characteristics: list[GlobalCharacteristic] = []

    if category_id:
        try:
            cat_uuid = uuid.UUID(category_id)
        except Exception:
            cat_uuid = None

        if cat_uuid:
            selected_category = await session.get(Category, cat_uuid)
            if selected_category:
                characteristics = await _load_category_characteristics(session, cat_uuid)

    return templates.TemplateResponse(
        "admin/products/create.html",
        {
            "request": request,
            "categories": categories,
            "brands": brands,
            "selected_category": selected_category,
            "selected_category_id": str(selected_category.id) if selected_category else "",
            "characteristics": characteristics,
            "ch_values": {},                    
            "error": None,
            "form_data": {},
        },
    )


@router.post("/admin/products/new")
async def product_create(
    request: Request,
    name: str = Form(...),
    description: str | None = Form(None),
    category_id: str = Form(...),
    main_image: UploadFile = File(...),
    extra_images: list[UploadFile] | None = File(None),
    brand_id: str | None = Form(None),
    price: int = Form(...),
    volume_m3: float = Form(...),
    weight_kg: float = Form(...),
    is_active: bool = Form(False),
    discount_percent: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
                                                                  
    try:
        cat_uuid = uuid.UUID(category_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректная категория.")

    characteristics = await _load_category_characteristics(session, cat_uuid)
    form = await request.form()
    parsed_ch, ch_error = _parse_characteristics_from_form(form, characteristics)

    if ch_error:
        categories, brands = await _get_form_choices(session)
        selected_category = await session.get(Category, cat_uuid)

        return templates.TemplateResponse(
            "admin/products/create.html",
            {
                "request": request,
                "categories": categories,
                "brands": brands,
                "selected_category": selected_category,
                "selected_category_id": str(cat_uuid),
                "characteristics": characteristics,
                "ch_values": {cid: (vs if vs is not None else vn) for cid, (vs, vn) in parsed_ch.items()},
                "form_data": {
                    "name": name,
                    "description": description or "",
                    "brand_id": brand_id or "",
                    "price": price,
                    "volume_m3": volume_m3,
                    "weight_kg": weight_kg,
                    "discount_percent": discount_percent or "",
                    "is_active": bool(is_active),
                },
                "error": ch_error,
            },
            status_code=400,
        )

    new_files: list[str] = []
    old_files_to_delete: list[str] = []

    try:
        product = Product(
            name=name,
            description=description,
            category_id=cat_uuid,
            brand_id=uuid.UUID(brand_id) if brand_id else None,
            price=price,
            volume_m3=volume_m3,
            weight_kg=weight_kg,
            is_active=is_active,
            discount_percent=int(discount_percent) if discount_percent else None,
        )

        base = slugify(product.name)
        product.slug = await ensure_unique_slug(session, Product, base_slug=base)

        session.add(product)
        await session.flush()

                      
        if not main_image or not main_image.filename:
            raise HTTPException(status_code=400, detail="Главное фото обязательно.")
        try:
            main_path = await _save_product_image(main_image)
        except ValueError as e:
            await session.rollback()

            categories, brands = await _get_form_choices(session)
            selected_category = await session.get(Category, cat_uuid)
            characteristics = await _load_category_characteristics(session, cat_uuid)

            return templates.TemplateResponse(
                "admin/products/create.html",
                {
                    "request": request,
                    "categories": categories,
                    "brands": brands,
                    "selected_category": selected_category,
                    "selected_category_id": str(cat_uuid),
                    "characteristics": characteristics,
                    "ch_values": {cid: (vs if vs is not None else vn) for cid, (vs, vn) in parsed_ch.items()},
                    "form_data": {
                        "name": name,
                        "description": description or "",
                        "brand_id": brand_id or "",
                        "price": price,
                        "volume_m3": volume_m3,
                        "weight_kg": weight_kg,
                        "discount_percent": discount_percent or "",
                        "is_active": bool(is_active),
                    },
                    "error": str(e),
                },
                status_code=400,
            )

        new_files.append(main_path)
        session.add(ProductImage(product_id=product.id, file_path=main_path, is_main=True))

                   
        for f in (extra_images or []):
            if not f or not f.filename:
                continue
            try:
                p = await _save_product_image(f)
            except ValueError:
                continue
            new_files.append(p)
            session.add(ProductImage(product_id=product.id, file_path=p, is_main=False))

                                
        for ch in characteristics:
            v_str, v_num = parsed_ch.get(ch.id, (None, None))
            if v_str is None and v_num is None:
                continue
            session.add(
                ProductCharacteristicValue(
                    product_id=product.id,
                    characteristic_id=ch.id,
                    value_string=v_str,
                    value_number=v_num,
                )
            )

        await session.commit()

        for p in old_files_to_delete:
            delete_product_image_if_local(p)

    except HTTPException:
        await session.rollback()
        for p in new_files:
            delete_product_image_if_local(p)
        raise
    except Exception:
        await session.rollback()
        for p in new_files:
            delete_product_image_if_local(p)
        raise

    return RedirectResponse("/admin/products", status_code=303)

@router.get("/admin/products/{product_id}/view")
async def product_view_redirect(
    product_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    res = await session.execute(select(Product.slug).where(Product.id == product_id))
    slug = res.scalar_one_or_none()
    if not slug:
        raise HTTPException(status_code=404, detail="Товар не найден.")

    return RedirectResponse(f"/catalog/product/{slug}", status_code=302)

@router.get("/admin/products/{product_id}/edit", response_class=HTMLResponse)
async def product_edit_page(
    product_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    category_id: str | None = None,
    confirm_change: str | None = None,                                         
):
    result = await session.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.category),
            selectinload(Product.brand),
            selectinload(Product.images),
            selectinload(Product.characteristics_values).selectinload(ProductCharacteristicValue.characteristic),
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404)

    categories, brands = await _get_form_choices(session, product.category_id)

    pending_change = False
    pending_category: Category | None = None

    effective_category_id = product.category_id                        
    selected_category_id_str = str(product.category_id)

    if category_id:
        try:
            new_cat_uuid = uuid.UUID(category_id)
        except Exception:
            new_cat_uuid = None

        if new_cat_uuid and new_cat_uuid != product.category_id:
                                                                                      
            if confirm_change == "1":
                effective_category_id = new_cat_uuid
                selected_category_id_str = str(new_cat_uuid)
            else:
                pending_change = True
                pending_category = await session.get(Category, new_cat_uuid)
                selected_category_id_str = str(new_cat_uuid)

    characteristics = await _load_category_characteristics(session, effective_category_id)

                                                                              
    current_values_by_id: dict[int, ProductCharacteristicValue] = {
        v.characteristic_id: v for v in (product.characteristics_values or [])
    }

    ch_values: dict[int, str] = {}
    for ch in characteristics:
        v = current_values_by_id.get(ch.id)
        if not v:
            continue
        if ch.value_type == CharacteristicType.number and v.value_number is not None:
            ch_values[ch.id] = f"{v.value_number}".rstrip("0").rstrip(".")
        elif ch.value_type == CharacteristicType.string and v.value_string:
            ch_values[ch.id] = v.value_string

    return templates.TemplateResponse(
        "admin/products/edit.html",
        {
            "request": request,
            "product": product,
            "categories": categories,
            "brands": brands,
            "selected_category_id": selected_category_id_str,
            "effective_category_id": str(effective_category_id),
            "pending_change": pending_change,
            "pending_category": pending_category,
            "characteristics": characteristics,
            "ch_values": ch_values,
            "error": None,
        },
    )


@router.post("/admin/products/{product_id}/edit")
async def product_edit(
    product_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    description: str | None = Form(None),
    category_id: str = Form(...),
    brand_id: str | None = Form(None),
    price: int = Form(...),
    delete_main: str | None = Form(None),
    delete_image_ids: list[int] = Form([]),
    volume_m3: float = Form(...),
    weight_kg: float = Form(...),
    is_active: bool = Form(False),
    main_image: UploadFile | None = File(None),
    extra_images: list[UploadFile] | None = File(None),
    discount_percent: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    form = await request.form()
    set_main_id_raw = form.get("set_main_id")

                                                                        
    try:
        cat_uuid = uuid.UUID(category_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректная категория.")

    characteristics = await _load_category_characteristics(session, cat_uuid)
    parsed_ch, ch_error = _parse_characteristics_from_form(form, characteristics)

    if ch_error:
                                                               
        result = await session.execute(
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.category),
                selectinload(Product.brand),
                selectinload(Product.images),
                selectinload(Product.characteristics_values).selectinload(ProductCharacteristicValue.characteristic),
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404)

        categories, brands = await _get_form_choices(session, product.category_id)

        from types import SimpleNamespace
        form_ns = SimpleNamespace(
            name=name,
            description=description or "",
            brand_id=(brand_id or ""),
            price=price,
            volume_m3=volume_m3,
            weight_kg=weight_kg,
            discount_percent=(discount_percent or ""),
            is_active=bool(is_active),
        )

        return templates.TemplateResponse(
            "admin/products/edit.html",
            {
                "request": request,
                "product": product,
                "categories": categories,
                "brands": brands,
                "selected_category_id": str(cat_uuid),
                "effective_category_id": str(cat_uuid),
                "pending_change": False,
                "pending_category": None,
                "characteristics": characteristics,
                "ch_values": {cid: (vs if vs is not None else vn) for cid, (vs, vn) in parsed_ch.items()},
                "form_data": form_ns,
                "error": ch_error,
            },
            status_code=400,
        )

    new_files: list[str] = []
    old_files_to_delete: list[str] = []

    try:
        result = await session.execute(
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.images),
                selectinload(Product.characteristics_values),
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404)

        old_category_id = product.category_id

                               
        product.name = name

                                                          
        base = slugify(product.name)
        product.slug = await ensure_unique_slug(
            session,
            Product,
            base_slug=base,
            exclude_id=product.id,                                        
        )

        product.description = description
        product.category_id = cat_uuid
        product.brand_id = uuid.UUID(brand_id) if brand_id else None
        product.price = price
        product.volume_m3 = volume_m3
        product.weight_kg = weight_kg
        product.is_active = is_active
        product.discount_percent = int(discount_percent) if discount_percent else None

        images_sorted = _sort_images(list(product.images or []))
        deleted_main_id: int | None = None

        ids_to_delete = set(delete_image_ids or [])

        if delete_main and not (main_image and main_image.filename):
            cur_main = next((img for img in images_sorted if img.is_main), None)
            if cur_main:
                ids_to_delete.add(cur_main.id)

        if ids_to_delete:
            for img in list(images_sorted):
                if img.id not in ids_to_delete:
                    continue
                if img.is_main:
                    deleted_main_id = img.id
                old_files_to_delete.append(img.file_path)
                await session.delete(img)

            await session.flush()

                                                             
            result_imgs0 = await session.execute(
                select(Product).where(Product.id == product_id).options(selectinload(Product.images))
            )
            product0 = result_imgs0.scalar_one()
            images_sorted = _sort_images(list(product0.images or []))

        will_delete_ids: set[int] = set(delete_image_ids or [])

        for img in images_sorted:
            if form.get(f"remove_{img.id}"):
                will_delete_ids.add(img.id)

        if delete_main and not (main_image and main_image.filename):
            cur_main = next((img for img in images_sorted if img.is_main), None)
            if cur_main:
                will_delete_ids.add(cur_main.id)

        remaining_imgs = [img for img in images_sorted if img.id not in will_delete_ids]

        set_main_id: int | None = None
        if set_main_id_raw:
            try:
                set_main_id = int(str(set_main_id_raw))
            except Exception:
                set_main_id = None

        main_id_after: int | None = None
        if set_main_id is not None and any(img.id == set_main_id for img in remaining_imgs):
            main_id_after = set_main_id
        else:
            cur_main2 = next((img for img in remaining_imgs if img.is_main), None)
            if cur_main2:
                main_id_after = cur_main2.id
            elif remaining_imgs:
                main_id_after = remaining_imgs[0].id

        remaining_extras = 0
        if remaining_imgs:
            remaining_extras = len(remaining_imgs) - (1 if main_id_after is not None else 0)
            if remaining_extras < 0:
                remaining_extras = 0

        incoming_extras = sum(1 for f in (extra_images or []) if f and f.filename)

        if remaining_extras + incoming_extras > MAX_EXTRA_IMAGES:
            result = await session.execute(
                select(Product)
                .where(Product.id == product_id)
                .options(
                    selectinload(Product.category),
                    selectinload(Product.brand),
                    selectinload(Product.images),
                    selectinload(Product.characteristics_values).selectinload(ProductCharacteristicValue.characteristic),
                )
            )
            product_view = result.scalar_one_or_none()
            if not product_view:
                raise HTTPException(status_code=404)

            categories, brands = await _get_form_choices(session, product_view.category_id)

            from types import SimpleNamespace
            form_ns = SimpleNamespace(
                name=name,
                description=description,
                brand_id=(brand_id or ""),
                price=price,
                volume_m3=volume_m3,
                weight_kg=weight_kg,
                discount_percent=(discount_percent or ""),
                is_active=is_active,
            )

            msg = f"Максимум дополнительных фото: {MAX_EXTRA_IMAGES}."

            return templates.TemplateResponse(
                "admin/products/edit.html",
                {
                    "request": request,
                    "product": product_view,
                    "categories": categories,
                    "brands": brands,
                    "selected_category_id": str(cat_uuid),
                    "effective_category_id": str(cat_uuid),
                    "pending_change": False,
                    "pending_category": None,
                    "characteristics": characteristics,
                    "ch_values": {cid: (vs if vs is not None else vn) for cid, (vs, vn) in parsed_ch.items()},
                    "form_data": form_ns,
                    "error": msg,
                },
                status_code=400,
            )


                                                                                              
        if main_image and main_image.filename:
            try:
                new_main_path = await _save_product_image(main_image)
            except ValueError as e:
                await session.rollback()

                result = await session.execute(
                    select(Product)
                    .where(Product.id == product_id)
                    .options(
                        selectinload(Product.category),
                        selectinload(Product.brand),
                        selectinload(Product.images),
                        selectinload(Product.characteristics_values).selectinload(
                            ProductCharacteristicValue.characteristic),
                    )
                )
                product_view = result.scalar_one_or_none()
                if not product_view:
                    raise HTTPException(status_code=404)

                categories, brands = await _get_form_choices(session, product_view.category_id)

                from types import SimpleNamespace
                form_ns = SimpleNamespace(
                    name=name,
                    description=description,
                    brand_id=(brand_id or ""),
                    price=price,
                    volume_m3=volume_m3,
                    weight_kg=weight_kg,
                    discount_percent=(discount_percent or ""),
                    is_active=is_active,
                )

                return templates.TemplateResponse(
                    "admin/products/edit.html",
                    {
                        "request": request,
                        "product": product_view,
                        "categories": categories,
                        "brands": brands,
                        "selected_category_id": str(cat_uuid),
                        "effective_category_id": str(cat_uuid),
                        "pending_change": False,
                        "pending_category": None,
                        "characteristics": characteristics,
                        "ch_values": {cid: (vs if vs is not None else vn) for cid, (vs, vn) in parsed_ch.items()},
                        "form_data": form_ns,
                        "error": str(e),
                    },
                    status_code=400,
                )

            new_files.append(new_main_path)

                                  
            current_main = next((img for img in images_sorted if img.is_main), None)

            if current_main:
                old_files_to_delete.append(current_main.file_path)
                current_main.file_path = new_main_path
                                                       
                for img in images_sorted:
                    img.is_main = False
                current_main.is_main = True
            else:
                                                                     
                session.add(ProductImage(product_id=product.id, file_path=new_main_path, is_main=True))

        if not images_sorted:
            main_fallback = form.get("main_image_fallback")
            if main_fallback and getattr(main_fallback, "filename", ""):
                try:
                    p = await _save_product_image(main_fallback)
                except ValueError as e:
                    await session.rollback()

                    result = await session.execute(
                        select(Product)
                        .where(Product.id == product_id)
                        .options(
                            selectinload(Product.category),
                            selectinload(Product.brand),
                            selectinload(Product.images),
                            selectinload(Product.characteristics_values).selectinload(
                                ProductCharacteristicValue.characteristic),
                        )
                    )
                    product_view = result.scalar_one_or_none()
                    if not product_view:
                        raise HTTPException(status_code=404)

                    categories, brands = await _get_form_choices(session, product_view.category_id)

                    from types import SimpleNamespace
                    form_ns = SimpleNamespace(
                        name=name,
                        description=description,
                        brand_id=(brand_id or ""),
                        price=price,
                        volume_m3=volume_m3,
                        weight_kg=weight_kg,
                        discount_percent=(discount_percent or ""),
                        is_active=is_active,
                    )

                    return templates.TemplateResponse(
                        "admin/products/edit.html",
                        {
                            "request": request,
                            "product": product_view,
                            "categories": categories,
                            "brands": brands,
                            "selected_category_id": str(cat_uuid),
                            "effective_category_id": str(cat_uuid),
                            "pending_change": False,
                            "pending_category": None,
                            "characteristics": characteristics,
                            "ch_values": {cid: (vs if vs is not None else vn) for cid, (vs, vn) in parsed_ch.items()},
                            "form_data": form_ns,
                            "error": str(e),
                        },
                        status_code=400,
                    )

                new_files.append(p)
                session.add(ProductImage(product_id=product.id, file_path=p, is_main=True))
                await session.flush()

                result2 = await session.execute(
                    select(Product).where(Product.id == product_id).options(selectinload(Product.images))
                )
                product = result2.scalar_one()
                images_sorted = _sort_images(list(product.images or []))

        set_main_id: int | None = None
        if set_main_id_raw:
            try:
                set_main_id = int(str(set_main_id_raw))
            except Exception:
                set_main_id = None

        if set_main_id is not None and images_sorted:
            target = next((img for img in images_sorted if img.id == set_main_id), None)
            if not target:
                raise HTTPException(status_code=400, detail="Выбранное главное фото не найдено.")

            for img in images_sorted:
                img.is_main = False
            await session.flush()

            target.is_main = True
            await session.flush()

            images_sorted = _sort_images(list(images_sorted))

        to_delete: list[ProductImage] = []

        for img in images_sorted:
            replace_file = form.get(f"replace_{img.id}")
            remove_flag = form.get(f"remove_{img.id}")

            if replace_file and getattr(replace_file, "filename", ""):
                try:
                    new_path = await _save_product_image(replace_file)
                except ValueError:
                    continue

                new_files.append(new_path)
                old_files_to_delete.append(img.file_path)
                img.file_path = new_path

            if remove_flag:
                if getattr(img, "is_main", False):
                    deleted_main_id = img.id
                old_files_to_delete.append(img.file_path)
                to_delete.append(img)

        for img in to_delete:
            await session.delete(img)

        for f in (extra_images or []):
            if not f or not f.filename:
                continue
            try:
                p = await _save_product_image(f)
            except ValueError:
                continue
            new_files.append(p)
            session.add(ProductImage(product_id=product.id, file_path=p, is_main=False))

        await session.flush()

        result_imgs = await session.execute(
            select(Product).where(Product.id == product_id).options(selectinload(Product.images))
        )
        product_imgs = result_imgs.scalar_one()
        remaining = list(product_imgs.images or [])

        if remaining:
            current_mains = [img for img in remaining if img.is_main]
            if len(current_mains) != 1:
                for img in remaining:
                    img.is_main = False
                await session.flush()

                new_main = _pick_next_main_after_delete(remaining, deleted_main_id)
                if new_main:
                    new_main.is_main = True
                    await session.flush()

                                          
        allowed_ids = {ch.id for ch in characteristics}

        existing_values: list[ProductCharacteristicValue] = list(product.characteristics_values or [])
        existing_by_id: dict[int, ProductCharacteristicValue] = {v.characteristic_id: v for v in existing_values}

                                                                       
        for v in existing_values:
            if v.characteristic_id not in allowed_ids:
                await session.delete(v)

                                                          
        for ch in characteristics:
            v_str, v_num = parsed_ch.get(ch.id, (None, None))
            existing = existing_by_id.get(ch.id)

                                                           
            if v_str is None and v_num is None:
                if existing:
                    await session.delete(existing)
                continue

            if existing:
                existing.value_string = v_str
                existing.value_number = v_num
            else:
                session.add(
                    ProductCharacteristicValue(
                        product_id=product.id,
                        characteristic_id=ch.id,
                        value_string=v_str,
                        value_number=v_num,
                    )
                )

                                                                                          
                                              
        _ = old_category_id                                                                           


        await session.commit()

        for p in old_files_to_delete:
            delete_product_image_if_local(p)

    except HTTPException:
        await session.rollback()
        for p in new_files:
            delete_product_image_if_local(p)
        raise
    except Exception:
        await session.rollback()
        for p in new_files:
            delete_product_image_if_local(p)
        raise

    return RedirectResponse("/admin/products", status_code=303)

@router.post("/admin/products/{product_id}/delete")
async def product_delete(product_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    old_files_to_delete: list[str] = []

    try:
        async with session.begin():
            result = await session.execute(
                select(Product).where(Product.id == product_id).options(selectinload(Product.images))
            )
            product = result.scalar_one_or_none()
            if not product:
                raise HTTPException(status_code=404)

            for img in (product.images or []):
                old_files_to_delete.append(img.file_path)
            await session.delete(product)

        for p in old_files_to_delete:
            delete_product_image_if_local(p)

    except HTTPException:
        raise

    return RedirectResponse("/admin/products", status_code=303)
