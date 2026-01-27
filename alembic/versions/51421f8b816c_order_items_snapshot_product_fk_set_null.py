"""order_items snapshot + product fk set null

Revision ID: 51421f8b816c
Revises: bf765c9af85e
Create Date: 2026-01-26 21:24:31.549490

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "51421f8b816c"
down_revision: Union[str, Sequence[str], None] = "bf765c9af85e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # product_id -> nullable
    op.alter_column(
        "order_items",
        "product_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    #  snapshot columns
    # product_name добавим nullable, заполним, потом сделаем NOT NULL
    op.add_column("order_items", sa.Column("product_name", sa.String(length=255), nullable=True))
    op.add_column("order_items", sa.Column("product_slug", sa.String(length=255), nullable=True))
    op.add_column("order_items", sa.Column("product_sku", sa.String(length=100), nullable=True))
    op.add_column("order_items", sa.Column("product_image", sa.String(), nullable=True))

    # веса/объёмы — NOT NULL, нужны server_default чтобы не упасть на существующих строках
    op.add_column("order_items", sa.Column("weight_kg", sa.Float(), nullable=False, server_default=sa.text("0")))
    op.add_column("order_items", sa.Column("volume_m3", sa.Float(), nullable=False, server_default=sa.text("0")))

    #  backfill для старых order_items из products (если products ещё есть)
    # Предполагаем, что в products есть поля: id, name, slug, weight_kg, volume_m3.
    op.execute(
        """
        UPDATE order_items oi
        SET
            product_name = p.name,
            product_slug = p.slug,
            weight_kg = COALESCE(p.weight_kg, 0),
            volume_m3 = COALESCE(p.volume_m3, 0)
        FROM products p
        WHERE oi.product_id = p.id;
        """
    )

    # Если часть товаров уже удаляли/нет данных — подстрахуемся
    op.execute(
        """
        UPDATE order_items
        SET product_name = 'Удалённый товар'
        WHERE product_name IS NULL;
        """
    )

    # теперь делаем NOT NULL
    op.alter_column(
        "order_items",
        "product_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    #  убрать server_default у вес/объём (оставляем default уже в приложении)
    op.alter_column("order_items", "weight_kg", existing_type=sa.Float(), server_default=None, nullable=False)
    op.alter_column("order_items", "volume_m3", existing_type=sa.Float(), server_default=None, nullable=False)


    op.execute(
        """
        DO $$
        DECLARE r record;
        BEGIN
          FOR r IN
            SELECT conname
            FROM pg_constraint
            WHERE conrelid = 'order_items'::regclass
              AND contype = 'f'
          LOOP
            EXECUTE format('ALTER TABLE order_items DROP CONSTRAINT %I', r.conname);
          END LOOP;
        END $$;
        """
    )

    # FK на orders (как было)
    op.create_foreign_key(
        "order_items_order_id_fkey",
        "order_items",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # FK на products (нужно для разрешения удаления товаров)
    op.create_foreign_key(
        "order_items_product_id_fkey",
        "order_items",
        "products",
        ["product_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM order_items WHERE product_id IS NULL) THEN
            RAISE EXCEPTION 'Cannot downgrade: order_items.product_id has NULL values (products were deleted).';
          END IF;
        END $$;
        """
    )

    # удалить FK (универсально)
    op.execute(
        """
        DO $$
        DECLARE r record;
        BEGIN
          FOR r IN
            SELECT conname
            FROM pg_constraint
            WHERE conrelid = 'order_items'::regclass
              AND contype = 'f'
          LOOP
            EXECUTE format('ALTER TABLE order_items DROP CONSTRAINT %I', r.conname);
          END LOOP;
        END $$;
        """
    )

    # вернуть product_id NOT NULL
    op.alter_column(
        "order_items",
        "product_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    # вернуть FK на orders (как минимум)
    op.create_foreign_key(
        "order_items_order_id_fkey",
        "order_items",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # вернуть FK на products без ondelete (как было изначально)
    op.create_foreign_key(
        "order_items_product_id_fkey",
        "order_items",
        "products",
        ["product_id"],
        ["id"],
        ondelete=None,
    )

    # удалить snapshot-колонки
    op.drop_column("order_items", "product_image")
    op.drop_column("order_items", "volume_m3")
    op.drop_column("order_items", "weight_kg")
    op.drop_column("order_items", "product_sku")
    op.drop_column("order_items", "product_slug")
    op.drop_column("order_items", "product_name")
