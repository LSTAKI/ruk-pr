"""
Demand Forecasting — Data Preparation Module
============================================

Responsibilities:
  1. Filter observations by product + destination.
  2. Sort chronologically.
  3. Detect & report duplicate product-destination-date observations.
  4. Apply an explicit missing-date policy (see below).
  5. Reject / report invalid negative demand.
  6. Preserve zero-demand observations as meaningful signal.
  7. Detect insufficient history.
  8. Distinguish actual zero demand from absent records.
  9. Prevent future observations from leaking into training windows.

Missing-date policy
-------------------
The dataset generator produces a contiguous daily record for every
(destination, product) combination for exactly `demand_history_days` days,
so gaps are *not expected* in the seeded demo data.

However, real FMCG datasets routinely have store-closure days,
public holidays, or data-pipeline failures.  This module:

  * Detects calendar gaps between the first and last observed date.
  * Reports gap count as a data-quality warning.
  * Does NOT impute (fill) gaps with zeros by default, because a missing
    record could represent a pipeline failure rather than true zero demand.
  * When ``fill_gaps_with_zero=True`` is explicitly passed, gaps are filled
    with zero-demand synthetic rows and marked ``is_simulated=True`` so
    downstream code can distinguish them from real observations.

This behaviour is documented and tested; callers that need gap-filled
series must opt in explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Typed record
# ---------------------------------------------------------------------------

@dataclass
class DemandRecord:
    """Normalised single observation for one product-destination-date."""

    demand_date: date
    quantity_demanded: int
    quantity_sold: int
    is_simulated: bool
    is_gap_filled: bool = False   # True ↔ synthesised by gap-fill policy

    def __post_init__(self) -> None:
        if self.quantity_demanded < 0:
            raise ValueError(
                f"Negative quantity_demanded={self.quantity_demanded} on {self.demand_date}. "
                "Negative demand is not physically meaningful and must be corrected upstream."
            )
        if self.quantity_sold < 0:
            raise ValueError(
                f"Negative quantity_sold={self.quantity_sold} on {self.demand_date}."
            )


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------

WARN_NEGATIVE_DEMAND = "negative_demand_detected"
WARN_DUPLICATE_DATES = "duplicate_dates_detected"
WARN_CALENDAR_GAPS = "calendar_gaps_detected"
WARN_INSUFFICIENT_HISTORY = "insufficient_history"
WARN_ALL_ZERO_DEMAND = "all_zero_demand"
WARN_FUTURE_OBSERVATIONS_EXCLUDED = "future_observations_excluded"
WARN_SIMULATED_DATA = "simulated_data"


# ---------------------------------------------------------------------------
# Minimum history thresholds
# ---------------------------------------------------------------------------

MIN_HISTORY_NAIVE = 1       # Naïve needs at least 1 point
MIN_HISTORY_EWMA = 7        # EWMA needs at least 7 observations to be meaningful
MIN_HISTORY_SEASONAL = 14   # Seasonal-naïve needs >= 14 days (two full weeks)


# ---------------------------------------------------------------------------
# Preparation result
# ---------------------------------------------------------------------------

@dataclass
class PreparedSeries:
    """Output of ``prepare_demand_series``.

    Attributes
    ----------
    records:
        Cleaned, sorted, unique daily records.
    warnings:
        Non-fatal data-quality issues discovered during preparation.
    duplicate_count:
        Number of duplicate (same date) records dropped.
    gap_count:
        Number of calendar days with no observation, between first and last date.
    negative_count:
        Number of records rejected due to negative demand.
    future_excluded_count:
        Number of records excluded because they fall after ``as_of_date``.
    history_days:
        Length of the cleaned series in calendar days (last - first + 1).
    observation_count:
        Actual number of rows in ``records`` (may be < history_days if gaps exist).
    is_simulated:
        True if *all* retained records carry ``is_simulated=True``.
    """

    records: List[DemandRecord]
    warnings: List[str]
    duplicate_count: int
    gap_count: int
    negative_count: int
    future_excluded_count: int
    history_days: int
    observation_count: int
    is_simulated: bool

    # Convenience helpers
    def supports_method(self, method: str) -> bool:
        """Returns True if the series has enough history for the requested method."""
        n = self.observation_count
        if method == "naive":
            return n >= MIN_HISTORY_NAIVE
        if method == "ewma":
            return n >= MIN_HISTORY_EWMA
        if method == "seasonal_naive":
            return n >= MIN_HISTORY_SEASONAL
        return False

    @property
    def demands(self) -> List[int]:
        """Ordered list of quantity_demanded values."""
        return [r.quantity_demanded for r in self.records]

    @property
    def dates(self) -> List[date]:
        """Ordered list of dates."""
        return [r.demand_date for r in self.records]


# ---------------------------------------------------------------------------
# Main preparation function
# ---------------------------------------------------------------------------

def prepare_demand_series(
    raw_records: List[Dict[str, Any]],
    as_of_date: Optional[date] = None,
    fill_gaps_with_zero: bool = False,
) -> PreparedSeries:
    """Prepares and validates a raw demand history for a single product-destination pair.

    Parameters
    ----------
    raw_records:
        List of dicts, each containing at minimum:
          ``demand_date`` (date | datetime | str),
          ``quantity_demanded`` (int),
          ``quantity_sold`` (int),
          ``is_simulated`` (bool).
    as_of_date:
        Forecast origin date.  Observations strictly *after* this date are
        excluded to prevent future data leakage.  Defaults to today (UTC).
    fill_gaps_with_zero:
        If True, missing calendar dates are filled with zero-demand synthetic
        rows marked ``is_gap_filled=True``.  Default is False (report only).

    Returns
    -------
    PreparedSeries
    """
    if as_of_date is None:
        as_of_date = datetime.utcnow().date()

    warnings: List[str] = []
    negative_count = 0
    future_excluded_count = 0

    # ------------------------------------------------------------------
    # Step 1 — Normalise dates, reject negatives, exclude future
    # ------------------------------------------------------------------
    normalised: List[Dict[str, Any]] = []
    for row in raw_records:
        raw_date = row.get("demand_date")
        if isinstance(raw_date, datetime):
            obs_date = raw_date.date()
        elif isinstance(raw_date, str):
            obs_date = datetime.fromisoformat(raw_date).date()
        elif isinstance(raw_date, date):
            obs_date = raw_date
        else:
            # Unrecognisable date — skip
            continue

        # Exclude future observations
        if obs_date > as_of_date:
            future_excluded_count += 1
            continue

        qty_d = int(row.get("quantity_demanded", 0))
        qty_s = int(row.get("quantity_sold", 0))

        if qty_d < 0 or qty_s < 0:
            negative_count += 1
            continue   # Reject invalid rows; do not impute

        normalised.append({
            "demand_date": obs_date,
            "quantity_demanded": qty_d,
            "quantity_sold": qty_s,
            "is_simulated": bool(row.get("is_simulated", False)),
        })

    if negative_count > 0:
        warnings.append(WARN_NEGATIVE_DEMAND)

    if future_excluded_count > 0:
        warnings.append(WARN_FUTURE_OBSERVATIONS_EXCLUDED)

    # ------------------------------------------------------------------
    # Step 2 — Sort chronologically
    # ------------------------------------------------------------------
    normalised.sort(key=lambda r: r["demand_date"])

    # ------------------------------------------------------------------
    # Step 3 — Detect and drop duplicates (keep first occurrence per date)
    # ------------------------------------------------------------------
    seen_dates: Dict[date, int] = {}   # date → list index of first occurrence
    deduped: List[Dict[str, Any]] = []
    dup_count = 0
    for row in normalised:
        d = row["demand_date"]
        if d in seen_dates:
            dup_count += 1
        else:
            seen_dates[d] = len(deduped)
            deduped.append(row)

    if dup_count > 0:
        warnings.append(WARN_DUPLICATE_DATES)

    # ------------------------------------------------------------------
    # Step 4 — Gap detection and optional fill
    # ------------------------------------------------------------------
    gap_count = 0
    if len(deduped) >= 2:
        first_date = deduped[0]["demand_date"]
        last_date = deduped[-1]["demand_date"]
        expected_days = (last_date - first_date).days + 1
        gap_count = expected_days - len(deduped)

        if gap_count > 0:
            warnings.append(WARN_CALENDAR_GAPS)

            if fill_gaps_with_zero:
                date_map = {r["demand_date"]: r for r in deduped}
                filled: List[Dict[str, Any]] = []
                cur = first_date
                while cur <= last_date:
                    if cur in date_map:
                        filled.append(date_map[cur])
                    else:
                        filled.append({
                            "demand_date": cur,
                            "quantity_demanded": 0,
                            "quantity_sold": 0,
                            "is_simulated": True,
                            "_gap_filled": True,
                        })
                    cur += timedelta(days=1)
                deduped = filled

    # ------------------------------------------------------------------
    # Step 5 — Build typed records
    # ------------------------------------------------------------------
    records: List[DemandRecord] = []
    for row in deduped:
        records.append(DemandRecord(
            demand_date=row["demand_date"],
            quantity_demanded=row["quantity_demanded"],
            quantity_sold=row["quantity_sold"],
            is_simulated=row.get("is_simulated", False),
            is_gap_filled=row.get("_gap_filled", False),
        ))

    # ------------------------------------------------------------------
    # Step 6 — Derived statistics
    # ------------------------------------------------------------------
    obs = len(records)
    if obs == 0:
        history_days = 0
    elif obs == 1:
        history_days = 1
    else:
        history_days = (records[-1].demand_date - records[0].demand_date).days + 1

    if obs < MIN_HISTORY_NAIVE:
        warnings.append(WARN_INSUFFICIENT_HISTORY)

    all_zero = obs > 0 and all(r.quantity_demanded == 0 for r in records)
    if all_zero:
        warnings.append(WARN_ALL_ZERO_DEMAND)

    all_simulated = obs > 0 and all(r.is_simulated for r in records)
    if all_simulated:
        warnings.append(WARN_SIMULATED_DATA)

    return PreparedSeries(
        records=records,
        warnings=warnings,
        duplicate_count=dup_count,
        gap_count=gap_count,
        negative_count=negative_count,
        future_excluded_count=future_excluded_count,
        history_days=history_days,
        observation_count=obs,
        is_simulated=all_simulated,
    )


# ---------------------------------------------------------------------------
# Chronological train/test split
# ---------------------------------------------------------------------------

def chronological_split(
    series: PreparedSeries,
    test_fraction: float = 0.2,
    min_test_days: int = 7,
) -> Tuple[PreparedSeries, PreparedSeries]:
    """Splits a PreparedSeries into train (earlier) and test (later) partitions.

    Splitting is strictly chronological so the model never sees future data
    during backtesting.

    Parameters
    ----------
    series:
        The prepared series to split.
    test_fraction:
        Fraction of observations to allocate to the test partition.
    min_test_days:
        Minimum number of test observations; overrides test_fraction if needed.

    Returns
    -------
    (train_series, test_series)
    """
    n = series.observation_count
    n_test = max(min_test_days, int(round(n * test_fraction)))
    n_test = min(n_test, n - MIN_HISTORY_EWMA)  # always keep enough for training
    if n_test < 1:
        n_test = 1

    n_train = n - n_test
    if n_train < 1:
        n_train = 1
        n_test = max(1, n - 1)

    train_records = series.records[:n_train]
    test_records = series.records[n_train:]

    def _subseries(recs: List[DemandRecord]) -> PreparedSeries:
        m = len(recs)
        hdays = 0 if m == 0 else (
            1 if m == 1 else (recs[-1].demand_date - recs[0].demand_date).days + 1
        )
        return PreparedSeries(
            records=recs,
            warnings=list(series.warnings),
            duplicate_count=0,
            gap_count=0,
            negative_count=0,
            future_excluded_count=0,
            history_days=hdays,
            observation_count=m,
            is_simulated=series.is_simulated,
        )

    return _subseries(train_records), _subseries(test_records)
