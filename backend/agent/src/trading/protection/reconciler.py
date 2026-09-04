import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

try:
    from guardrails import (
        InvertedStopError,
        InvertedTakeProfitError,
        PositionSide,
        ProtectionInvariantError,
        to_decimal,
        validate_protection_invariants,
    )
except ImportError:
    from src.trading.protection.guardrails import (
        InvertedStopError,
        InvertedTakeProfitError,
        PositionSide,
        ProtectionInvariantError,
        to_decimal,
        validate_protection_invariants,
    )

logger = logging.getLogger("ProtectionReconciler")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s][%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


@dataclass(frozen=True)
class ProtectionPlan:
    symbol: str
    side: PositionSide
    position_size: Decimal
    fill_price: Decimal
    stop_loss_price: Decimal
    take_profit_price: Optional[Decimal]


@dataclass
class ReconcileResult:
    success: bool
    placed_stop_loss_id: Optional[str] = None
    placed_take_profit_id: Optional[str] = None
    cancelled_order_ids: List[str] = None
    error_reason: Optional[str] = None


class AtomicProtectionReconciler:
    def __init__(self, exchange_client: Any):
        """
        `exchange_client` must implement:
          - create_stop_order(symbol, side, quantity, stop_price, reduce_only) -> dict
          - create_tp_order(symbol, side, quantity, stop_price, reduce_only) -> dict
          - cancel_order(symbol, order_id) -> bool
        """
        self.exchange = exchange_client

    def reconcile(
        self,
        plan: ProtectionPlan,
        stale_order_ids: List[str]
    ) -> ReconcileResult:
        """
        Executes atomic whole-pair replacement:
        1. Pre-flight invariant check.
        2. Places new Stop Loss.
        3. Places new Take Profit (if configured).
        4. Cancels stale order IDs only after all new protection is verified.
        5. Performs automatic rollback of new orders if placement fails midway.
        """
        # Step 1: Pre-flight directionality guard
        try:
            validate_protection_invariants(
                side=plan.side,
                fill_price=plan.fill_price,
                stop_price=plan.stop_loss_price,
                take_profit_price=plan.take_profit_price,
            )
        except (InvertedStopError, InvertedTakeProfitError, ProtectionInvariantError) as err:
            err_msg = f"REJECTED: Pre-flight protection violation for {plan.symbol}: {err}"
            logger.critical(err_msg)
            return ReconcileResult(success=False, error_reason=err_msg)

        exit_side = "SELL" if plan.side == PositionSide.LONG else "BUY"
        placed_new_ids: List[str] = []
        sl_order_id: Optional[str] = None
        tp_order_id: Optional[str] = None

        try:
            # Step 2: Place New Stop Loss Leg First
            logger.info(
                f"Submitting verified Stop Loss for {plan.symbol} | "
                f"Side: {exit_side} | Qty: {plan.position_size} | StopPrice: {plan.stop_loss_price}"
            )
            sl_resp = self.exchange.create_stop_order(
                symbol=plan.symbol,
                side=exit_side,
                quantity=str(plan.position_size),
                stop_price=str(plan.stop_loss_price),
                reduce_only=True,
            )
            sl_order_id = str(sl_resp["orderId"])
            placed_new_ids.append(sl_order_id)

            # Step 3: Place New Take Profit Leg (if configured)
            if plan.take_profit_price is not None:
                logger.info(
                    f"Submitting verified Take Profit for {plan.symbol} | "
                    f"Side: {exit_side} | Qty: {plan.position_size} | TPPrice: {plan.take_profit_price}"
                )
                tp_resp = self.exchange.create_tp_order(
                    symbol=plan.symbol,
                    side=exit_side,
                    quantity=str(plan.position_size),
                    stop_price=str(plan.take_profit_price),
                    reduce_only=True,
                )
                tp_order_id = str(tp_resp["orderId"])
                placed_new_ids.append(tp_order_id)

            # Step 4: Both new legs verified live -> Safely cancel stale orders
            logger.info(
                f"New whole-pair protection active for {plan.symbol}: SL={sl_order_id}, TP={tp_order_id}. "
                f"Cancelling stale order IDs: {stale_order_ids}"
            )
            cancelled_ids: List[str] = []
            for stale_id in stale_order_ids:
                try:
                    self.exchange.cancel_order(symbol=plan.symbol, order_id=stale_id)
                    cancelled_ids.append(stale_id)
                except Exception as cancel_exc:
                    # Non-fatal to position safety since new orders are already active
                    logger.warning(
                        f"Non-critical: Failed to cancel stale order {stale_id} for {plan.symbol}: {cancel_exc}"
                    )

            return ReconcileResult(
                success=True,
                placed_stop_loss_id=sl_order_id,
                placed_take_profit_id=tp_order_id,
                cancelled_order_ids=cancelled_ids,
            )

        except Exception as exc:
            # Step 5: Circuit Breaker / Rollback mechanism on placement failure
            err_msg = f"Order placement failed for {plan.symbol}: {exc}. Triggering emergency rollback."
            logger.critical(err_msg)

            for order_to_rollback in placed_new_ids:
                try:
                    logger.warning(f"Rolling back orphan protection order: {order_to_rollback}")
                    self.exchange.cancel_order(symbol=plan.symbol, order_id=order_to_rollback)
                except Exception as rollback_exc:
                    logger.critical(
                        f"CRITICAL: Failed to rollback orphan order {order_to_rollback}: {rollback_exc}"
                    )

            return ReconcileResult(
                success=False,
                placed_stop_loss_id=None,
                placed_take_profit_id=None,
                cancelled_order_ids=[],
                error_reason=str(exc),
            )
