"""drop legacy email columns

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_column_if_exists(table: str, column: str) -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if table not in inspector.get_table_names():
        return
    cols = [c["name"] for c in inspector.get_columns(table)]
    if column not in cols:
        return
    with op.batch_alter_table(table) as batch_op:
        batch_op.drop_column(column)


def upgrade() -> None:
    for tbl in ("auth", "user"):
        _drop_column_if_exists(tbl, "email")


def downgrade() -> None:
    op.add_column("auth", sa.Column("email", sa.String(), nullable=True))
    op.add_column("user", sa.Column("email", sa.String(), nullable=True))
