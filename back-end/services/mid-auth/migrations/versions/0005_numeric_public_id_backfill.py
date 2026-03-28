"""backfill users.public_id to numeric ids

Revision ID: 0005_numeric_public_id_backfill
Revises: 0004_add_virtmate_tables
"""

from __future__ import annotations

import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_numeric_public_id_backfill"
down_revision: Union[str, None] = "0004_add_virtmate_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PUBLIC_ID_RE = re.compile(r"^[1-9][0-9]{7,}$")


def upgrade() -> None:
    conn = op.get_bind()
    rows = (
        conn.execute(
            sa.text(
                "SELECT id, public_id FROM users ORDER BY created_at ASC, id ASC"
            )
        )
        .mappings()
        .all()
    )
    used: set[str] = set()
    for row in rows:
        pid = str(row["public_id"] or "").strip()
        if _PUBLIC_ID_RE.match(pid):
            used.add(pid)

    next_value = 10_000_000
    updates: list[tuple[str, str]] = []
    for row in rows:
        old = str(row["public_id"] or "").strip()
        if _PUBLIC_ID_RE.match(old):
            continue
        while str(next_value) in used:
            next_value += 1
        new_pid = str(next_value)
        next_value += 1
        used.add(new_pid)
        updates.append((str(row["id"]), new_pid))

    for user_id, new_pid in updates:
        conn.execute(
            sa.text("UPDATE users SET public_id = :public_id WHERE id = :id"),
            {"id": user_id, "public_id": new_pid},
        )

    if conn.dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_users_public_id_numeric'
              ) THEN
                ALTER TABLE users
                ADD CONSTRAINT ck_users_public_id_numeric
                CHECK (public_id ~ '^[1-9][0-9]{7,}$');
              END IF;
            END
            $$;
            """
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute(
            """
            ALTER TABLE users
            DROP CONSTRAINT IF EXISTS ck_users_public_id_numeric
            """
        )
