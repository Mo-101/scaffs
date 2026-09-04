import os
import pytest
from src.db_dsn import assert_safe_test_database, resolve_dsn


def test_pytest_can_never_connect_to_production():
    """CI test asserting that pytest connecting to production database fails immediately."""
    production_dsn = "postgresql://postgres:mostar@127.0.0.1:5434/mostar"
    with pytest.raises(RuntimeError, match="REFUSING TEST EXECUTION AGAINST PRODUCTION DATABASE"):
        assert_safe_test_database(production_dsn)


def test_test_environment_requires_test_dbname_suffix():
    """Test databases must end with _test."""
    invalid_test_dsn = "postgresql://postgres:mostar@127.0.0.1:5434/trading_data"
    with pytest.raises(RuntimeError, match="must end in '_test'"):
        assert_safe_test_database(invalid_test_dsn)


def test_unreachable_explicit_dsn_fails_hard():
    """Explicitly specified unreachable DSN must fail hard and never silently fall back."""
    os.environ["VIBE_PAPER_DATABASE_URL"] = "postgresql://postgres:mostar@127.0.0.1:9999/unreachable_test"
    try:
        with pytest.raises(RuntimeError, match="Configured database DSN is unreachable"):
            resolve_dsn()
    finally:
        del os.environ["VIBE_PAPER_DATABASE_URL"]
