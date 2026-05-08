"""add object_type, rcs_size, international_designator, decay_date

Adds the four CelesTrak GP fields available alongside TLE lines so we can
filter out rocket bodies / debris from the user-facing satellite list and
expose richer detail-panel info without re-fetching.

Revision ID: 3d6183811fdf
Revises: d534b54331c0
Create Date: 2026-05-08 23:53:31.108124

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3d6183811fdf"
down_revision: Union[str, Sequence[str], None] = "d534b54331c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


object_type_enum = sa.Enum(
    "PAYLOAD",
    "ROCKET_BODY",
    "DEBRIS",
    "UNKNOWN",
    name="object_type",
)

rcs_size_enum = sa.Enum(
    "LARGE",
    "MEDIUM",
    "SMALL",
    "UNKNOWN",
    name="rcs_size",
)


def upgrade() -> None:
    object_type_enum.create(op.get_bind(), checkfirst=True)
    rcs_size_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "satellites",
        sa.Column("international_designator", sa.Text(), nullable=True),
    )
    op.add_column(
        "satellites",
        sa.Column("object_type", object_type_enum, nullable=True),
    )
    op.add_column(
        "satellites",
        sa.Column("rcs_size", rcs_size_enum, nullable=True),
    )
    op.add_column(
        "satellites",
        sa.Column("decay_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("satellites", "decay_date")
    op.drop_column("satellites", "rcs_size")
    op.drop_column("satellites", "object_type")
    op.drop_column("satellites", "international_designator")
    rcs_size_enum.drop(op.get_bind(), checkfirst=True)
    object_type_enum.drop(op.get_bind(), checkfirst=True)
