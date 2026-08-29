"""Tests for fail-closed Binance credential loading."""
from __future__ import annotations

import os
from typing import Generator

import pytest

from src.trading.connectors.binance.futures_sdk import (
    BinanceConfig,
    BinanceFuturesConfig,
    DEFAULT_FUTURES_TESTNET_HOST,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch) -> Generator[None, None, None]:
    """Clear all Binance-related env vars before each test."""
    for key in {
        "TRADING_ENV",
        "BINANCE_TRADING_MODE",
        "BINANCE_TESTNET_API_KEY",
        "BINANCE_TESTNET_API_SECRET",
        "BINANCE_FUTURES_TESTNET_HOST",
        "BINANCE_PROD_API_KEY",
        "BINANCE_PROD_API_SECRET",
        "BINANCE_PRODUCTION_ENABLED",
        "SCAFFS_ALLOW_BINANCE_PRODUCTION",
    }:
        monkeypatch.delenv(key, raising=False)
    yield


def test_paper_mode_requires_no_credentials(monkeypatch):
    monkeypatch.setenv("TRADING_ENV", "paper")
    cfg = BinanceConfig.from_env()
    assert cfg.mode == "paper"
    assert cfg.api_key is None
    assert cfg.api_secret is None
    assert cfg.host is None
    assert cfg.trading_env == "paper"


def test_testnet_mode_requires_testnet_credentials(monkeypatch):
    monkeypatch.setenv("TRADING_ENV", "binance_testnet")
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
    cfg = BinanceConfig.from_env()
    assert cfg.mode == "testnet"
    assert cfg.api_key == "test-key"
    assert cfg.api_secret == "test-secret"
    assert cfg.host == DEFAULT_FUTURES_TESTNET_HOST


def test_testnet_mode_fails_without_credentials(monkeypatch):
    monkeypatch.setenv("TRADING_ENV", "binance_testnet")
    with pytest.raises(RuntimeError, match="Missing Binance testnet credential"):
        BinanceConfig.from_env()


def test_testnet_mode_rejects_non_testnet_host(monkeypatch):
    monkeypatch.setenv("TRADING_ENV", "binance_testnet")
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_HOST", "https://fapi.binance.com")
    with pytest.raises(RuntimeError, match="Testnet host"):
        BinanceConfig.from_env()


def test_production_mode_requires_armed_switch(monkeypatch):
    monkeypatch.setenv("TRADING_ENV", "binance_production")
    monkeypatch.setenv("BINANCE_PROD_API_KEY", "prod-key")
    monkeypatch.setenv("BINANCE_PROD_API_SECRET", "prod-secret")
    monkeypatch.setenv("BINANCE_PRODUCTION_ENABLED", "true")
    cfg = BinanceConfig.from_env()
    assert cfg.mode == "production"
    assert cfg.api_key == "prod-key"
    assert cfg.api_secret == "prod-secret"


def test_production_mode_rejects_when_not_enabled(monkeypatch):
    monkeypatch.setenv("TRADING_ENV", "binance_production")
    monkeypatch.setenv("BINANCE_PROD_API_KEY", "prod-key")
    monkeypatch.setenv("BINANCE_PROD_API_SECRET", "prod-secret")
    with pytest.raises(RuntimeError, match="Production Binance trading is not enabled"):
        BinanceConfig.from_env()


def test_unknown_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("TRADING_ENV", "binance_staging")
    with pytest.raises(RuntimeError, match="Unsupported TRADING_ENV"):
        BinanceConfig.from_env()


def test_binance_futures_config_from_env_for_testnet(monkeypatch):
    monkeypatch.setenv("TRADING_ENV", "binance_testnet")
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
    fcfg = BinanceFuturesConfig.from_env()
    assert fcfg.api_key == "test-key"
    assert fcfg.api_secret == "test-secret"
    assert fcfg.is_testnet is True
    assert fcfg.base_url == DEFAULT_FUTURES_TESTNET_HOST


def test_binance_futures_config_from_env_for_paper(monkeypatch):
    monkeypatch.setenv("TRADING_ENV", "paper")
    fcfg = BinanceFuturesConfig.from_env()
    assert fcfg.api_key == ""
    assert fcfg.api_secret == ""
    assert fcfg.is_testnet is False
    assert fcfg.trading_env == "paper"
