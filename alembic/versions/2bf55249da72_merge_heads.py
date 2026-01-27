"""merge heads

Revision ID: 2bf55249da72
Revises: 51421f8b816c, 2caeb22d0a76
Create Date: 2026-01-26 22:02:33.113120

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2bf55249da72'
down_revision: Union[str, Sequence[str], None] = ('51421f8b816c', '2caeb22d0a76')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
