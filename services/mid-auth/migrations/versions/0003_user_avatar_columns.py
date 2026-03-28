"""add users.avatar_* for mid-auth profile photos

Revision ID: 0003_user_avatar_columns
Revises: 0002_drop_users_is_admin
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_user_avatar_columns"
down_revision: Union[str, None] = "0002_drop_users_is_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("avatar_mime_type", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("avatar_data", sa.LargeBinary(), nullable=True))
        batch.add_column(
            sa.Column("avatar_updated_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("avatar_updated_at")
        batch.drop_column("avatar_data")
        batch.drop_column("avatar_mime_type")
