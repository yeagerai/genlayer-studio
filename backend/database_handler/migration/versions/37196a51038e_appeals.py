"""appeals

Revision ID: 37196a51038e
Revises: 1ecaa2085aec
Create Date: 2024-10-25 17:39:00.130046

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "37196a51038e"
down_revision: Union[str, None] = "1ecaa2085aec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_unique_constraint(None, "rollup_transactions", ["transaction_hash"])
    op.add_column("transactions", sa.Column("appeal", sa.Boolean(), nullable=False))
    op.add_column(
        "transactions", sa.Column("timestamp_accepted", sa.BigInteger(), nullable=True)
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("transactions", "timestamp_accepted")
    op.drop_column("transactions", "appeal")
    op.drop_constraint(None, "rollup_transactions", type_="unique")
    # ### end Alembic commands ###
