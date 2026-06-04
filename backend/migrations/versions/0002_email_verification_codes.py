"""email verification codes

Revision ID: 0002_email_verification_codes
Revises: 0001_initial_schema
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_email_verification_codes"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "email_verification_codes" not in tables:
        op.create_table(
            "email_verification_codes",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("code_hash", sa.String(), nullable=False),
            sa.Column("full_name", sa.String(), nullable=False),
            sa.Column("organization", sa.String(), nullable=True),
            sa.Column("password_hash", sa.String(), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=True),
            sa.Column("consumed", sa.Boolean(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    indexes = {
        index["name"]
        for index in sa.inspect(bind).get_indexes("email_verification_codes")
    }
    if "idx_email_verification_email" not in indexes:
        op.create_index("idx_email_verification_email", "email_verification_codes", ["email"])
    if "idx_email_verification_expires" not in indexes:
        op.create_index("idx_email_verification_expires", "email_verification_codes", ["expires_at"])


def downgrade() -> None:
    op.drop_index("idx_email_verification_expires", table_name="email_verification_codes")
    op.drop_index("idx_email_verification_email", table_name="email_verification_codes")
    op.drop_table("email_verification_codes")
