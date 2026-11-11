"""Add a single garden plant profile."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_plant_profile"
down_revision: str | None = "0004_raw_analog_readings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plant_profiles",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("plant_name", sa.String(100), nullable=False),
        sa.Column("species", sa.String(120), nullable=False),
        sa.Column("plant_type", sa.String(80), nullable=False),
        sa.Column("planting_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("device_id", sa.String(100), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id"),
    )


def downgrade() -> None:
    op.drop_table("plant_profiles")
