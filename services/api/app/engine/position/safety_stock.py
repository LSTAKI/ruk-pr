"""
Safety Stock Calculation Module
================================

Implements a configurable safety-stock policy using the classical square-root
formula as a baseline.  The module is kept modular so more sophisticated
approaches (e.g., Poisson demand, lumpy demand, stochastic lead times) can
be added later without changing the caller interface.

Formula
-------
    SS = z × σ_d × √L

Where:
    z     Service-level factor (dimensionless). A higher z provides a larger
          buffer against demand and supply uncertainty.
          z is NOT a guaranteed achieved service level.  Achieving a target
          service level requires that the underlying demand distribution
          matches the assumption (see Statistical Assumptions below).
    σ_d   Sample standard deviation of daily historical demand (units/day).
          Calculated as the corrected (Bessel-corrected, ddof=1) sample
          standard deviation over the available history window.
    L     Replenishment lead time in days (float, from the Route table).
          Fractional lead times are supported (e.g., 1.5 days).

Statistical Assumptions
-----------------------
1. Daily demand is independently and identically distributed (i.i.d.).
2. Demand follows an approximately normal distribution.
3. Lead time is treated as a deterministic constant (point estimate).
4. The observed historical window is representative of future demand.

These assumptions frequently do not hold for FMCG products:
  - Demand exhibits weekly seasonality (documented in the generator).
  - Lead times have variance not modelled here.
  - The history window may be shorter than one seasonal cycle.

Callers must document whether these assumptions are met for their product.

Fallback Policy
---------------
When σ_d cannot be reliably estimated (fewer than MIN_HISTORY_FOR_STDDEV
observations, or all demand is zero), safety stock falls back to a
configurable percentage of mean daily demand × lead time:

    SS_fallback = fallback_factor × mean_daily_demand × L

This fallback is documented and warned in the result.  A fallback_factor
of 0.0 means zero safety stock when data is insufficient.

Rounding Policy
---------------
Safety stock is returned as a float for precision.  Integer conversion
(ceil) is applied at the replenishment-requirement boundary.

Double-counting prevention
--------------------------
Safety stock is a BUFFER TARGET, not a physical quantity.
It must NEVER be added to on-hand stock or to the forecast demand.
It is used only to set the replenishment threshold:
    threshold = lead_time_demand + safety_stock
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

# Minimum observations to compute a meaningful standard deviation
MIN_HISTORY_FOR_STDDEV = 7

# Warning codes
WARN_SS_FALLBACK_USED = "safety_stock_fallback_used"
WARN_SS_ZERO_HISTORY = "safety_stock_zero_history"
WARN_SS_ZERO_LEAD_TIME = "safety_stock_zero_lead_time"
WARN_SS_INSUFFICIENT_HISTORY = "safety_stock_insufficient_history_for_stddev"
WARN_SS_ALL_ZERO_DEMAND = "safety_stock_all_zero_demand"
WARN_SS_SIMULATED_DATA = "safety_stock_computed_from_simulated_data"


@dataclass
class SafetyStockConfig:
    """Configuration for the safety-stock policy.

    Attributes
    ----------
    service_level_z:
        Service-level factor (z-score).  Common values:
          85 % → z ≈ 1.04
          90 % → z ≈ 1.28
          95 % → z ≈ 1.65  (default)
          99 % → z ≈ 2.33
        This value is a configuration parameter, NOT a guarantee.
    fallback_factor:
        Fraction of mean-demand × lead-time used when σ_d is unreliable.
        Default 0.25 (25 % buffer).  Set to 0.0 for zero fallback safety stock.
    min_safety_stock_units:
        Absolute minimum safety-stock floor (default 0).
    """
    service_level_z: float = 1.65     # 95th-percentile z-score
    fallback_factor: float = 0.25     # fallback buffer fraction
    min_safety_stock_units: float = 0.0

    def validate(self) -> None:
        """Raises ValueError for invalid configuration values."""
        if self.service_level_z < 0:
            raise ValueError(
                f"service_level_z must be >= 0. Got: {self.service_level_z}. "
                "A negative z-score produces negative safety stock."
            )
        if self.service_level_z > 4.0:
            raise ValueError(
                f"service_level_z={self.service_level_z} is unrealistically large "
                "(> 4.0 corresponds to > 99.997% service level). Check configuration."
            )
        if not (0.0 <= self.fallback_factor <= 1.0):
            raise ValueError(
                f"fallback_factor must be in [0, 1]. Got: {self.fallback_factor}."
            )
        if self.min_safety_stock_units < 0:
            raise ValueError(
                f"min_safety_stock_units must be >= 0. Got: {self.min_safety_stock_units}."
            )


@dataclass
class SafetyStockResult:
    """Result of a single safety-stock calculation.

    Attributes
    ----------
    safety_stock_units:
        Calculated safety stock in units (non-negative float, before ceiling).
    safety_stock_int:
        Safety stock rounded up to the nearest integer (ceil) for use as a
        replenishment buffer.
    method_used:
        'formula'    — SS = z × σ_d × √L was used.
        'fallback'   — fallback_factor × mean × L was used.
        'zero'       — no history or zero lead time; SS set to 0.
    mean_daily_demand:
        Sample mean of daily demand over the history window.
    stddev_daily_demand:
        Sample standard deviation (ddof=1) of daily demand.
        None if fewer than 2 observations.
    lead_time_days:
        Lead time used in the calculation (days, from the Route table).
    observations_used:
        Number of historical observations used to compute σ_d / mean.
    warnings:
        Non-fatal conditions encountered during computation.
    is_simulated_data:
        True if the underlying demand history is flagged as simulated.
    """
    safety_stock_units: float
    safety_stock_int: int
    method_used: str   # 'formula', 'fallback', 'zero'
    mean_daily_demand: float
    stddev_daily_demand: Optional[float]
    lead_time_days: float
    observations_used: int
    warnings: List[str]
    is_simulated_data: bool


def compute_safety_stock(
    daily_demands: List[float],
    lead_time_days: float,
    config: Optional[SafetyStockConfig] = None,
    is_simulated_data: bool = False,
) -> SafetyStockResult:
    """Computes safety stock for a single product-destination pair.

    Parameters
    ----------
    daily_demands:
        Ordered list of historical daily demand values (units).
        Must already be cleaned (no negatives, no future observations).
    lead_time_days:
        Route lead time in days.  Fractional values are supported:
        e.g., lead_time_days=1.5 means 36 hours transit.
    config:
        Safety-stock policy configuration.  Uses defaults if None.
    is_simulated_data:
        If True, a warning is appended to the result.

    Returns
    -------
    SafetyStockResult

    Notes
    -----
    - Negative safety stock is prevented by clamping to 0.
    - Zero lead time → safety stock = 0 (no transit buffer needed).
    - Fewer than MIN_HISTORY_FOR_STDDEV observations → fallback.
    - All-zero demand → safety stock = 0 (no variance to buffer).
    """
    if config is None:
        config = SafetyStockConfig()
    config.validate()

    warnings: List[str] = []
    n = len(daily_demands)

    if is_simulated_data:
        warnings.append(WARN_SS_SIMULATED_DATA)

    # ------------------------------------------------------------------
    # Zero history
    # ------------------------------------------------------------------
    if n == 0:
        warnings.append(WARN_SS_ZERO_HISTORY)
        return SafetyStockResult(
            safety_stock_units=max(0.0, config.min_safety_stock_units),
            safety_stock_int=max(0, math.ceil(config.min_safety_stock_units)),
            method_used="zero",
            mean_daily_demand=0.0,
            stddev_daily_demand=None,
            lead_time_days=lead_time_days,
            observations_used=0,
            warnings=warnings,
            is_simulated_data=is_simulated_data,
        )

    # ------------------------------------------------------------------
    # Zero lead time
    # ------------------------------------------------------------------
    if lead_time_days <= 0.0:
        warnings.append(WARN_SS_ZERO_LEAD_TIME)
        mean_d = sum(daily_demands) / n
        return SafetyStockResult(
            safety_stock_units=max(0.0, config.min_safety_stock_units),
            safety_stock_int=max(0, math.ceil(config.min_safety_stock_units)),
            method_used="zero",
            mean_daily_demand=round(mean_d, 4),
            stddev_daily_demand=None,
            lead_time_days=lead_time_days,
            observations_used=n,
            warnings=warnings,
            is_simulated_data=is_simulated_data,
        )

    mean_d = sum(daily_demands) / n
    all_zero = all(d == 0.0 for d in daily_demands)

    if all_zero:
        warnings.append(WARN_SS_ALL_ZERO_DEMAND)
        return SafetyStockResult(
            safety_stock_units=max(0.0, config.min_safety_stock_units),
            safety_stock_int=max(0, math.ceil(config.min_safety_stock_units)),
            method_used="zero",
            mean_daily_demand=0.0,
            stddev_daily_demand=0.0,
            lead_time_days=lead_time_days,
            observations_used=n,
            warnings=warnings,
            is_simulated_data=is_simulated_data,
        )

    # ------------------------------------------------------------------
    # Standard deviation (Bessel-corrected, ddof=1)
    # ------------------------------------------------------------------
    stddev: Optional[float] = None
    if n >= MIN_HISTORY_FOR_STDDEV:
        variance = sum((d - mean_d) ** 2 for d in daily_demands) / (n - 1)
        stddev = math.sqrt(variance)
    else:
        warnings.append(WARN_SS_INSUFFICIENT_HISTORY)

    # ------------------------------------------------------------------
    # Primary formula path
    # ------------------------------------------------------------------
    if stddev is not None:
        ss_raw = config.service_level_z * stddev * math.sqrt(lead_time_days)
        ss_units = max(0.0, ss_raw, config.min_safety_stock_units)
        method = "formula"
    else:
        # Fallback: fraction of mean × lead-time
        warnings.append(WARN_SS_FALLBACK_USED)
        ss_raw = config.fallback_factor * mean_d * lead_time_days
        ss_units = max(0.0, ss_raw, config.min_safety_stock_units)
        method = "fallback"

    return SafetyStockResult(
        safety_stock_units=round(ss_units, 4),
        safety_stock_int=math.ceil(ss_units),
        method_used=method,
        mean_daily_demand=round(mean_d, 4),
        stddev_daily_demand=round(stddev, 4) if stddev is not None else None,
        lead_time_days=lead_time_days,
        observations_used=n,
        warnings=warnings,
        is_simulated_data=is_simulated_data,
    )
