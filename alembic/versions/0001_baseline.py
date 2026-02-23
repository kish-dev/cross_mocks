"""baseline

Revision ID: 0001_baseline
Revises: 
Create Date: 2026-02-23
"""

from typing import Sequence, Union
from alembic import op

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline revision for existing schema. Next schema changes must go via Alembic.
    pass


def downgrade() -> None:
    pass
