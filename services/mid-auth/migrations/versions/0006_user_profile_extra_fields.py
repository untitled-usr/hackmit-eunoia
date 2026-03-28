"""add users gender/description columns

Revision ID: 0006_user_profile_extra_fields
Revises: 0005_numeric_public_id_backfill
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_user_profile_extra_fields"
down_revision: Union[str, None] = "0005_numeric_public_id_backfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("gender", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("description")
        batch.drop_column("gender")
