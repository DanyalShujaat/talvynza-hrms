"""Separate mobile and biometric access from web attendance."""
import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("mobile_attendance_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("employees", sa.Column("premises_attendance_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute("UPDATE employees SET mobile_attendance_enabled = attendance_enabled")


def downgrade() -> None:
    op.drop_column("employees", "premises_attendance_enabled")
    op.drop_column("employees", "mobile_attendance_enabled")
