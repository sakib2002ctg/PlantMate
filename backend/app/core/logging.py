"""Small, consistent application logging setup."""

import logging

from app.core.config import get_settings


def configure_logging() -> None:
    """Configure standard-library logging without exposing configuration secrets."""

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
