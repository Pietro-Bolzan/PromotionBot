"""generalize promotions to several stores

Revision ID: 8b461e8efea6
Revises: 557676fdb242
Create Date: 2026-11-09 08:46:45.633529

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b461e8efea6"
down_revision: str | Sequence[str] | None = "557676fdb242"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PENDING_ONLY = sa.text("status = 'PENDING'")
STORES = ("amazon", "shopee", "aliexpress")
OPTIONAL_COLUMNS = {
    "original_price": sa.Numeric(12, 2),
    "discounted_price": sa.Numeric(12, 2),
    "discount_percentage": sa.Numeric(5, 2),
    "category": sa.String(120),
}


def upgrade() -> None:
    """Upgrade schema."""
    # Every existing row came from the Amazon mock.
    op.add_column(
        "promotions",
        sa.Column("store", sa.String(20), nullable=False, server_default="amazon"),
    )
    # New rows must say which store they come from.
    op.alter_column("promotions", "store", server_default=None)
    op.create_check_constraint(
        "promotion_store",
        "promotions",
        sa.column("store").in_(STORES),
    )

    op.drop_index("uq_promotions_pending_asin", table_name="promotions")
    op.drop_index("ix_promotions_asin", table_name="promotions")
    op.alter_column(
        "promotions",
        "asin",
        new_column_name="external_id",
        type_=sa.String(64),
        existing_type=sa.String(20),
        existing_nullable=False,
    )
    op.create_index(
        "ix_promotions_store_external_id",
        "promotions",
        ["store", "external_id"],
    )
    op.create_index(
        "uq_promotions_pending_product",
        "promotions",
        ["store", "external_id"],
        unique=True,
        postgresql_where=PENDING_ONLY,
    )

    for column, type_ in OPTIONAL_COLUMNS.items():
        op.alter_column(
            "promotions",
            column,
            existing_type=type_,
            existing_nullable=False,
            nullable=True,
        )

    op.add_column(
        "promotions", sa.Column("affiliate_url", sa.String(1200), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    # The old schema can only hold Amazon promotions with every price: refuse
    # rather than silently deleting the rows that do not fit.
    incompatible = op.get_bind().scalar(
        sa.text(
            """
            SELECT count(*) FROM promotions
            WHERE store <> 'amazon'
               OR length(external_id) > 20
               OR original_price IS NULL
               OR discounted_price IS NULL
               OR discount_percentage IS NULL
               OR category IS NULL
            """
        )
    )
    if incompatible:
        raise RuntimeError(
            f"{incompatible} promotions do not fit the previous schema "
            "(another store, or a missing price or category); delete them "
            "before downgrading"
        )

    op.drop_column("promotions", "affiliate_url")

    for column, type_ in OPTIONAL_COLUMNS.items():
        op.alter_column(
            "promotions",
            column,
            existing_type=type_,
            existing_nullable=True,
            nullable=False,
        )

    op.drop_index(
        "uq_promotions_pending_product",
        table_name="promotions",
        postgresql_where=PENDING_ONLY,
    )
    op.drop_index("ix_promotions_store_external_id", table_name="promotions")
    op.alter_column(
        "promotions",
        "external_id",
        new_column_name="asin",
        type_=sa.String(20),
        existing_type=sa.String(64),
        existing_nullable=False,
    )
    op.create_index("ix_promotions_asin", "promotions", ["asin"])
    op.create_index(
        "uq_promotions_pending_asin",
        "promotions",
        ["asin"],
        unique=True,
        postgresql_where=PENDING_ONLY,
    )

    op.drop_constraint("promotion_store", "promotions", type_="check")
    op.drop_column("promotions", "store")
