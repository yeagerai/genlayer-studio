"""merge_hardhat_migrations

Revision ID: 0d9538be0318
Revises: 1daddff774b2
Create Date: 2024-11-28 10:40:15.277640

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0d9538be0318"
down_revision: Union[str, None] = "1daddff774b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
