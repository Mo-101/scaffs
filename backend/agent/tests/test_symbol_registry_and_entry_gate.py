"""Symbol allowlist must come from exchange metadata, not a character class.

Binance USD-M lists Chinese-character perpetuals, so "non-ASCII" is not
evidence a market is fake. The real discriminator is `status`: 龙虾USDT and
the ASCII ZKCUSDT were both PENDING_TRADING, which is why set_margin_type
failed on them and reported a misleading MARGIN_MODE_MISMATCH.

Also pins the new-entry kill switch, which previously existed in .env and in
every deploy script while being read by no code at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

agent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(agent_dir))
sys.path.insert(0, str(agent_dir / "src"))

from src.trading import symbol_registry
from src.trading.symbol_registry import (
    SYMBOL_NOT_TRADING_BLOCKED,
    UNSUPPORTED_SYMBOL_BLOCKED,
    resolve_market,
)
from src.trading.entry_gate import new_entries_enabled


def _market(symbol, status="TRADING", contract="PERPETUAL", quote="USDT"):
    return {"symbol": symbol, "status": status, "contractType": contract, "quoteAsset": quote}


class FakeClient:
    """Serves a fixed exchangeInfo; counts fetches to prove caching."""

    def __init__(self, markets, fail=False):
        self._markets = markets
        self.fail = fail
        self.calls = 0

    def _request(self, method, path, params=None, signed=False):
        self.calls += 1
        if self.fail:
            raise RuntimeError("exchangeInfo unreachable")
        return {"symbols": self._markets}


@pytest.fixture(autouse=True)
def _clear_cache():
    symbol_registry._markets = {}
    symbol_registry._fetched_at = 0.0
    yield
    symbol_registry._markets = {}
    symbol_registry._fetched_at = 0.0


DEFAULT = [
    _market("BTCUSDT"),
    _market("1000PEPEUSDT"),
    _market("币安人生USDT"),
    _market("龙虾USDT", status="PENDING_TRADING"),
    _market("ZKCUSDT", status="PENDING_TRADING"),
    _market("OLDUSDT", status="SETTLING"),
    _market("BTCUSDC", quote="USDC"),
    _market("BTCUSDT_251226", contract="CURRENT_QUARTER"),
]


def test_plain_ascii_symbol_passes():
    market, block, _ = resolve_market(FakeClient(DEFAULT), "BTCUSDT")
    assert block is None
    assert market["symbol"] == "BTCUSDT"


def test_numeric_prefix_symbol_passes():
    """1000-prefixed tokens are ordinary listed markets."""
    _, block, _ = resolve_market(FakeClient(DEFAULT), "1000PEPEUSDT")
    assert block is None


def test_legitimate_unicode_symbol_passes():
    """A Chinese-character perpetual that IS trading must not be blocked."""
    market, block, reason = resolve_market(FakeClient(DEFAULT), "币安人生USDT")
    assert block is None, reason
    assert market["symbol"] == "币安人生USDT"


def test_unicode_symbol_not_yet_trading_is_blocked_on_status():
    market, block, reason = resolve_market(FakeClient(DEFAULT), "龙虾USDT")
    assert market is None
    assert block == SYMBOL_NOT_TRADING_BLOCKED
    assert "PENDING_TRADING" in reason


def test_ascii_symbol_not_yet_trading_is_blocked_identically():
    """The ASCII case must fail the same way -- encoding is irrelevant."""
    _, block, reason = resolve_market(FakeClient(DEFAULT), "ZKCUSDT")
    assert block == SYMBOL_NOT_TRADING_BLOCKED
    assert "PENDING_TRADING" in reason


def test_settling_symbol_is_blocked():
    _, block, _ = resolve_market(FakeClient(DEFAULT), "OLDUSDT")
    assert block == SYMBOL_NOT_TRADING_BLOCKED


def test_unknown_symbol_is_unsupported():
    _, block, reason = resolve_market(FakeClient(DEFAULT), "NOTAREALCOINUSDT")
    assert block == UNSUPPORTED_SYMBOL_BLOCKED
    assert "not listed" in reason


def test_wrong_quote_asset_is_blocked():
    _, block, reason = resolve_market(FakeClient(DEFAULT), "BTCUSDC")
    assert block == SYMBOL_NOT_TRADING_BLOCKED
    assert "quoteAsset" in reason


def test_non_perpetual_contract_is_blocked():
    _, block, reason = resolve_market(FakeClient(DEFAULT), "BTCUSDT_251226")
    assert block == SYMBOL_NOT_TRADING_BLOCKED
    assert "contractType" in reason


def test_no_metadata_fails_closed():
    """Unverifiable metadata must refuse, never assume the market is fine."""
    _, block, reason = resolve_market(FakeClient([], fail=True), "BTCUSDT")
    assert block == UNSUPPORTED_SYMBOL_BLOCKED
    assert "metadata unavailable" in reason


def test_metadata_is_cached_not_fetched_per_signal():
    client = FakeClient(DEFAULT)
    for _ in range(5):
        resolve_market(client, "BTCUSDT")
    assert client.calls == 1


def test_stale_cache_survives_a_refresh_failure():
    """A refresh failure with a usable cache must not halt trading."""
    client = FakeClient(DEFAULT)
    resolve_market(client, "BTCUSDT")
    symbol_registry._fetched_at = 0.0  # force staleness
    client.fail = True
    _, block, _ = resolve_market(client, "BTCUSDT")
    assert block is None


def test_empty_symbol_is_unsupported():
    _, block, _ = resolve_market(FakeClient(DEFAULT), "   ")
    assert block == UNSUPPORTED_SYMBOL_BLOCKED


# --- new-entry kill switch -------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("false", False), ("False", False), ("0", False), ("no", False), ("off", False),
    ("true", True), ("True", True), ("1", True), ("yes", True), ("on", True),
])
def test_kill_switch_parses_flag(monkeypatch, value, expected):
    monkeypatch.setenv("NEW_ENTRIES_ENABLED", value)
    assert new_entries_enabled() is expected


def test_kill_switch_defaults_to_enabled_when_unset(monkeypatch):
    """Unset preserves historical behaviour; only an explicit falsy halts."""
    monkeypatch.delenv("NEW_ENTRIES_ENABLED", raising=False)
    assert new_entries_enabled() is True
    monkeypatch.setenv("NEW_ENTRIES_ENABLED", "   ")
    assert new_entries_enabled() is True
