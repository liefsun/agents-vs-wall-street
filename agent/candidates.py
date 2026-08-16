"""Candidate forecasters — the roster that competes in the rolling-origin backtest.

Ported from the lab pipeline's model set (seasonal naive is the mandatory baseline
every other model must beat). Each pure-series model maps a chronological list y
-> next-point, or None if it lacks the data to fire. `guidance` is handled
separately in backtest.py because it is exogenous (issued by the company), not a
function of the series.
"""
from __future__ import annotations

import numpy as np

SEASON = 4
ETS_ALPHA, ETS_BETA, ETS_GAMMA = 0.4, 0.1, 0.2
DRIFT_LOOKBACK_SEASONS = 2


def seasonal_naive(y, season=SEASON):  # mandatory baseline: same reporting period last year
    return y[-season] if len(y) >= season else None


def naive_last(y, season=SEASON):
    return y[-1] if len(y) >= 1 else None


def drift_mult(y, season=SEASON):       # seasonal x median YoY growth (needs positive base)
    if len(y) < 2 * season or y[-season] <= 0:
        return None
    g = [
        y[i] / y[i - season]
        for i in range(season, len(y))
        if y[i - season] > 0
    ]
    return y[-season] * float(np.median(g)) if len(g) >= season else None


def drift_add(y, season=SEASON):        # seasonal + median YoY change (handles negatives)
    if len(y) < 2 * season:
        return None
    changes = [y[i] - y[i - season] for i in range(season, len(y))]
    lookback = DRIFT_LOOKBACK_SEASONS * season
    return y[-season] + float(np.median(changes[-lookback:])) if changes else None


def trend_mult(y, season=SEASON):       # seasonal + linear trend in YoY growth
    if len(y) < 3 * season or y[-season] <= 0:
        return None
    g = [
        (i, y[i] / y[i - season] - 1)
        for i in range(season, len(y))
        if y[i - season] > 0
    ]
    if len(g) < max(3, season + 2):
        return None
    x = np.array([i for i, _ in g], float)
    gg = np.array([v for _, v in g], float)
    b1, b0 = np.polyfit(x, gg, 1)
    return y[-season] * (1 + float(b0 + b1 * len(y)))


def ar_lag(y, season=SEASON):           # lagged OLS / AR with reporting-frequency lag
    if len(y) < 3 * season:
        return None
    X, t = [], []
    for i in range(season, len(y)):
        X.append([1.0, y[i - 1], y[i - season]])
        t.append(y[i])
    try:
        coef, *_ = np.linalg.lstsq(np.array(X), np.array(t), rcond=None)
    except np.linalg.LinAlgError:
        return None
    return float(coef[0] + coef[1] * y[-1] + coef[2] * y[-season])


def ets_hw(y, season=SEASON):           # additive Holt-Winters, fixed smoothing
    m = season
    if len(y) < 2 * m:
        return None
    a, b, g = ETS_ALPHA, ETS_BETA, ETS_GAMMA
    level = sum(y[:m]) / m
    trend = (sum(y[m:2 * m]) - sum(y[:m])) / (m * m)
    season = [y[i] - level for i in range(m)]
    for i in range(m, len(y)):
        s = season[i % m]
        prev = level
        level = a * (y[i] - s) + (1 - a) * (level + trend)
        trend = b * (level - prev) + (1 - b) * trend
        season[i % m] = g * (y[i] - level) + (1 - g) * s
    return float(level + trend + season[len(y) % m])


# (key -> (label, fn)) — pure-series candidates only; guidance is added in the backtest
SERIES_MODELS = {
    "seasonal_naive": ("Seasonal naive · same period last year", seasonal_naive),
    "naive_last": ("Naive · last reported period", naive_last),
    "drift_mult": ("Seasonal drift · median YoY growth", drift_mult),
    "drift_add": ("Seasonal drift · median YoY change", drift_add),
    "trend_mult": ("Seasonal + growth trend", trend_mult),
    "ar_lag": ("Lagged OLS / AR", ar_lag),
    "ets_hw": ("ETS / Holt-Winters", ets_hw),
}
BASELINE = "seasonal_naive"
