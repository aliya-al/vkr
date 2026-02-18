#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from sqlalchemy import select

from app.models.order_item import OrderItem
from app.models.product import Product
from app.utils.database import async_session_maker


@dataclass
class CleanupStats:
    null_product_id: int
    empty_slug: int
    missing_product: int
    product_empty_slug: int
    total_unique: int


async def collect_invalid_ids(session) -> tuple[set[int], CleanupStats]:
    null_product_id_rows = await session.scalars(
        select(OrderItem.id).where(OrderItem.product_id.is_(None))
    )
    empty_slug_rows = await session.scalars(
        select(OrderItem.id).where(
            OrderItem.product_slug.is_(None) | (OrderItem.product_slug == "")
        )
    )
    missing_product_rows = await session.scalars(
        select(OrderItem.id)
        .outerjoin(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.product_id.is_not(None), Product.id.is_(None))
    )
    product_empty_slug_rows = await session.scalars(
        select(OrderItem.id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(Product.slug.is_(None) | (Product.slug == ""))
    )

    null_product_id = set(null_product_id_rows.all())
    empty_slug = set(empty_slug_rows.all())
    missing_product = set(missing_product_rows.all())
    product_empty_slug = set(product_empty_slug_rows.all())

    all_invalid = null_product_id | empty_slug | missing_product | product_empty_slug
    stats = CleanupStats(
        null_product_id=len(null_product_id),
        empty_slug=len(empty_slug),
        missing_product=len(missing_product),
        product_empty_slug=len(product_empty_slug),
        total_unique=len(all_invalid),
    )
    return all_invalid, stats


async def print_examples(session, invalid_ids: set[int], limit: int = 10) -> None:
    if not invalid_ids:
        print("Примеры: не найдены")
        return

    rows = (
        await session.execute(
            select(
                OrderItem.id,
                OrderItem.order_id,
                OrderItem.product_id,
                OrderItem.product_slug,
                OrderItem.product_name,
            )
            .where(OrderItem.id.in_(sorted(invalid_ids)))
            .order_by(OrderItem.id.asc())
            .limit(limit)
        )
    ).all()

    print("Примеры строк для удаления:")
    for row in rows:
        print(
            f"  id={row.id} order_id={row.order_id} product_id={row.product_id} "
            f"slug={row.product_slug!r} name={row.product_name!r}"
        )


async def cleanup(dry_run: bool) -> None:
    async with async_session_maker() as session:
        async with session.begin():
            invalid_ids, stats = await collect_invalid_ids(session)

            print("Найдено проблемных позиций order_items:")
            print(f"  - product_id IS NULL: {stats.null_product_id}")
            print(f"  - product_slug IS NULL/empty: {stats.empty_slug}")
            print(f"  - product_id без записи в products: {stats.missing_product}")
            print(f"  - product со slug NULL/empty: {stats.product_empty_slug}")
            print(f"  - уникальных строк к удалению: {stats.total_unique}")
            await print_examples(session, invalid_ids)

            if dry_run:
                print("DRY-RUN: удаление не выполнено.")
                await session.rollback()
                return

            if not invalid_ids:
                print("Нечего удалять.")
                return

            deleted = await session.execute(
                OrderItem.__table__.delete().where(OrderItem.id.in_(sorted(invalid_ids)))
            )
            print(f"Удалено строк: {deleted.rowcount or 0}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Очистка битых записей order_items для корректной аналитики top-products"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только показать, что будет удалено, без изменений в БД",
    )
    args = parser.parse_args()
    asyncio.run(cleanup(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
