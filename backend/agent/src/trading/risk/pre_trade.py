from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence


ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    symbol: str
    mark_price: Decimal
    timestamp_epoch: int
    status: str = "OK"


@dataclass(frozen=True, slots=True)
class TradeIntent:
    intent_id: str
    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    reduce_only: bool
    requested_leverage: Decimal
    market_snapshot: MarketSnapshot
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    range_metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    available_balance_usdt: Decimal
    status: str = "OK"
    # Optional: total wallet balance (equity), distinct from available/free
    # margin. available_balance_usdt is a capital-sufficiency constraint (it
    # shrinks as other isolated positions reserve margin); total_wallet_balance
    # is the "risk-base" equity a risk_pct sizing formula should scale against,
    # so opening one isolated position doesn't itself change what risk_pct
    # nominally means for the next one. None when the caller hasn't fetched it.
    total_wallet_balance_usdt: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    symbol: str
    # Signed notional: positive=long, negative=short, zero=flat.
    signed_notional_usdt: Decimal
    leverage: Decimal


@dataclass(frozen=True, slots=True)
class RiskConfig:
    max_trade_notional_usdt: Decimal
    max_position_notional_usdt: Decimal
    max_leverage: Decimal
    min_available_balance_usdt: Decimal
    max_open_positions: int
    trade_cooldown_seconds: int
    allowed_symbols: frozenset[str]
    max_market_data_age_seconds: int


@dataclass(frozen=True, slots=True)
class RiskDecision:
    intent_id: str
    allowed: bool
    reasons: tuple[str, ...]
    requested_notional_usdt: Decimal | None
    projected_position_notional_usdt: Decimal | None
    observed: Mapping[str, Any]
    thresholds: Mapping[str, Any]
    evaluated_at: str

    def to_dict(self) -> dict[str, Any]:
        def encode(value: Any) -> Any:
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, frozenset):
                return sorted(value)
            if isinstance(value, tuple):
                return [encode(v) for v in value]
            if isinstance(value, dict):
                return {k: encode(v) for k, v in value.items()}
            return value

        return encode(asdict(self))


class RiskInputError(ValueError):
    pass


def _position_for(
    positions: Sequence[PositionSnapshot],
    symbol: str,
) -> PositionSnapshot:
    matches = [p for p in positions if p.symbol == symbol]
    if len(matches) > 1:
        raise RiskInputError(f"duplicate exchange positions for symbol={symbol}")
    if matches:
        return matches[0]
    return PositionSnapshot(symbol=symbol, signed_notional_usdt=ZERO, leverage=Decimal("1"))


def _thresholds(config: RiskConfig) -> dict[str, Any]:
    return {
        "max_trade_notional_usdt": config.max_trade_notional_usdt,
        "max_position_notional_usdt": config.max_position_notional_usdt,
        "max_leverage": config.max_leverage,
        "min_available_balance_usdt": config.min_available_balance_usdt,
        "max_open_positions": config.max_open_positions,
        "trade_cooldown_seconds": config.trade_cooldown_seconds,
        "allowed_symbols": config.allowed_symbols,
        "max_market_data_age_seconds": config.max_market_data_age_seconds,
        "resize_policy": "reject",
        "execution_enabled": False,
        "environment": "binance_testnet",
    }


def evaluate_pre_trade(
    *,
    intent: TradeIntent,
    account: AccountSnapshot,
    positions: Sequence[PositionSnapshot],
    positions_status: str,
    previous_intent_exists: bool,
    last_entry_timestamp_epoch: int | None,
    config: RiskConfig,
    now_epoch: int,
) -> RiskDecision:
    """
    Pure deterministic Step-4 risk evaluation.

    Safety rules:
    - fail closed;
    - reject oversized requests (never resize);
    - reduce-only may reduce risk but cannot flip exposure;
    - reduce-only exits bypass entry cooldown/incremental-margin checks;
    - no live execution decision is produced by this function.
    """
    reasons: list[str] = []
    requested_notional: Decimal | None = None
    projected_abs_notional: Decimal | None = None

    symbol = intent.symbol.strip().upper() if isinstance(intent.symbol, str) else ""
    side = intent.side.strip().upper() if isinstance(intent.side, str) else ""
    order_type = intent.order_type.strip().upper() if isinstance(intent.order_type, str) else ""

    # Exchange/market health must fail closed before trusting state.
    if account.status != "OK" or positions_status != "OK" or intent.market_snapshot.status != "OK":
        reasons.append("EXCHANGE_STATE_UNAVAILABLE")

    if not intent.intent_id or not symbol:
        reasons.append("INVALID_TRADE_INTENT")
    if side not in {"BUY", "SELL"}:
        reasons.append("INVALID_SIDE")
    if order_type not in {"MARKET", "LIMIT"}:
        reasons.append("INVALID_ORDER_TYPE")
    if intent.quantity <= ZERO:
        reasons.append("INVALID_QUANTITY")
    if intent.requested_leverage <= ZERO:
        reasons.append("INVALID_LEVERAGE")

    if previous_intent_exists:
        reasons.append("DUPLICATE_INTENT")

    if "*" not in config.allowed_symbols and symbol not in config.allowed_symbols:
        reasons.append("SYMBOL_NOT_ALLOWED")

    if intent.market_snapshot.symbol.strip().upper() != symbol:
        reasons.append("MARKET_SYMBOL_MISMATCH")

    mark_price = intent.market_snapshot.mark_price
    age_seconds = now_epoch - intent.market_snapshot.timestamp_epoch
    if mark_price <= ZERO or age_seconds < 0 or age_seconds > config.max_market_data_age_seconds:
        reasons.append("STALE_OR_INVALID_MARKET_DATA")

    try:
        current = _position_for(positions, symbol)
    except RiskInputError:
        reasons.append("EXCHANGE_STATE_UNAVAILABLE")
        current = PositionSnapshot(symbol=symbol, signed_notional_usdt=ZERO, leverage=Decimal("1"))

    effective_leverage = max(current.leverage, intent.requested_leverage)
    if effective_leverage <= ZERO or effective_leverage > config.max_leverage:
        reasons.append("MAX_LEVERAGE_EXCEEDED")

    if mark_price > ZERO and intent.quantity > ZERO:
        requested_notional = intent.quantity * mark_price
        if requested_notional > config.max_trade_notional_usdt:
            reasons.append("MAX_TRADE_NOTIONAL_EXCEEDED")

        if side in {"BUY", "SELL"}:
            signed_delta = requested_notional if side == "BUY" else -requested_notional
            projected_signed = current.signed_notional_usdt + signed_delta
            projected_abs_notional = abs(projected_signed)

            if projected_abs_notional > config.max_position_notional_usdt:
                reasons.append("MAX_POSITION_NOTIONAL_EXCEEDED")

            if intent.reduce_only:
                if current.signed_notional_usdt == ZERO:
                    reasons.append("REDUCE_ONLY_NO_POSITION")
                else:
                    # Must trade opposite the current exposure.
                    correct_side = (
                        current.signed_notional_usdt > ZERO and side == "SELL"
                    ) or (
                        current.signed_notional_usdt < ZERO and side == "BUY"
                    )
                    if not correct_side:
                        reasons.append("REDUCE_ONLY_WRONG_SIDE")

                    # A reduction may flatten, but must never cross zero and flip.
                    if abs(signed_delta) > abs(current.signed_notional_usdt):
                        reasons.append("REDUCE_ONLY_WOULD_FLIP_EXPOSURE")

                    if projected_abs_notional > abs(current.signed_notional_usdt):
                        reasons.append("REDUCE_ONLY_WOULD_INCREASE_EXPOSURE")

    open_count = sum(1 for p in positions if p.signed_notional_usdt != ZERO)
    current_exists = current.signed_notional_usdt != ZERO
    if not intent.reduce_only and not current_exists and open_count >= config.max_open_positions:
        reasons.append("MAX_OPEN_POSITIONS_EXCEEDED")

    # Preserve ability to reduce risk when balance is distressed.
    if not intent.reduce_only:
        if account.available_balance_usdt < config.min_available_balance_usdt:
            reasons.append("INSUFFICIENT_AVAILABLE_BALANCE")
        if requested_notional is not None and effective_leverage > ZERO:
            required_margin = requested_notional / effective_leverage
            if account.available_balance_usdt < required_margin:
                reasons.append("INSUFFICIENT_AVAILABLE_BALANCE")

        if last_entry_timestamp_epoch is not None:
            elapsed = now_epoch - last_entry_timestamp_epoch
            if elapsed < 0 or elapsed < config.trade_cooldown_seconds:
                reasons.append("TRADE_COOLDOWN_ACTIVE")

    # Stable de-duplication keeps the decision deterministic.
    reasons = list(dict.fromkeys(reasons))

    observed = {
        "symbol": symbol,
        "side": side,
        "order_type": order_type,
        "mark_price": mark_price,
        "market_age_seconds": age_seconds,
        "available_balance_usdt": account.available_balance_usdt,
        "current_signed_position_notional_usdt": current.signed_notional_usdt,
        "current_position_leverage": current.leverage,
        "requested_leverage": intent.requested_leverage,
        "open_positions": open_count,
        "previous_intent_exists": previous_intent_exists,
        "last_entry_timestamp_epoch": last_entry_timestamp_epoch,
    }

    return RiskDecision(
        intent_id=intent.intent_id,
        allowed=not reasons,
        reasons=tuple(reasons),
        requested_notional_usdt=requested_notional,
        projected_position_notional_usdt=projected_abs_notional,
        observed=observed,
        thresholds=_thresholds(config),
        evaluated_at=datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat(),
    )
