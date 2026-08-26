from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .pre_trade import (
    AccountSnapshot,
    PositionSnapshot,
    RiskConfig,
    RiskDecision,
    TradeIntent,
    evaluate_pre_trade,
)
from .risk_ledger import RiskDecisionLedger


EXPECTED_TESTNET_HOST = "https://testnet.binancefuture.com"


class BinanceStateProvider(Protocol):
    mode: str
    host: str
    is_testnet: bool

    def account_snapshot(self) -> AccountSnapshot: ...
    def positions(self) -> tuple[str, Sequence[PositionSnapshot]]: ...


class IntentRegistry(Protocol):
    def exists(self, intent_id: str) -> bool: ...


class TradeLedger(Protocol):
    def last_entry_timestamp(self, symbol: str) -> int | None: ...


class DryRunExecutor(Protocol):
    def submit_dry_run(self, intent: TradeIntent, decision: RiskDecision) -> object: ...


@dataclass(frozen=True, slots=True)
class Step4Result:
    status: str
    decision: RiskDecision
    execution_sent: bool
    dry_run_result: object | None = None


def _normalize_host(value: str) -> str:
    return value.rstrip("/").lower()


def process_trade_intent_step4(
    *,
    intent: TradeIntent,
    config: RiskConfig,
    exchange: BinanceStateProvider,
    intent_registry: IntentRegistry,
    trade_ledger: TradeLedger,
    risk_ledger: RiskDecisionLedger,
    dry_run_executor: DryRunExecutor,
    now_epoch: int,
    execution_enabled: bool = False,
) -> Step4Result:
    """
    Step 4 has NO live-submit branch.

    Even an allowed RiskDecision can only reach submit_dry_run().
    Step 5 must introduce a separately reviewed execution path.
    """
    if execution_enabled:
        raise RuntimeError("STEP4_EXECUTION_MUST_REMAIN_DISABLED")

    if (
        exchange.mode != "testnet"
        or exchange.is_testnet is not True
        or _normalize_host(exchange.host) != EXPECTED_TESTNET_HOST
    ):
        # Fail closed before trusting any account/position data.
        decision = RiskDecision(
            intent_id=intent.intent_id,
            allowed=False,
            reasons=("NON_TESTNET_EXECUTION_BLOCKED",),
            requested_notional_usdt=None,
            projected_position_notional_usdt=None,
            observed={
                "mode": exchange.mode,
                "host_class": "testnet" if "testnet" in exchange.host.lower() else "non_testnet",
                "is_testnet": exchange.is_testnet,
            },
            thresholds={
                "execution_enabled": False,
                "environment": "binance_testnet",
            },
            evaluated_at=__import__("datetime").datetime.fromtimestamp(
                now_epoch, tz=__import__("datetime").timezone.utc
            ).isoformat(),
        )
        risk_ledger.append(decision.to_dict())
        return Step4Result(
            status="RISK_REJECTED",
            decision=decision,
            execution_sent=False,
        )

    try:
        account = exchange.account_snapshot()
        positions_status, positions = exchange.positions()
    except Exception as exc:
        # Do not persist exception text; provider errors can leak request details.
        decision = RiskDecision(
            intent_id=intent.intent_id,
            allowed=False,
            reasons=("EXCHANGE_STATE_UNAVAILABLE",),
            requested_notional_usdt=None,
            projected_position_notional_usdt=None,
            observed={"exchange_lookup": "failed"},
            thresholds={
                "execution_enabled": False,
                "environment": "binance_testnet",
            },
            evaluated_at=__import__("datetime").datetime.fromtimestamp(
                now_epoch, tz=__import__("datetime").timezone.utc
            ).isoformat(),
        )
        risk_ledger.append(decision.to_dict())
        return Step4Result(
            status="RISK_REJECTED",
            decision=decision,
            execution_sent=False,
        )

    decision = evaluate_pre_trade(
        intent=intent,
        account=account,
        positions=positions,
        positions_status=positions_status,
        previous_intent_exists=intent_registry.exists(intent.intent_id),
        last_entry_timestamp_epoch=trade_ledger.last_entry_timestamp(intent.symbol),
        config=config,
        now_epoch=now_epoch,
    )
    risk_ledger.append(decision.to_dict())

    if not decision.allowed:
        return Step4Result(
            status="RISK_REJECTED",
            decision=decision,
            execution_sent=False,
        )

    dry_run_result = dry_run_executor.submit_dry_run(intent, decision)
    return Step4Result(
        status="APPROVED_DRY_RUN",
        decision=decision,
        execution_sent=False,
        dry_run_result=dry_run_result,
    )
