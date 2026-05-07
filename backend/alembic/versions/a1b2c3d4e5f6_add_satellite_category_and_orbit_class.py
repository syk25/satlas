"""add satellite_category and populate orbit_class

Revision ID: a1b2c3d4e5f6
Revises: c42c5fcb7c2a
Create Date: 2026-05-07 21:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c42c5fcb7c2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

satellite_category = sa.Enum(
    "STATION",
    "WEATHER",
    "GNSS",
    "MILITARY",
    "AMATEUR",
    "COMMERCIAL",
    "EARTH_OBS",
    "SCIENTIFIC",
    "OTHER",
    name="satellite_category",
)


def upgrade() -> None:
    satellite_category.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "satellites",
        sa.Column("category", satellite_category, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("satellites", "category")
    satellite_category.drop(op.get_bind(), checkfirst=True)
