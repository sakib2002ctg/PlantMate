"""Store uncalibrated soil and LDR ADC readings without relabeling them."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_raw_analog_readings"
down_revision: str | None = "0003_sensor_readings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("sensor_readings", "soil_moisture", existing_type=sa.Float(), nullable=True)
    op.alter_column("sensor_readings", "light_lux", existing_type=sa.Float(), nullable=True)
    op.add_column(
        "sensor_readings", sa.Column("soil_moisture_raw_adc", sa.Integer(), nullable=True)
    )
    op.add_column("sensor_readings", sa.Column("light_raw_adc", sa.Integer(), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    raw_only_count = connection.execute(
        sa.text(
            "SELECT count(*) FROM sensor_readings "
            "WHERE soil_moisture IS NULL OR light_lux IS NULL"
        )
    ).scalar_one()
    if raw_only_count:
        raise RuntimeError(
            "Cannot downgrade raw sensor readings until soil moisture and light are calibrated."
        )

    op.drop_column("sensor_readings", "soil_moisture_raw_adc")
    op.drop_column("sensor_readings", "light_raw_adc")
    op.alter_column("sensor_readings", "soil_moisture", existing_type=sa.Float(), nullable=False)
    op.alter_column("sensor_readings", "light_lux", existing_type=sa.Float(), nullable=False)
