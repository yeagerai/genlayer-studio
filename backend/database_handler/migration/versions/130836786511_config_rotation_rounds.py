"""config_rotation_rounds

Revision ID: 130836786511
Revises: d932a5fef8b1
Create Date: 2025-01-16 16:01:59.319254

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "130836786511"
down_revision: Union[str, None] = "d932a5fef8b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "transactions", sa.Column("config_rotation_rounds", sa.Integer(), nullable=True)
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("transactions", "config_rotation_rounds")
    # ### end Alembic commands ###
