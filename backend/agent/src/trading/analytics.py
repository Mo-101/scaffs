"""Rolling ratio analytics for 15-minute 24/7 trading evaluation intervals.

Annualization factor for 15-minute 24/7 intervals:
  A = 365 * 24 * 4 = 35,040 observations / year.
"""

from __future__ import annotations

from math import sqrt
from statistics import mean, stdev
from typing import Any, Dict, List

PERIODS_PER_YEAR_15M = 365 * 24 * 4  # 35,040


def rolling_ratios(
    equity: List[float],
    *,
    min_samples: int = 30,
    risk_free_per_period: float = 0.0,
    mar_per_period: float = 0.0,
) -> Dict[str, Any]:
    """Calculates annualized rolling Sharpe & Sortino ratios for 15m intervals."""
    if len(equity) < min_samples + 1:
        return {
            "sharpe": None,
            "sortino": None,
            "status": "INSUFFICIENT_HISTORY",
            "samples": max(0, len(equity) - 1),
            "min_samples": min_samples,
        }

    returns = [equity[i] / equity[i - 1] - 1.0 for i in range(1, len(equity))]
    excess = [r - risk_free_per_period for r in returns]
    sigma = stdev(excess) if len(excess) > 1 else 0.0
    sharpe = (sqrt(PERIODS_PER_YEAR_15M) * mean(excess) / sigma) if sigma > 0 else None

    downside = [min(r - mar_per_period, 0.0) for r in returns]
    sum_sq_downside = sum(x * x for x in downside)
    downside_dev = sqrt(sum_sq_downside / len(downside)) if len(downside) > 0 else 0.0
    sortino = (
        (sqrt(PERIODS_PER_YEAR_15M) * (mean(returns) - mar_per_period) / downside_dev)
        if downside_dev > 0
        else None
    )

    return {
        "sharpe": round(sharpe, 4) if sharpe is not None else None,
        "sortino": round(sortino, 4) if sortino is not None else None,
        "status": "OK",
        "samples": len(returns),
        "min_samples": min_samples,
    }
