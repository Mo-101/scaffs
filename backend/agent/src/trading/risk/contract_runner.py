"""MoScript contract pack runner registration for Scaffs risk contracts."""

from __future__ import annotations

from typing import Any, Callable, Dict

from . import scaffs_pretrade_risk_pack

CONTRACTS: Dict[str, Callable[[dict], dict]] = {
    scaffs_pretrade_risk_pack.CONTRACT_ID: scaffs_pretrade_risk_pack.run,
    "scaffs-step4-binding-001": scaffs_pretrade_risk_pack.run,
}


def run_contract(contract_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a contract id to the registered pack handler."""
    handler = CONTRACTS.get(contract_id)
    if handler is None:
        raise ValueError(f"Unknown contract id: {contract_id!r}")
    return handler(payload)
