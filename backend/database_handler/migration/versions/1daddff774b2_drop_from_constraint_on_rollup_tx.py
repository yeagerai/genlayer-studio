"""drop_from_constraint_on_rollup_tx

Revision ID: 1daddff774b2
Revises: 579e86111b36
Create Date: 2024-11-21 16:25:11.469033

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1daddff774b2"
down_revision: Union[str, None] = "579e86111b36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "rollup_transactions",
        "from_",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "rollup_transactions",
        "from_",
        existing_type=sa.String(length=255),
        nullable=False,
    )
