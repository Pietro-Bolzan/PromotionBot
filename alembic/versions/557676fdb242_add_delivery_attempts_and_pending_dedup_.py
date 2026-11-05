"""add delivery attempts and pending dedup index

Revision ID: 557676fdb242
Revises: ccf55b7bb21d
Create Date: 2026-11-05 19:37:33.604129

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "557676fdb242"
down_revision: str | Sequence[str] | None = "ccf55b7bb21d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PENDING_ONLY = sa.text("status = 'PENDING'")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "promotions",
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("promotions", sa.Column("last_error", sa.Text(), nullable=True))

    # Before this migration there were no retries: every row already SENT or
    # FAILED was tried exactly once.
    op.execute("UPDATE promotions SET attempts = 1 WHERE status IN ('SENT', 'FAILED')")

    # The unique index below cannot be created while an ASIN has more than one
    # PENDING row, which the old deduplication allowed. Keep the oldest one
    # open and close the others, recording why. Not reverted on downgrade.
    op.execute(
        """
        UPDATE promotions AS p
        SET status = 'FAILED',
            last_error = 'Superseded by an older PENDING row for the same ASIN '
                         '(migration 557676fdb242)'
        WHERE p.status = 'PENDING'
          AND EXISTS (
              SELECT 1
              FROM promotions AS older
              WHERE older.asin = p.asin
                AND older.status = 'PENDING'
                AND (older.created_at, older.id) < (p.created_at, p.id)
          )
        """
    )

    op.create_index(
        "ix_promotions_pending_created_at",
        "promotions",
        ["created_at"],
        unique=False,
        postgresql_where=PENDING_ONLY,
    )
    op.create_index(
        "uq_promotions_pending_asin",
        "promotions",
        ["asin"],
        unique=True,
        postgresql_where=PENDING_ONLY,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_promotions_pending_asin",
        table_name="promotions",
        postgresql_where=PENDING_ONLY,
    )
    op.drop_index(
        "ix_promotions_pending_created_at",
        table_name="promotions",
        postgresql_where=PENDING_ONLY,
    )
    op.drop_column("promotions", "last_error")
    op.drop_column("promotions", "attempts")
