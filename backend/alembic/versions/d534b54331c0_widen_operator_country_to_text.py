"""widen operator_country to text

CelesTrak country codes vary in length (US, PRC, USSR, ESRO, INTELSAT)
so the original CHAR(2) constraint cannot store the full set.

Revision ID: d534b54331c0
Revises: a1b2c3d4e5f6
Create Date: 2026-05-08 23:44:07.018213

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d534b54331c0"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "satellites",
        "operator_country",
        existing_type=sa.CHAR(length=2),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "satellites",
        "operator_country",
        existing_type=sa.Text(),
        type_=sa.CHAR(length=2),
        existing_nullable=True,
        postgresql_using="left(operator_country, 2)",
    )
