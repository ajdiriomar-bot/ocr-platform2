"""add ice verification fields

Revision ID: 4c69a9e2f4db
Revises:
Create Date: 2026-07-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4c69a9e2f4db"
down_revision: Union[str, Sequence[str], None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "ice_verification_status",
            sa.String(length=30),
            nullable=False,
            server_default="non_verifie",
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "verified_company_name",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "ice_verification_message",
            sa.String(length=500),
            nullable=True,
        ),
    )

    op.add_column(
        "documents",
        sa.Column(
            "ice_verification_url",
            sa.String(length=500),
            nullable=True,
        ),
    )

    op.alter_column(
        "documents",
        "ice_verification_status",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("documents", "ice_verification_url")
    op.drop_column("documents", "ice_verification_message")
    op.drop_column("documents", "verified_company_name")
    op.drop_column("documents", "ice_verification_status")