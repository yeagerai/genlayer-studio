"""appeal_processing_time

Revision ID: d932a5fef8b1
Revises: 2de9c3151194
Create Date: 2025-01-31 15:39:44.618075

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d932a5fef8b1"
down_revision: Union[str, None] = "2de9c3151194"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "transactions", sa.Column("timestamp_appeal", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("appeal_processing_time", sa.Integer(), nullable=True)
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("transactions", "appeal_processing_time")
    op.drop_column("transactions", "timestamp_appeal")
    # ### end Alembic commands ###
