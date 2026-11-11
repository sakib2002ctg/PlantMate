"""Deterministic starter plant-care rules based on received measurements."""

from app.models.sensor_reading import SensorReading
from app.modules.sensors.schemas import CareStatus


def assess_plant_health(reading: SensorReading | None) -> CareStatus:
    """Report basic care guidance without estimating or inventing measurements."""

    if reading is None:
        return CareStatus(
            status="unavailable",
            message="Plant health will be available after the first sensor reading.",
        )

    issues: list[str] = []
    if reading.soil_moisture is not None:
        if reading.soil_moisture < 20:
            issues.append("soil is very dry")
        elif reading.soil_moisture < 35:
            issues.append("soil moisture is low")

    if reading.temperature_c > 35:
        issues.append("temperature is high")
    elif reading.temperature_c < 8:
        issues.append("temperature is low")

    if reading.humidity < 25:
        issues.append("air humidity is low")

    if not issues:
        if reading.soil_moisture is None:
            return CareStatus(
                status="unavailable",
                message="Soil moisture is raw ADC; calibrate it to enable moisture care guidance.",
            )
        return CareStatus(
            status="healthy", message="Current readings are within the starter care ranges."
        )
    return CareStatus(status="attention", message="Review: " + "; ".join(issues) + ".")
