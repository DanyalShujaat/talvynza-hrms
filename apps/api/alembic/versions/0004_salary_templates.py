"""Reusable salary templates and revision provenance.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "salary_templates",
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("basic", sa.Numeric(14, 2), nullable=False),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column("increment_type", sa.String(10), nullable=False),
        sa.Column("increment_value", sa.Numeric(14, 4), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_salary_templates_tenant_id_tenants"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_salary_templates")),
        sa.UniqueConstraint("tenant_id", "name", name="uq_salary_template_name"),
    )
    op.create_index(op.f("ix_salary_templates_tenant_id"), "salary_templates", ["tenant_id"])
    with op.batch_alter_table("salary_revisions") as batch_op:
        batch_op.add_column(sa.Column("template_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(op.f("fk_salary_revisions_template_id_salary_templates"), "salary_templates", ["template_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("salary_revisions") as batch_op:
        batch_op.drop_constraint(op.f("fk_salary_revisions_template_id_salary_templates"), type_="foreignkey")
        batch_op.drop_column("template_id")
    op.drop_index(op.f("ix_salary_templates_tenant_id"), table_name="salary_templates")
    op.drop_table("salary_templates")
