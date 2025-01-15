"""remove rollup transactions table

Revision ID: b9421e9f12aa
Revises: 37196a51038e
Create Date: 2024-12-05 10:01:15.224567

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = "b9421e9f12aa"
down_revision: Union[str, None] = "37196a51038e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if rollup_transactions table exists before dropping
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    if "rollup_transactions" in tables:
        op.drop_table("rollup_transactions")


def downgrade() -> None:
    # Recreate the rollup_transactions table in case of rollback
    op.create_table(
        "rollup_transactions",
        sa.Column("transaction_hash", sa.String(length=66), nullable=False),
        sa.Column("from_", sa.String(length=255), nullable=True),
        sa.Column("to_", sa.String(length=255), nullable=True),
        sa.Column("gas", sa.Integer(), nullable=False),
        sa.Column("gas_price", sa.Integer(), nullable=False),
        sa.Column("value", sa.Integer(), nullable=True),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("nonce", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("transaction_hash", name="rollup_transactions_pkey"),
        sa.UniqueConstraint("transaction_hash", name="rollup_transactions_hash"),
    )
