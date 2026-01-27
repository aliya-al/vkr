"""add missing products.slug

Revision ID: 2caeb22d0a76
Revises: 51421f8b816c
Create Date: 2026-01-26 21:59:47.896323

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2caeb22d0a76'
down_revision = "bf765c9af85e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("slug", sa.String(length=255), nullable=True))

def downgrade() -> None:
    op.drop_column("products", "slug")

