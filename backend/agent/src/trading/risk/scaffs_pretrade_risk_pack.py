from __future__ import annotations

"""
MoScript contract-pack adapter.

Contract id: scaffs-pretrade-risk-001
Target: Grid.Body

This wrapper contains no Binance client and no live executor. Runtime state is supplied
by the trusted Scaffs Step-4 adapter so the contract remains deterministic.
"""

from decimal import Decimal

from .pre_trade import (
    AccountSnapshot,
    MarketSnapshot,
    PositionSnapshot,
    RiskConfig,
    TradeIntent,
    evaluate_pre_trade,
)


CONTRACT_ID = "scaffs-pretrade-risk-001"


def _d(value) -> Decimal:
    return Decimal(str(value))


def run(payload: dict) -> dict:
    args = payload.get("args") or payload.get("payload") or {}

    if args.get("execution_enabled") is not False:
        return {
            "status": "denied",
            "contract_id": CONTRACT_ID,
            "result": {
                "allowed": False,
                "reasons": ["STEP4_EXECUTION_MUST_REMAIN_DISABLED"],
                "execution_sent": False,
            },
        }

    intent_raw = args["intent"]
    market_raw = intent_raw["market_snapshot"]
    account_raw = args["account"]
    positions_raw = args["positions"]
    cfg = args["config"]

    intent = TradeIntent(
        intent_id=str(intent_raw["intent_id"]),
        symbol=str(intent_raw["symbol"]),
        side=str(intent_raw["side"]),
        order_type=str(intent_raw["order_type"]),
        quantity=_d(intent_raw["quantity"]),
        reduce_only=bool(intent_raw.get("reduce_only", False)),
        requested_leverage=_d(intent_raw.get("requested_leverage", 1)),
        market_snapshot=MarketSnapshot(
            symbol=str(market_raw["symbol"]),
            mark_price=_d(market_raw["mark_price"]),
            timestamp_epoch=int(market_raw["timestamp_epoch"]),
            status=str(market_raw.get("status", "OK")),
        ),
    )

    account = AccountSnapshot(
        available_balance_usdt=_d(account_raw["available_balance_usdt"]),
        status=str(account_raw.get("status", "OK")),
    )

    positions = [
        PositionSnapshot(
            symbol=str(p["symbol"]),
            signed_notional_usdt=_d(p["signed_notional_usdt"]),
            leverage=_d(p["leverage"]),
        )
        for p in positions_raw
    ]

    config = RiskConfig(
        max_trade_notional_usdt=_d(cfg["max_trade_notional_usdt"]),
        max_position_notional_usdt=_d(cfg["max_position_notional_usdt"]),
        max_leverage=_d(cfg["max_leverage"]),
        min_available_balance_usdt=_d(cfg["min_available_balance_usdt"]),
        max_open_positions=int(cfg["max_open_positions"]),
        trade_cooldown_seconds=int(cfg["trade_cooldown_seconds"]),
        allowed_symbols=frozenset(str(s).upper() for s in cfg["allowed_symbols"]),
        max_market_data_age_seconds=int(cfg["max_market_data_age_seconds"]),
    )

    decision = evaluate_pre_trade(
        intent=intent,
        account=account,
        positions=positions,
        positions_status=str(args.get("positions_status", "OK")),
        previous_intent_exists=bool(args.get("previous_intent_exists", False)),
        last_entry_timestamp_epoch=args.get("last_entry_timestamp_epoch"),
        config=config,
        now_epoch=int(args["now_epoch"]),
    )

    return {
        "status": "aligned" if decision.allowed else "denied",
        "contract_id": CONTRACT_ID,
        "result": {
            **decision.to_dict(),
            "execution_sent": False,
        },
    }
