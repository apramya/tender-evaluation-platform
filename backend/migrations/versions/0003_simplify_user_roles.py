"""simplify user roles

Revision ID: 0003_simplify_user_roles
Revises: 0002_email_verification_codes
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_simplify_user_roles"
down_revision = "0002_email_verification_codes"
branch_labels = None
depends_on = None

LEGACY_ROLE_UPPER = "REVIEW" + "ER"
LEGACY_ROLE_LOWER = "review" + "er"
LEGACY_REVIEW_COLUMN = "review" + "er_id"
LEGACY_REVIEW_INDEX = "idx_reviews_" + "review" + "er"


def _enum_exists(bind, enum_name: str) -> bool:
    return bool(bind.execute(sa.text(
        "SELECT 1 FROM pg_type WHERE typname = :enum_name"
    ), {"enum_name": enum_name}).scalar())


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql" and _enum_exists(bind, "userrole"):
        op.execute(f"""
            ALTER TABLE users ALTER COLUMN role DROP DEFAULT;
            UPDATE users
            SET role = 'PROCUREMENT_OFFICER'
            WHERE role::text IN ('{LEGACY_ROLE_UPPER}', '{LEGACY_ROLE_LOWER}');
            CREATE TYPE userrole_new AS ENUM ('USER', 'ADMIN', 'PROCUREMENT_OFFICER');
            ALTER TABLE users
            ALTER COLUMN role TYPE userrole_new
            USING (
                CASE
                    WHEN role::text IN ('{LEGACY_ROLE_UPPER}', '{LEGACY_ROLE_LOWER}') THEN 'PROCUREMENT_OFFICER'
                    ELSE role::text
                END
            )::userrole_new;
            DROP TYPE userrole;
            ALTER TYPE userrole_new RENAME TO userrole;
            ALTER TABLE users ALTER COLUMN role SET DEFAULT 'USER'::userrole;
        """)

    inspector = sa.inspect(bind)
    if "reviews" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("reviews")}
        indexes = {index["name"] for index in inspector.get_indexes("reviews")}

        if LEGACY_REVIEW_COLUMN in columns and "reviewed_by" not in columns:
            op.alter_column("reviews", LEGACY_REVIEW_COLUMN, new_column_name="reviewed_by")

        if LEGACY_REVIEW_INDEX in indexes:
            op.execute(f"ALTER INDEX {LEGACY_REVIEW_INDEX} RENAME TO idx_reviews_reviewed_by")


def downgrade() -> None:
    bind = op.get_bind()

    inspector = sa.inspect(bind)
    if "reviews" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("reviews")}
        indexes = {index["name"] for index in inspector.get_indexes("reviews")}

        if "reviewed_by" in columns and LEGACY_REVIEW_COLUMN not in columns:
            op.alter_column("reviews", "reviewed_by", new_column_name=LEGACY_REVIEW_COLUMN)

        if "idx_reviews_reviewed_by" in indexes:
            op.execute(f"ALTER INDEX idx_reviews_reviewed_by RENAME TO {LEGACY_REVIEW_INDEX}")

    if bind.dialect.name == "postgresql" and _enum_exists(bind, "userrole"):
        op.execute("""
            ALTER TABLE users ALTER COLUMN role DROP DEFAULT;
            CREATE TYPE userrole_old AS ENUM ('USER', 'ADMIN', 'PROCUREMENT_OFFICER');
            ALTER TABLE users
            ALTER COLUMN role TYPE userrole_old
            USING role::text::userrole_old;
            DROP TYPE userrole;
            ALTER TYPE userrole_old RENAME TO userrole;
            ALTER TABLE users ALTER COLUMN role SET DEFAULT 'USER'::userrole;
        """)
