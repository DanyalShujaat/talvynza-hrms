"""One-time assistant action proposals.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("identity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"],
            name=op.f("fk_assistant_proposals_tenant_id_tenants"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["identity_id"], ["identities.id"], name=op.f("fk_assistant_proposals_identity_id_identities")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_proposals")),
    )
    op.create_index(op.f("ix_assistant_proposals_tenant_id"), "assistant_proposals", ["tenant_id"])
    op.create_index(op.f("ix_assistant_proposals_identity_id"), "assistant_proposals", ["identity_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_assistant_proposals_identity_id"), table_name="assistant_proposals")
    op.drop_index(op.f("ix_assistant_proposals_tenant_id"), table_name="assistant_proposals")
    op.drop_table("assistant_proposals")
