"""add product slug

Revision ID: c7eb17f7d0bc
Revises: 629fd13d3c9f
Create Date: 2026-01-29 18:30:44.723185

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import re
import unicodedata


_RU_TO_LATIN = {
    "а": "a","б": "b","в": "v","г": "g","д": "d","е": "e","ё": "e","ж": "zh","з": "z",
    "и": "i","й": "i","к": "k","л": "l","м": "m","н": "n","о": "o","п": "p","р": "r",
    "с": "s","т": "t","у": "u","ф": "f","х": "h","ц": "ts","ч": "ch","ш": "sh","щ": "shch",
    "ъ": "","ы": "y","ь": "","э": "e","ю": "yu","я": "ya",
}

def slugify(value: str) -> str:
    transliterated = []
    for char in value.lower():
        if char in _RU_TO_LATIN:
            transliterated.append(_RU_TO_LATIN[char])
            continue

        normalized = unicodedata.normalize("NFKD", char)
        ascii_char = normalized.encode("ascii", "ignore").decode("ascii")
        transliterated.append(ascii_char)

    slug_base = "".join(transliterated)
    slug_base = re.sub(r"[^a-z0-9]+", "_", slug_base)
    slug_base = slug_base.strip("_")
    slug_base = re.sub(r"_+", "_", slug_base)
    return slug_base


def _ensure_unique(existing: set[str], base_slug: str, max_len: int = 255) -> str:
    base = (base_slug or "").strip("_")[:max_len]
    if not base:
        base = "item"

    slug = base
    i = 2
    while slug in existing:
        suffix = f"_{i}"
        cut = max_len - len(suffix)
        slug = (base[:cut].rstrip("_")) + suffix
        i += 1

    existing.add(slug)
    return slug

# revision identifiers, used by Alembic.
revision: str = 'c7eb17f7d0bc'
down_revision: Union[str, Sequence[str], None] = '629fd13d3c9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("slug", sa.String(length=255), nullable=True))

    conn = op.get_bind()

    existing = {
        r[0] for r in conn.execute(sa.text("SELECT slug FROM products WHERE slug IS NOT NULL")).fetchall()
    }

    rows = conn.execute(sa.text("SELECT id, name FROM products")).fetchall()
    for product_id, name in rows:
        base = slugify(name)
        slug = _ensure_unique(existing, base)
        conn.execute(
            sa.text("UPDATE products SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": product_id},
        )

    op.alter_column("products", "slug", nullable=False)

    op.create_index("ix_products_slug", "products", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_products_slug", table_name="products")
    op.drop_column("products", "slug")