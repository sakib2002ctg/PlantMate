"""Add timestamped ESP32 sensor readings."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_sensor_readings"
down_revision: str | None = "0002_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sensor_readings",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(length=100), nullable=False),
        sa.Column("soil_moisture", sa.Float(), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=False),
        sa.Column("humidity", sa.Float(), nullable=False),
        sa.Column("light_lux", sa.Float(), nullable=False),
        sa.Column("tds_ppm", sa.Float(), nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sensor_readings_device_id", "sensor_readings", ["device_id"])
    op.create_index("ix_sensor_readings_recorded_at", "sensor_readings", ["recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_sensor_readings_recorded_at", table_name="sensor_readings")
    op.drop_index("ix_sensor_readings_device_id", table_name="sensor_readings")
    op.drop_table("sensor_readings")
