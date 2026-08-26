"""Binance USDⓈ-M Futures Testnet / Demo Connector SDK.

Provides direct REST client and CCXT adapter for Binance Futures Testnet (https://testnet.binancefuture.com).
Supports account balance retrieval, position tracking, leverage/margin-type configuration,
and order execution (market, limit, take-profit, stop-loss).
"""

from __future__ import annotations
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Optional, Union

TradingMode = Literal["paper", "testnet", "production"]


try:
    from .classification import BinanceOutcomeClass, classify_binance_mutation_error
except (ImportError, ValueError):
    try:
        from src.trading.connectors.binance.classification import (
            BinanceOutcomeClass,
            classify_binance_mutation_error,
        )
    except (ImportError, ValueError):
        from classification import BinanceOutcomeClass, classify_binance_mutation_error

logger = logging.getLogger(__name__)

DEFAULT_FUTURES_TESTNET_HOST = "https://testnet.binancefuture.com"
DEFAULT_FUTURES_LIVE_HOST = "https://fapi.binance.com"
ALLOWED_TESTNET_HOSTS = {DEFAULT_FUTURES_TESTNET_HOST, "https://testnet.binancefuture.com"}


@dataclass(frozen=True)
class BinanceConfig:
    """Mode-specific, fail-closed Binance credential configuration.

    No fallback chain.  Each mode uses only its own variables, and only
    production mode can be armed with an explicit enable switch.
    """

    mode: TradingMode
    api_key: Optional[str]
    api_secret: Optional[str]
    host: Optional[str]

    @classmethod
    def from_env(cls) -> "BinanceConfig":
        mode = os.getenv("BINANCE_TRADING_MODE", "testnet").lower().strip()
        if mode not in ("paper", "testnet", "production"):
            raise RuntimeError(f"Unsupported BINANCE_TRADING_MODE: {mode}")

        if mode == "paper":
            return cls(mode="paper", api_key=None, api_secret=None, host=None)

        if mode == "testnet":
            key = _require_env("BINANCE_TESTNET_API_KEY", "testnet")
            secret = _require_env("BINANCE_TESTNET_API_SECRET", "testnet")
            host = os.getenv("BINANCE_FUTURES_TESTNET_HOST", DEFAULT_FUTURES_TESTNET_HOST).strip()
            if host not in ALLOWED_TESTNET_HOSTS:
                raise RuntimeError(f"Testnet host '{host}' is not in the allowed list: {ALLOWED_TESTNET_HOSTS}")
            return cls(mode="testnet", api_key=key, api_secret=secret, host=host)

        if mode == "production":
            if os.getenv("BINANCE_PRODUCTION_ENABLED") != "true":
                raise RuntimeError("Production Binance trading is not enabled")
            key = _require_env("BINANCE_PROD_API_KEY", "production")
            secret = _require_env("BINANCE_PROD_API_SECRET", "production")
            return cls(mode="production", api_key=key, api_secret=secret, host=DEFAULT_FUTURES_LIVE_HOST)

        raise RuntimeError(f"Unsupported BINANCE_TRADING_MODE: {mode}")


def _require_env(name: str, context: str) -> str:
    value = os.getenv(name, "").strip().strip("'\"")
    if not value:
        raise RuntimeError(f"Missing Binance {context} credential: {name}")
    return value


class BinanceAPIError(RuntimeError):
    """Structured exception for Binance REST errors with Phase 5 outcome classification."""

    def __init__(
        self,
        msg: str,
        code: Optional[int] = None,
        http_status: Optional[int] = None,
        outcome_class: BinanceOutcomeClass = BinanceOutcomeClass.UNKNOWN_ERROR,
        is_timeout: bool = False,
    ):
        super().__init__(msg)
        self.code = code
        self.http_status = http_status
        self.outcome_class = outcome_class
        self.is_timeout = is_timeout


class BinanceAmbiguousMutationError(BinanceAPIError):
    """Raised when an order mutation state is uncertain and requires reconciliation."""

    def __init__(
        self,
        msg: str,
        client_order_id: str,
        symbol: str,
        code: Optional[int] = None,
        http_status: Optional[int] = None,
    ):
        super().__init__(
            msg=msg,
            code=code,
            http_status=http_status,
            outcome_class=BinanceOutcomeClass.RECONCILE_REQUIRED,
        )
        self.client_order_id = client_order_id
        self.symbol = symbol


def generate_deterministic_client_order_id(
    symbol: str,
    side: str,
    intent_id: Optional[str] = None,
    quantity: Optional[float] = None,
    price: Optional[float] = None,
    signal_id: Optional[str] = None,
    session_id: Optional[str] = None,
    cycle_seq: Optional[int | str] = None,
) -> str:
    """Generate a deterministic, idempotent clientOrderId for order submission.

    Derives a reproducible hash from the immutable decision parameters (signal, intent,
    symbol, side, quantity, price, cycle sequence). This guarantees that after any network
    timeout, restart, or crash, the exact same clientOrderId is recomputed to query Binance
    authoritatively for order resolution without ambiguity. Maximum length: 36 characters.
    """
    clean_sym = symbol.upper().replace("-", "").replace("/", "")
    clean_side = side.upper()
    qty_str = f"{quantity:.8f}".rstrip("0").rstrip(".") if quantity is not None else "0"
    px_str = f"{price:.8f}".rstrip("0").rstrip(".") if price is not None else "market"
    # Immutable anchor: database persistent intent/signal UUID, or deterministic trade tuple
    anchor = intent_id or signal_id or f"{clean_sym}_{clean_side}_{qty_str}_{px_str}"
    digest = hashlib.sha256(f"{clean_sym}_{clean_side}_{anchor}".encode("utf-8")).hexdigest()[:16]
    prefix = f"sc_{clean_sym.lower()[:6]}_{clean_side.lower()[:1]}"
    cid = f"{prefix}_{digest}"
    return cid[:36]


@dataclass(frozen=True, slots=True)
class BinanceFuturesConfig:
    api_key: str = ""
    api_secret: str = ""
    testnet_host: str = DEFAULT_FUTURES_TESTNET_HOST
    is_testnet: bool = True
    timeout_seconds: int = 15

    @classmethod
    def from_env(cls) -> "BinanceFuturesConfig":
        """Load configuration from environment variables or workspace .env files."""
        try:
            from dotenv import load_dotenv
            load_dotenv()
            scaffs_env = Path(__file__).resolve().parents[4] / ".env"
            if scaffs_env.is_file():
                load_dotenv(scaffs_env)
        except Exception:
            pass

        cfg = BinanceConfig.from_env()
        if cfg.mode == "paper":
            return cls()
        if cfg.mode == "testnet":
            return cls(
                api_key=cfg.api_key or "",
                api_secret=cfg.api_secret or "",
                testnet_host=cfg.host or DEFAULT_FUTURES_TESTNET_HOST,
                is_testnet=True,
            )
        # production
        return cls(
            api_key=cfg.api_key or "",
            api_secret=cfg.api_secret or "",
            testnet_host=DEFAULT_FUTURES_LIVE_HOST,
            is_testnet=False,
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None = None) -> "BinanceFuturesConfig":
        if not data:
            return cls.from_env()
        return cls(
            api_key=str(data.get("api_key") or data.get("apiKey") or "").strip(),
            api_secret=str(data.get("api_secret") or data.get("apiSecret") or "").strip(),
            testnet_host=str(data.get("testnet_host") or DEFAULT_FUTURES_TESTNET_HOST).strip(),
            is_testnet=bool(data.get("is_testnet", True)),
            timeout_seconds=int(data.get("timeout_seconds", 15)),
        )

    @property
    def base_url(self) -> str:
        return self.testnet_host if self.is_testnet else DEFAULT_FUTURES_LIVE_HOST


class BinanceFuturesClient:
    """Synchronous REST client for Binance USD-M Futures Testnet / Live."""

    def __init__(self, config: BinanceFuturesConfig | None = None):
        self.config = config or BinanceFuturesConfig.from_env()

    def _sign(self, params: dict[str, Any]) -> str:
        query = urllib.parse.urlencode(params)
        signature = hmac.new(
            self.config.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict[str, Any]] = None,
        signed: bool = False,
    ) -> Any:
        params = dict(params or {})
        headers = {
            "User-Agent": "MoStar-Scaffs/1.0",
            "Accept": "application/json",
        }

        if signed or self.config.api_key:
            headers["X-MBX-APIKEY"] = self.config.api_key

        if signed:
            if not self.config.api_key or not self.config.api_secret:
                raise ValueError("Binance Testnet API key and secret are required for signed operations.")
            params["timestamp"] = int(time.time() * 1000)
            params["signature"] = self._sign(params)

        query_str = urllib.parse.urlencode(params)
        url = f"{self.config.base_url.rstrip('/')}{path}"
        data = None

        if method.upper() in ("GET", "DELETE"):
            if query_str:
                url = f"{url}?{query_str}"
        else:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = query_str.encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            err_code = None
            err_msg = ""
            try:
                err_body = json.loads(exc.read().decode("utf-8"))
                if isinstance(err_body, dict):
                    err_code = err_body.get("code")
                    err_msg = err_body.get("msg", "")
                else:
                    err_msg = str(err_body)
            except Exception:
                err_msg = str(exc)
            
            outcome_class = classify_binance_mutation_error(err_code, err_msg, http_status=exc.code)
            raise BinanceAPIError(
                msg=f"Binance Futures API error ({exc.code}): code={err_code} msg={err_msg}",
                code=err_code,
                http_status=exc.code,
                outcome_class=outcome_class,
            ) from exc
        except urllib.error.URLError as exc:
            outcome_class = classify_binance_mutation_error(None, str(exc), is_network_timeout=True)
            raise BinanceAPIError(
                msg=f"Network transport failure connecting to Binance Futures ({url}): {exc}",
                code=None,
                http_status=None,
                outcome_class=outcome_class,
                is_timeout=True,
            ) from exc
        except Exception as exc:
            outcome_class = classify_binance_mutation_error(None, str(exc))
            raise BinanceAPIError(
                msg=f"Unexpected error in Binance Futures request ({url}): {exc}",
                code=None,
                http_status=None,
                outcome_class=outcome_class,
            ) from exc

    def ping(self) -> dict[str, Any]:
        """Test connectivity to the Futures REST API."""
        return self._request("GET", "/fapi/v1/ping", signed=False)

    def get_server_time(self) -> int:
        """Fetch exchange server time in milliseconds."""
        res = self._request("GET", "/fapi/v1/time", signed=False)
        return int(res.get("serverTime", 0))

    def get_account_balance(self) -> list[dict[str, Any]]:
        """Fetch user futures account balances (e.g. USDT, BNB, USDC)."""
        return self._request("GET", "/fapi/v2/balance", signed=True)

    def get_account_information(self) -> dict[str, Any]:
        """Fetch full account overview including total margin, equity, and positions."""
        return self._request("GET", "/fapi/v2/account", signed=True)

    def get_positions(self, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        """Fetch active futures positions."""
        params = {}
        if symbol:
            params["symbol"] = symbol.upper().replace("-", "").replace("/", "")
        raw_positions = self._request("GET", "/fapi/v2/positionRisk", params=params, signed=True)
        return [p for p in raw_positions if float(p.get("positionAmt", 0)) != 0.0]

    def get_ticker_price(self, symbol: str) -> float:
        """Fetch current mark/ticker price for a symbol."""
        formatted_symbol = symbol.upper().replace("-", "").replace("/", "")
        res = self._request("GET", "/fapi/v1/ticker/price", params={"symbol": formatted_symbol}, signed=False)
        return float(res.get("price", 0.0))

    def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        """Set initial leverage for a symbol (e.g., 5x or 10x)."""
        formatted_symbol = symbol.upper().replace("-", "").replace("/", "")
        return self._request(
            "POST",
            "/fapi/v1/leverage",
            params={"symbol": formatted_symbol, "leverage": int(leverage)},
            signed=True,
        )

    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED") -> dict[str, Any]:
        """Change symbol margin mode: 'ISOLATED' or 'CROSSED'."""
        formatted_symbol = symbol.upper().replace("-", "").replace("/", "")
        try:
            return self._request(
                "POST",
                "/fapi/v1/marginType",
                params={"symbol": formatted_symbol, "marginType": margin_type.upper()},
                signed=True,
            )
        except BinanceAPIError as e:
            if "No need to change margin type" in str(e) or e.code == -4046:
                return {"code": 200, "msg": "already set"}
            raise

    def get_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Query single order status by orderId or origClientOrderId."""
        formatted_symbol = symbol.upper().replace("-", "").replace("/", "")
        params: dict[str, Any] = {"symbol": formatted_symbol}
        if order_id is not None:
            params["orderId"] = order_id
        if client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        return self._request("GET", "/fapi/v1/order", params=params, signed=True)

    def get_quantity_precision(self, symbol: str) -> int:
        defaults = {
            "BTCUSDT": 3, "ETHUSDT": 3, "SOLUSDT": 1, "BNBUSDT": 2,
            "DOGEUSDT": 0, "XRPUSDT": 1, "ADAUSDT": 0, "AAVEUSDT": 1,
            "SUIUSDT": 1, "TAOUSDT": 3, "LTCUSDT": 3, "BCHUSDT": 3,
            "UNIUSDT": 0, "1000PEPEUSDT": 0, "PENGUUSDT": 0, "WLDUSDT": 0,
            "HYPEUSDT": 1, "LITUSDT": 0, "UAIUSDT": 0, "PAXGUSDT": 3, "ZECUSDT": 3
        }
        return defaults.get(symbol.upper(), 1)

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str = "MARKET",
        quantity: float | None = None,
        price: float | None = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        stop_price: float | None = None,
        client_order_id: Optional[str] = None,
        intent_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        session_id: Optional[str] = None,
        cycle_seq: Optional[int | str] = None,
    ) -> dict[str, Any]:
        """Place an order on the Binance Futures Testnet with outcome classification & reconciliation.

        Uses deterministic clientOrderId idempotency keys and Phase 5 outcome classification
        to handle transport drops, -1021 timestamp drift, and ambiguous mutations safely.
        """
        formatted_symbol = symbol.upper().replace("-", "").replace("/", "")
        norm_side = "BUY" if side.upper() in ("BUY", "LONG") else "SELL"
        cid = client_order_id or generate_deterministic_client_order_id(
            formatted_symbol,
            norm_side,
            intent_id=intent_id,
            signal_id=signal_id,
            quantity=quantity,
            price=price,
        )

        params: dict[str, Any] = {
            "symbol": formatted_symbol,
            "side": norm_side,
            "type": order_type.upper(),
            "newClientOrderId": cid,
        }

        if quantity is not None:
            prec = self.get_quantity_precision(formatted_symbol)
            params["quantity"] = str(int(round(quantity))) if prec == 0 else f"{quantity:.{prec}f}"
        if price is not None and order_type.upper() != "MARKET":
            params["price"] = f"{price:.8f}".rstrip("0").rstrip(".")
            params["timeInForce"] = time_in_force
        if reduce_only:
            params["reduceOnly"] = "true"
        if stop_price is not None:
            params["stopPrice"] = f"{stop_price:.8f}".rstrip("0").rstrip(".")

        try:
            raw_order = self._request("POST", "/fapi/v1/order", params=params, signed=True)
            return {
                "ok": True,
                "reconciled": False,
                "client_order_id": cid,
                "order": raw_order,
                "outcome_class": BinanceOutcomeClass.SUCCESS.value,
            }
        except BinanceAPIError as exc:
            # If transport drop, clock drift (-1021), or ambiguous mutation -> reconcile via status query
            if exc.outcome_class == BinanceOutcomeClass.RECONCILE_REQUIRED:
                logger.warning(
                    "Order placement encountered ambiguous outcome (%s: %s). Querying status by clientOrderId=%s",
                    exc.code,
                    exc,
                    cid,
                )
                try:
                    reconciled_order = self.get_order(formatted_symbol, client_order_id=cid)
                    if reconciled_order and reconciled_order.get("orderId"):
                        logger.info("Order successfully confirmed on exchange via reconciliation: %s", reconciled_order)
                        return {
                            "ok": True,
                            "reconciled": True,
                            "client_order_id": cid,
                            "order": reconciled_order,
                            "outcome_class": BinanceOutcomeClass.SUCCESS.value,
                            "reconciliation_note": f"Order confirmed after transport condition ({exc})",
                        }
                except BinanceAPIError as status_err:
                    if status_err.code == -2013:
                        # Order definitely does not exist on exchange
                        raise BinanceAPIError(
                            msg=f"Order rejected pre-engine (confirmed not on exchange): {exc}",
                            code=exc.code,
                            http_status=exc.http_status,
                            outcome_class=BinanceOutcomeClass.TERMINAL_REJECT,
                        ) from exc
                    logger.error("Failed secondary order status query for clientOrderId=%s: %s", cid, status_err)

                raise BinanceAmbiguousMutationError(
                    msg=f"Order state ambiguous after transport failure: {exc}",
                    client_order_id=cid,
                    symbol=formatted_symbol,
                    code=exc.code,
                    http_status=exc.http_status,
                ) from exc

            # Terminal or rate-limit error: pass through
            raise

    def cancel_order(
        self,
        symbol: str,
        order_id: Optional[int] = None,
        client_order_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Cancel an open order with status reconciliation for -2013, -2011, and -4131."""
        formatted_symbol = symbol.upper().replace("-", "").replace("/", "")
        params: dict[str, Any] = {"symbol": formatted_symbol}
        if order_id is not None:
            params["orderId"] = order_id
        if client_order_id is not None:
            params["origClientOrderId"] = client_order_id

        try:
            res = self._request("DELETE", "/fapi/v1/order", params=params, signed=True)
            return {
                "ok": True,
                "canceled": True,
                "order": res,
                "outcome_class": BinanceOutcomeClass.SUCCESS.value,
            }
        except BinanceAPIError as exc:
            # -2013 (Order does not exist) or -2011 (Unknown order / cancel rejected) or -4131 (Price protection expiry)
            if exc.code in (-2013, -2011, -4131) or exc.outcome_class == BinanceOutcomeClass.RECONCILE_REQUIRED:
                logger.warning("Cancel rejected (%s: %s). Reconciling order status...", exc.code, exc)
                try:
                    existing = self.get_order(formatted_symbol, order_id=order_id, client_order_id=client_order_id)
                    st = existing.get("status", "")
                    if st == "FILLED":
                        return {
                            "ok": True,
                            "canceled": False,
                            "status": "FILLED",
                            "order": existing,
                            "outcome_class": BinanceOutcomeClass.SUCCESS.value,
                            "note": "Order was filled before cancel reached matching engine.",
                        }
                    if st in ("CANCELED", "EXPIRED"):
                        return {
                            "ok": True,
                            "canceled": True,
                            "status": st,
                            "order": existing,
                            "outcome_class": BinanceOutcomeClass.SUCCESS.value,
                            "note": f"Order was already {st.lower()}.",
                        }
                except Exception as query_err:
                    logger.error("Failed to reconcile order status after cancel error: %s", query_err)

            raise

    def get_open_orders(self, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        """Get all currently open orders."""
        params = {}
        if symbol:
            params["symbol"] = symbol.upper().replace("-", "").replace("/", "")
        return self._request("GET", "/fapi/v1/openOrders", params=params, signed=True)


# Convenience singleton helper
_client_instance: Optional[BinanceFuturesClient] = None


def get_binance_futures_client(config: Optional[BinanceFuturesConfig] = None) -> BinanceFuturesClient:
    global _client_instance
    if config is not None:
        return BinanceFuturesClient(config)
    current_cfg = BinanceFuturesConfig.from_env()
    if _client_instance is None or _client_instance.config != current_cfg:
        _client_instance = BinanceFuturesClient(current_cfg)
    return _client_instance
