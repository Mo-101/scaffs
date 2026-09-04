from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class ProtectionInvariantError(Exception):
    """Base exception for invalid trade protection parameters."""
    pass


class InvertedStopError(ProtectionInvariantError):
    """Raised when a stop-loss is placed on the wrong side of the fill price."""
    pass


class InvertedTakeProfitError(ProtectionInvariantError):
    """Raised when a take-profit is placed on the wrong side of the fill price."""
    pass


def to_decimal(value: str | int | float | Decimal) -> Decimal:
    """Safely converts arbitrary numerical input to a Decimal."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as err:
        raise ValueError(f"Cannot convert value '{value}' to Decimal: {err}")


def validate_protection_invariants(
    side: PositionSide | str,
    fill_price: str | int | float | Decimal,
    stop_price: str | int | float | Decimal,
    take_profit_price: Optional[str | int | float | Decimal] = None,
    min_distance_pct: Decimal = Decimal("0.0005")  # 0.05% minimum distance buffer
) -> None:
    """
    Guarantees mathematically that:
    1. Long positions CANNOT have a stop price >= fill price.
    2. Short positions CANNOT have a stop price <= fill price.
    3. Take profits sit on the opposite, profitable side.
    4. Orders cannot sit inside the minimum price tolerance window.
    """
    if isinstance(side, str):
        side = PositionSide(side.upper())

    fill = to_decimal(fill_price)
    stop = to_decimal(stop_price)
    tp = to_decimal(take_profit_price) if take_profit_price is not None else None

    if fill <= Decimal("0"):
        raise ProtectionInvariantError(f"Fill price must be strictly positive, got {fill}")
    if stop <= Decimal("0"):
        raise ProtectionInvariantError(f"Stop price must be strictly positive, got {stop}")

    if side == PositionSide.LONG:
        # Long Stop must be strictly BELOW fill price
        if stop >= fill:
            raise InvertedStopError(
                f"INVERTED LONG STOP DETECTED: Stop ({stop}) >= Fill ({fill}). "
                f"Difference: +{(stop - fill)}. Instant stop-out aborted."
            )
        
        # Check minimum buffer distance to prevent immediate trigger upon tick noise
        required_max_stop = fill * (Decimal("1") - min_distance_pct)
        if stop > required_max_stop:
            raise ProtectionInvariantError(
                f"Long stop {stop} is too close to fill {fill}. Max allowed is {required_max_stop}."
            )

        # Long TP must be strictly ABOVE fill price
        if tp is not None:
            if tp <= fill:
                raise InvertedTakeProfitError(
                    f"INVERTED LONG TAKE PROFIT: TP ({tp}) <= Fill ({fill})."
                )

    elif side == PositionSide.SHORT:
        # Short Stop must be strictly ABOVE fill price
        if stop <= fill:
            raise InvertedStopError(
                f"INVERTED SHORT STOP DETECTED: Stop ({stop}) <= Fill ({fill}). "
                f"Difference: -{(fill - stop)}. Instant stop-out aborted."
            )

        # Check minimum buffer distance
        required_min_stop = fill * (Decimal("1") + min_distance_pct)
        if stop < required_min_stop:
            raise ProtectionInvariantError(
                f"Short stop {stop} is too close to fill {fill}. Min allowed is {required_min_stop}."
            )

        # Short TP must be strictly BELOW fill price
        if tp is not None:
            if tp >= fill:
                raise InvertedTakeProfitError(
                    f"INVERTED SHORT TAKE PROFIT: TP ({tp}) >= Fill ({fill})."
                )
    else:
        raise ProtectionInvariantError(f"Invalid position side: {side}")
