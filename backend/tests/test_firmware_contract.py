"""Keep the ESP32 JSON builder aligned with the backend ingestion schema."""

from pathlib import Path

from app.modules.sensors.schemas import SensorReadingCreate

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = PROJECT_ROOT / "firmware" / "esp32" / "PlantMateESP32" / "PlantMateESP32.ino"
SECRETS_EXAMPLE = (
    PROJECT_ROOT / "firmware" / "esp32" / "PlantMateESP32" / "plantmate_secrets.h.example"
)


def test_firmware_contains_every_backend_payload_field() -> None:
    source = FIRMWARE.read_text(encoding="utf-8")
    assert all(field in source for field in SensorReadingCreate.model_fields)
    assert '"X-Device-Key"' in source
    assert "REPORT_INTERVAL_MS = 12000" in source


def test_local_firmware_configuration_is_template_only_and_ignored() -> None:
    template = SECRETS_EXAMPLE.read_text(encoding="utf-8")
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "replace-with-your-wifi-password" in template
    assert "copy-DEVICE_INGESTION_KEY-from-the-root-.env" in template
    assert "firmware/esp32/PlantMateESP32/plantmate_secrets.h" in gitignore


def test_firmware_keeps_tds_label_explicit() -> None:
    source = FIRMWARE.read_text(encoding="utf-8")
    assert "TDS from soil-water extract" in source
    assert "not direct soil EC" in source
