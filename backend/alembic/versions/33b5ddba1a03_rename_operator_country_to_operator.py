"""rename operator_country to operator

The SATCAT OWNER column we populate this field from holds country codes
(US, PRC) AND organization codes (INTELSAT, PLAN, SES). "Country" was
misleading; "operator" matches the broader semantic.

Revision ID: 33b5ddba1a03
Revises: 3d6183811fdf
Create Date: 2026-05-09 00:50:22.676966

"""

from typing import Sequence, Union

from alembic import op

revision: str = "33b5ddba1a03"
down_revision: Union[str, Sequence[str], None] = "3d6183811fdf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("satellites", "operator_country", new_column_name="operator")


def downgrade() -> None:
    op.alter_column("satellites", "operator", new_column_name="operator_country")
