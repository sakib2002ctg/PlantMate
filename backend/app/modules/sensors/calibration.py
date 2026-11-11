"""Measured sensor calibration references and derived measurement helpers.

The current LDR reference points are dark=4095 ADC and bright=60 ADC.
This maps the measured ADC range to relative brightness only; it is not lux.
"""

LIGHT_DARK_ADC = 4095
LIGHT_BRIGHT_ADC = 60
ADC_MAX = 4095


def relative_light_percent(raw_adc: int) -> float:
    """Convert a valid ESP32 ADC count to clamped relative light percent."""

    if isinstance(raw_adc, bool) or not isinstance(raw_adc, int) or not 0 <= raw_adc <= ADC_MAX:
        raise ValueError("light ADC must be an integer from 0 through 4095")
    percent = ((LIGHT_DARK_ADC - raw_adc) / (LIGHT_DARK_ADC - LIGHT_BRIGHT_ADC)) * 100
    return min(100.0, max(0.0, percent))
