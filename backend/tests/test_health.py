"""Unit tests for health route behavior and application routing."""

from unittest.mock import Mock

from sqlalchemy.exc import OperationalError

from app.api.v1.health import database_health_check, health_check
from app.main import app


def test_health_routes_are_registered_at_root_and_v1() -> None:
    routes = {route.path for route in app.routes if hasattr(route, "path")}
    assert {"/health", "/health/db", "/api/v1/health", "/api/v1/health/db"} <= routes


def test_health_check_reports_ok() -> None:
    assert health_check() == {"status": "ok"}


def test_database_health_check_executes_probe() -> None:
    database = Mock()
    response = database_health_check(database)
    assert response == {"status": "ok", "database": "ok"}
    database.execute.assert_called_once()


def test_database_health_check_returns_safe_503() -> None:
    database = Mock()
    database.execute.side_effect = OperationalError("SELECT 1", {}, RuntimeError("offline"))
    try:
        database_health_check(database)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
        assert getattr(exc, "detail", None) == "Database unavailable"
    else:
        raise AssertionError("database health should fail when SELECT 1 fails")


def test_unhandled_error_handler_is_registered() -> None:
    assert Exception in app.exception_handlers
