"""add final_price_per_item to order_items

Revision ID: 629fd13d3c9f
Revises: 3ced8974d52b
Create Date: 2026-01-28 13:22:04.408600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '629fd13d3c9f'
down_revision: Union[str, Sequence[str], None] = '3ced8974d52b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "order_items",
        sa.Column("final_price_per_item", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("order_items", "final_price_per_item", server_default=None)

def downgrade():
    op.drop_column("order_items", "final_price_per_item")