import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, exists, select, text, update
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.category_characteristic import CategoryCharacteristic
from app.models.characteristic import GlobalCharacteristic
from app.models.product import Product
from app.models.product_image import ProductImage
from app.utils.database import get_async_session
from app.utils.delete_product_image import delete_product_image_if_local
from app.utils.strings import ensure_unique_slug, slugify
from app.utils.templates import templates
from app.utils.category_image import find_category_image_url, save_category_image, delete_category_image
from app.utils.deps import require_admin_or_404

router = APIRouter(dependencies=[Depends(require_admin_or_404)])

CAT_NAME_MAX = 30

def _truthy(v: str | None) -> bool:
    if not v:
        return False
    return v.strip().lower() in {"1", "true", "on", "yes", "ok"}


def _clean_int_list(values: list[int] | None) -> list[int]:
    clean: list[int] = []
    for x in values or []:
        try:
            clean.append(int(x))
        except Exception:
            continue
    return clean


async def _has_children(session: AsyncSession, category_id: uuid.UUID) -> bool:
    q = select(exists().where(Category.parent_id == category_id))
    return bool(await session.scalar(q))


async def _has_products(session: AsyncSession, category_id: uuid.UUID) -> bool:
    q = select(exists().where(Product.category_id == category_id))
    return bool(await session.scalar(q))


async def _move_decision_for_parent(
    session: AsyncSession,
    parent_id: uuid.UUID,
) -> tuple[bool, str | None]:
    """
    Перенос нужен, если у parent_id пока НЕТ детей и ЕСТЬ товары.
    Возвращаем: (move_needed, parent_name)
    """
    had_children_before = await _has_children(session, parent_id)
    has_products = await _has_products(session, parent_id)

    move_needed = (not had_children_before) and has_products
    if not move_needed:
        return False, None

    parent = await session.get(Category, parent_id)
    return True, (parent.name if parent else None)


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


async def _ensure_no_cycle(session: AsyncSession, category_id: uuid.UUID, new_parent_id: uuid.UUID | None) -> None:
    """Защита от циклов в дереве категорий."""
    if not new_parent_id:
        return
    if new_parent_id == category_id:
        raise HTTPException(status_code=400, detail="Нельзя выбрать категорию саму себе родителем.")

    descendants = await _get_subtree_category_ids(session, category_id)
    if new_parent_id in descendants:
        raise HTTPException(status_code=400, detail="Нельзя выбрать потомка в качестве родителя (получится цикл).")


async def _get_category_options(
    session: AsyncSession,
    exclude_ids: list[uuid.UUID] | None = None,
) -> list[dict]:
    stmt = select(Category.id, Category.name).order_by(Category.name)
    if exclude_ids:
        stmt = stmt.where(~Category.id.in_(exclude_ids))
    rows = (await session.execute(stmt)).all()
    return [{"id": r.id, "name": r.name} for r in rows]


async def _get_all_characteristics(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            select(
                GlobalCharacteristic.id,
                GlobalCharacteristic.name,
                GlobalCharacteristic.value_type,
                GlobalCharacteristic.unit,
            ).order_by(GlobalCharacteristic.name)
        )
    ).all()

    return [
        {
            "id": r.id,
            "name": r.name,
            "value_type": getattr(r.value_type, "value", str(r.value_type)),
            "unit": r.unit,
        }
        for r in rows
    ]


async def _get_selected_characteristic_ids(session: AsyncSession, category_id: uuid.UUID) -> set[int]:
    rows = (
        await session.execute(
            select(CategoryCharacteristic.characteristic_id).where(CategoryCharacteristic.category_id == category_id)
        )
    ).all()
    return {int(r[0]) for r in rows}


async def _replace_category_characteristics(
    session: AsyncSession,
    category_id: uuid.UUID,
    selected_ids: list[int],
) -> None:
    """Полностью заменяет набор характеристик категории. Вызывать внутри транзакции."""
    await session.execute(delete(CategoryCharacteristic).where(CategoryCharacteristic.category_id == category_id))

    clean_ids = _clean_int_list(selected_ids)
    if not clean_ids:
        return

    session.add_all(
        [CategoryCharacteristic(category_id=category_id, characteristic_id=cid) for cid in clean_ids]
    )


async def _get_categories_for_index(session: AsyncSession) -> list[dict]:
    Parent = aliased(Category)
    Child = aliased(Category)

    has_children_expr = exists(select(1).select_from(Child).where(Child.parent_id == Category.id))
    has_products_expr = exists(select(1).select_from(Product).where(Product.category_id == Category.id))

    stmt = (
        select(
            Category.id.label("id"),
            Category.name.label("name"),
            Category.slug.label("slug"),
            Category.parent_id.label("parent_id"),
            Category.image_path.label("image_path"),
            Parent.name.label("parent_name"),
            has_children_expr.label("has_children"),
            has_products_expr.label("has_products"),
        )
        .outerjoin(Parent, Parent.id == Category.parent_id)
        .order_by(Category.name)
    )

    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]


async def _parse_moved_message(request: Request, session: AsyncSession) -> tuple[int, str | None]:
    qp = request.query_params
    moved_raw = qp.get("moved")
    to_raw = qp.get("to")
    if not moved_raw or not to_raw:
        return 0, None

    try:
        moved_count = int(moved_raw)
        to_id = uuid.UUID(to_raw)
    except Exception:
        return 0, None

    to_obj = await session.get(Category, to_id)
    return moved_count, (to_obj.name if to_obj else None)


@router.get("/admin/categories", response_class=HTMLResponse)
async def categories_list(request: Request, session: AsyncSession = Depends(get_async_session)):
    categories = await _get_categories_for_index(session)
    moved_count, moved_to_name = await _parse_moved_message(request, session)

    by_id: dict = {}
    for c in categories:
        c["children"] = []
        img_path = c.get("image_path")
        img_path = c.get("image_path")

        if img_path:
            c["image_url"] = img_path
        else:
            c["image_url"] = find_category_image_url(c["id"])

        by_id[c["id"]] = c

    roots: list[dict] = []
    for c in by_id.values():
        pid = c.get("parent_id")
        if pid and pid in by_id:
            by_id[pid]["children"].append(c)
        else:
            roots.append(c)

    def sort_branch(nodes: list[dict]) -> None:
        nodes.sort(key=lambda x: (x.get("name") or "").lower())
        for n in nodes:
            sort_branch(n["children"])

    sort_branch(roots)

    return templates.TemplateResponse(
        "admin/categories/index.html",
        {
            "request": request,
            "roots": roots,
            "cat_name_max": CAT_NAME_MAX,
            "moved_count": moved_count,
            "moved_to_name": moved_to_name,
        },
    )


@router.get("/admin/categories/new", response_class=HTMLResponse)
async def category_create_page(request: Request, session: AsyncSession = Depends(get_async_session)):
    categories = await _get_category_options(session)
    characteristics = await _get_all_characteristics(session)

    selected_parent_id = request.query_params.get("parent_id", "")
    selected_ids: set[int] = set()
    if selected_parent_id:
        try:
            selected_ids = await _get_selected_characteristic_ids(session, uuid.UUID(selected_parent_id))
        except Exception:
            selected_parent_id = ""
            selected_ids = set()

    return templates.TemplateResponse(
        "admin/categories/create.html",
        {
            "request": request,
            "image_url": None,
            "categories": categories,
            "name_value": request.query_params.get("name", ""),
            "parent_id_value": selected_parent_id,
            "selected_parent_id": selected_parent_id,
            "confirm_required": False,
            "confirm_text": "",
            "cancel_url": "",
                                                                              
            "is_leaf": True,
            "characteristics": characteristics,
            "selected_characteristic_ids": selected_ids,
            "parent_set": request.query_params.get("parent_set", ""),

        },
    )


@router.post("/admin/categories/new", response_class=HTMLResponse)
async def category_create(
    request: Request,
    name: str = Form(...),
    parent_id: str | None = Form(None),
    characteristic_ids: list[int] | None = Form(None),
    confirm_move: str | None = Form(None),
    image: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_async_session),
):
    name_value = (name or "").strip()
    parent_uuid = uuid.UUID(parent_id) if parent_id else None

    if len(name_value) > CAT_NAME_MAX:
        categories = await _get_category_options(session)
        characteristics = await _get_all_characteristics(session)
        return templates.TemplateResponse(
            "admin/categories/create.html",
            {
                "request": request,
                "categories": categories,
                "cat_name_max": CAT_NAME_MAX,
                "characteristics": characteristics,
                "selected_characteristic_ids": set(_clean_int_list(characteristic_ids)),
                "error": f"Название категории не должно превышать {CAT_NAME_MAX} символов.",
                "parent_id_value": parent_id or "",
                "selected_parent_id": parent_id or "",
                "name_value": name_value,
                "confirm_required": False,
                "confirm_text": "",
                "cancel_url": "",
                "parent_set": "1",
                "is_leaf": True,
                "image_url": None,
            },
            status_code=400,
        )

    final_characteristic_ids: list[int]
    final_characteristic_ids = _clean_int_list(characteristic_ids)

    move_needed = False
    parent_name: str | None = None
    if parent_uuid:
        move_needed, parent_name = await _move_decision_for_parent(session, parent_uuid)

                                                  
    if move_needed and not _truthy(confirm_move):
        categories = await _get_category_options(session)
        characteristics = await _get_all_characteristics(session)

        cancel_url = "/admin/categories/new?" + urlencode({"name": name, "parent_id": parent_id or "", "parent_set": "1"})

        return templates.TemplateResponse(
            "admin/categories/create.html",
            {
                "request": request,
                "categories": categories,
                "parent_set": "1",
                "name_value": name,
                "parent_id_value": parent_id or "",
                "selected_parent_id": parent_id or "",
                "confirm_required": True,
                "confirm_text": (
                    f"Категория «{parent_name or 'Родительская'}» уже содержит товары. "
                    f"Они будут перенесены в создаваемую категорию «{name}»."
                ),
                "cancel_url": cancel_url,
                                                                                                           
                "is_leaf": True,
                "characteristics": characteristics,
                "selected_characteristic_ids": set(final_characteristic_ids),
            },
            status_code=200,
        )

    base = slugify(name)
    slug = await ensure_unique_slug(session, Category, base)

    try:
        category = Category(name=name, slug=slug, parent_id=parent_uuid)
        session.add(category)
        await session.flush()

                                                         
        if image and image.filename:
            try:
                saved_path = save_category_image(str(category.id), image)
                category.image_path = saved_path
            except ValueError as e:
                await session.rollback()

                categories = await _get_category_options(session)
                characteristics = await _get_all_characteristics(session)

                return templates.TemplateResponse(
                    "admin/categories/create.html",
                    {
                        "request": request,
                        "categories": categories,
                        "cat_name_max": CAT_NAME_MAX,
                        "name_value": name,
                        "parent_id_value": parent_id or "",
                        "selected_parent_id": parent_id or "",
                        "parent_set": "1",
                        "confirm_required": False,
                        "confirm_text": "",
                        "cancel_url": "",
                        "is_leaf": True,
                        "characteristics": characteristics,
                        "selected_characteristic_ids": set(final_characteristic_ids),
                        "image_url": None,
                        "image_error": str(e),
                    },
                    status_code=400,
                )

                                                           
        await _replace_category_characteristics(session, category.id, final_characteristic_ids)

                                             
        if move_needed and parent_uuid and _truthy(confirm_move):
            await session.execute(
                update(Product).where(Product.category_id == parent_uuid).values(category_id=category.id)
            )

        await session.commit()
    except Exception:
        await session.rollback()
        raise


    return RedirectResponse("/admin/categories", status_code=303)

@router.get("/admin/categories/{category_id}/edit", response_class=HTMLResponse)
async def category_edit_page(
    category_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    category_obj = await session.get(Category, category_id)
    current_parent_str = str(category_obj.parent_id) if category_obj.parent_id else ""
    selected_parent_id = request.query_params.get("parent_id", current_parent_str) or ""
    if not category_obj:
        raise HTTPException(status_code=404)

    descendants = await _get_subtree_category_ids(session, category_id)
    categories = await _get_category_options(session, exclude_ids=descendants)

    category = {
        "id": str(category_obj.id),
        "name": category_obj.name,
        "parent_id": str(category_obj.parent_id) if category_obj.parent_id else "",
    }

    name_value = request.query_params.get("name", category_obj.name)

    name_value = (name_value or "").strip()
    if len(name_value) > CAT_NAME_MAX:
        categories = await _get_category_options(session)
        characteristics = await _get_all_characteristics(session)
        return templates.TemplateResponse(
            "admin/categories/edit.html",
            {
                "request": request,
                "category": category,
                "categories": categories,
                "cat_name_max": CAT_NAME_MAX,
                "characteristics": characteristics,
                "selected_characteristic_ids": set(),
                "error": f"Название категории не должно превышать {CAT_NAME_MAX} символов.",
                "parent_id_value": current_parent_str,
                "name_value": name_value,
                "pending_change": False,
                "pending_parent": None,
            },
            status_code=400,
        )

    confirm_parent_change = request.query_params.get("confirm_parent_change") == "1"

    is_leaf = not await _has_children(session, category_id)
    can_edit_characteristics = is_leaf

    pending_change = False
    pending_parent = None

    characteristics: list[dict] = []
    selected_ids: set[int] = set()

    effective_parent_id_value = current_parent_str

    if can_edit_characteristics:
        characteristics = await _get_all_characteristics(session)

        if selected_parent_id != current_parent_str:
            if not confirm_parent_change:
                pending_change = True

                if selected_parent_id:
                    try:
                        pp_uuid = uuid.UUID(selected_parent_id)
                        pp = await session.get(Category, pp_uuid)
                        pending_parent = {"id": selected_parent_id, "name": pp.name if pp else "—"}
                    except Exception:
                        pending_parent = {"id": selected_parent_id, "name": "—"}
                else:
                    pending_parent = {"id": "", "name": "(нет)"}

                selected_ids = await _get_selected_characteristic_ids(session, category_id)
                effective_parent_id_value = current_parent_str
            else:
                if selected_parent_id:
                    selected_ids = await _get_selected_characteristic_ids(session, uuid.UUID(selected_parent_id))
                    effective_parent_id_value = selected_parent_id
                else:
                    selected_ids = set()
                    effective_parent_id_value = ""
        else:
            selected_ids = await _get_selected_characteristic_ids(session, category_id)
            effective_parent_id_value = current_parent_str

    image_url = category_obj.image_path

    return templates.TemplateResponse(
        "admin/categories/edit.html",
        {
            "request": request,
            "image_url": image_url,
            "category": category,
            "categories": categories,
            "name_value": name_value,
            "parent_id_value": selected_parent_id,
            "selected_parent_id": selected_parent_id,
            "current_parent_id": current_parent_str,
            "effective_parent_id_value": effective_parent_id_value,
            "pending_change": pending_change,
            "pending_parent": pending_parent,
            "confirm_required": False,
            "confirm_text": "",
            "cancel_url": "",
            "is_leaf": is_leaf,
            "can_edit_characteristics": can_edit_characteristics,
            "characteristics": characteristics,
            "selected_characteristic_ids": selected_ids,
        },
    )

@router.post("/admin/categories/{category_id}/edit", response_class=HTMLResponse)
async def category_edit(
    category_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    characteristic_ids: list[int] | None = Form(None),
    parent_id: str | None = Form(None),
    image: UploadFile | None = File(None),
    delete_image: str | None = Form(None),
    confirm_move: str | None = Form(None),
    session: AsyncSession = Depends(get_async_session),
):
    category_obj = await session.get(Category, category_id)
    if not category_obj:
        raise HTTPException(status_code=404)

    original_parent_id = category_obj.parent_id
    original_image_url = category_obj.image_path

    name = name.strip()
    new_parent_id = uuid.UUID(parent_id) if parent_id else None
    await _ensure_no_cycle(session, category_id, new_parent_id)

    is_leaf = not await _has_children(session, category_id)
    can_edit_characteristics = is_leaf

    parent_changed = (new_parent_id != category_obj.parent_id)

    if can_edit_characteristics:
        if parent_changed and new_parent_id and characteristic_ids is None:
            final_characteristic_ids = list(await _get_selected_characteristic_ids(session, new_parent_id))
        elif parent_changed and (not new_parent_id) and characteristic_ids is None:
            final_characteristic_ids = []
        elif characteristic_ids is None:
            final_characteristic_ids = list(await _get_selected_characteristic_ids(session, category_id))
        else:
            final_characteristic_ids = _clean_int_list(characteristic_ids)
    else:
        final_characteristic_ids = []

    move_needed = False
    parent_name: str | None = None
    if parent_changed and new_parent_id:
        move_needed, parent_name = await _move_decision_for_parent(session, new_parent_id)

    if move_needed and not _truthy(confirm_move):
        descendants = await _get_subtree_category_ids(session, category_id)
        categories = await _get_category_options(session, exclude_ids=descendants)

        cancel_url = f"/admin/categories/{category_id}/edit?" + urlencode({"name": name, "parent_id": parent_id or ""})

        category = {
            "id": str(category_obj.id),
            "name": category_obj.name,
            "parent_id": str(category_obj.parent_id) if category_obj.parent_id else "",
        }

        selected_ids = set(final_characteristic_ids)
        characteristics: list[dict] = []

        if can_edit_characteristics:
            characteristics = await _get_all_characteristics(session)
            if not selected_ids:
                selected_ids = await _get_selected_characteristic_ids(session, category_id)

        return templates.TemplateResponse(
            "admin/categories/edit.html",
            {
                "request": request,
                "category": category,
                "categories": categories,
                "name_value": name,
                "parent_id_value": parent_id or "",
                "selected_parent_id": parent_id or "",
                "current_parent_id": str(category_obj.parent_id) if category_obj.parent_id else "",
                "effective_parent_id_value": parent_id or "",
                "pending_change": False,
                "pending_parent": None,
                "confirm_required": True,
                "confirm_text": (
                    f"Категория «{parent_name or 'Родительская'}» уже содержит товары. "
                    f"Они будут перенесены в категорию «{name}»."
                ),
                "cancel_url": cancel_url,
                "is_leaf": is_leaf,
                "characteristics": characteristics,
                "selected_characteristic_ids": selected_ids,
                "image_url": category_obj.image_path,
            },
            status_code=200,
        )

    base = slugify(name)
    slug = await ensure_unique_slug(session, Category, base, exclude_id=category_id)

    category_obj.name = name
    category_obj.slug = slug
    category_obj.parent_id = new_parent_id

    try:
        await session.flush()

        if move_needed and new_parent_id and _truthy(confirm_move):
            await session.execute(
                update(Product).where(Product.category_id == new_parent_id).values(category_id=category_obj.id)
            )

        if can_edit_characteristics:
            await _replace_category_characteristics(session, category_id, final_characteristic_ids)

        if _truthy(delete_image):
            delete_category_image(str(category_id))
            category_obj.image_path = None

        if image and image.filename:
            try:
                saved_path = save_category_image(str(category_id), image)
                category_obj.image_path = saved_path
            except ValueError as e:
                await session.rollback()

                descendants = await _get_subtree_category_ids(session, category_id)
                categories = await _get_category_options(session, exclude_ids=descendants)

                is_leaf = not await _has_children(session, category_id)
                can_edit_characteristics = is_leaf

                category = {
                    "id": str(category_id),
                    "name": name,
                    "parent_id": str(new_parent_id) if new_parent_id else "",
                }

                characteristics = []
                selected_ids = set()

                if can_edit_characteristics:
                    characteristics = await _get_all_characteristics(session)
                    selected_ids = set(final_characteristic_ids)

                return templates.TemplateResponse(
                    "admin/categories/edit.html",
                    {
                        "request": request,
                        "category": category,
                        "categories": categories,
                        "name_value": name,
                        "parent_id_value": str(new_parent_id) if new_parent_id else "",
                        "selected_parent_id": str(new_parent_id) if new_parent_id else "",
                        "effective_parent_id_value": str(new_parent_id) if new_parent_id else "",
                        "current_parent_id": str(original_parent_id) if original_parent_id else "",
                        "pending_change": False,
                        "pending_parent": None,
                        "confirm_required": False,
                        "confirm_text": "",
                        "cancel_url": "",
                        "is_leaf": is_leaf,
                        "can_edit_characteristics": can_edit_characteristics,
                        "characteristics": characteristics,
                        "selected_characteristic_ids": selected_ids,
                        "image_url": original_image_url,
                        "error": str(e),
                    },
                    status_code=400,
                )

        await session.commit()

    except Exception:
        await session.rollback()
        raise

    return RedirectResponse("/admin/categories", status_code=303)

@router.post("/admin/categories/{category_id}/delete")
async def category_delete(category_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)):
    """Удаление категории вместе со всем деревом потомков и всеми товарами внутри."""
    files_to_delete: list[str] = []

    async with session.begin():
        category_ids = await _get_subtree_category_ids(session, category_id)
                                                  
        for cid in category_ids:
            delete_category_image(str(cid))

        if not category_ids:
            raise HTTPException(status_code=404)

        img_rows = await session.execute(
            select(ProductImage.file_path)
            .join(Product, ProductImage.product_id == Product.id)
            .where(Product.category_id.in_(category_ids))
        )
        files_to_delete = [r[0] for r in img_rows.all()]

        await session.execute(delete(Product).where(Product.category_id.in_(category_ids)))
        await session.execute(delete(Category).where(Category.id.in_(category_ids)))

    for p in files_to_delete:
        try:
            delete_product_image_if_local(p)
        except Exception:
            pass

    return RedirectResponse("/admin/categories", status_code=303)
