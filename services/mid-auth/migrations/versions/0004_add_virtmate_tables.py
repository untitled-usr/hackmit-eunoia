"""add virtmate session/global tables

Revision ID: 0004_add_virtmate_tables
Revises: 0003_user_avatar_columns
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_add_virtmate_tables"
down_revision: Union[str, None] = "0003_user_avatar_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "virtmate_user_globals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_virtmate_user_globals_user_id"),
    )
    op.create_index(
        "ix_virtmate_user_globals_user_id",
        "virtmate_user_globals",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "virtmate_session_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "session_id", name="uq_virtmate_session_settings"
        ),
    )
    op.create_index(
        "ix_virtmate_session_settings_user_session",
        "virtmate_session_settings",
        ["user_id", "session_id"],
        unique=False,
    )

    op.create_table(
        "virtmate_session_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "session_id", name="uq_virtmate_session_states"),
    )
    op.create_index(
        "ix_virtmate_session_states_user_session",
        "virtmate_session_states",
        ["user_id", "session_id"],
        unique=False,
    )

    op.create_table(
        "virtmate_session_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_virtmate_session_messages_user_session",
        "virtmate_session_messages",
        ["user_id", "session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_virtmate_session_messages_user_session",
        table_name="virtmate_session_messages",
    )
    op.drop_table("virtmate_session_messages")

    op.drop_index(
        "ix_virtmate_session_states_user_session", table_name="virtmate_session_states"
    )
    op.drop_table("virtmate_session_states")

    op.drop_index(
        "ix_virtmate_session_settings_user_session",
        table_name="virtmate_session_settings",
    )
    op.drop_table("virtmate_session_settings")

    op.drop_index("ix_virtmate_user_globals_user_id", table_name="virtmate_user_globals")
    op.drop_table("virtmate_user_globals")

