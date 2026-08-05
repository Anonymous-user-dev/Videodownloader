"""add download job status

Revision ID: a38c7420f06d
Revises: f459bfa772ef
Create Date: 2026-08-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a38c7420f06d"
down_revision: Union[str, Sequence[str], None] = "f459bfa772ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("downloads", sa.Column("request_id", sa.String(length=36), nullable=True))
    op.add_column("downloads", sa.Column("status", sa.String(length=20), nullable=True))
    op.add_column(
        "downloads",
        sa.Column("requested_quality", sa.Integer(), server_default="1080", nullable=False),
    )
    op.add_column("downloads", sa.Column("error_code", sa.String(length=50), nullable=True))
    op.add_column("downloads", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("downloads", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "downloads",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.execute("UPDATE downloads SET status = 'sent' WHERE status IS NULL")
    op.alter_column(
        "downloads",
        "status",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="queued",
    )
    op.create_index("ix_downloads_request_id", "downloads", ["request_id"], unique=True)
    op.create_index("ix_downloads_status", "downloads", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_downloads_status", table_name="downloads")
    op.drop_index("ix_downloads_request_id", table_name="downloads")
    op.drop_column("downloads", "updated_at")
    op.drop_column("downloads", "completed_at")
    op.drop_column("downloads", "started_at")
    op.drop_column("downloads", "error_code")
    op.drop_column("downloads", "requested_quality")
    op.drop_column("downloads", "status")
    op.drop_column("downloads", "request_id")
