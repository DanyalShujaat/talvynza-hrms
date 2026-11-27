"""Branch premises and employee self-service attendance access.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("branches", sa.Column("email", sa.String(320), nullable=True))
    op.add_column("branches", sa.Column("premises", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("employees", sa.Column("attendance_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("employees", "attendance_enabled")
    op.drop_column("branches", "premises")
    op.drop_column("branches", "email")
