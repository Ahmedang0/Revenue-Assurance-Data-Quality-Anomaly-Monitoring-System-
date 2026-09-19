"""Statistical anomaly detection methods. Every function here is pure —
takes a Series/DataFrame, returns a result — with no file I/O, plotting, or
database access, so each is directly unit-testable against small synthetic data.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from revenue_assurance.config import (
    IQR_MULTIPLIER,
    ISOLATION_FOREST_CONTAMINATION,
    ISOLATION_FOREST_SEED,
    ZSCORE_THRESHOLD,
    ZSCORE_WINDOW,
)


@dataclass
class ZScoreResult:
    series: pd.Series
    rolling_mean: pd.Series
    rolling_std: pd.Series
    zscore: pd.Series
    anomalous_index: pd.Index


def rolling_zscore(
    series: pd.Series, window: int = ZSCORE_WINDOW, threshold: float = ZSCORE_THRESHOLD
) -> ZScoreResult:
    """Flag points where the value deviates > `threshold` standard deviations
    from a rolling baseline computed on *prior* points only.

    Critical detail: the rolling mean/std for index i uses only points
    strictly before i (`.shift(1)` before `.rolling()`). Including the
    current point in its own baseline dilutes exactly the anomaly you're
    trying to detect — this is a common and easy-to-miss bug in naive
    rolling z-score implementations.
    """
    shifted = series.shift(1)
    rolling_mean = shifted.rolling(window, min_periods=3).mean()
    rolling_std = shifted.rolling(window, min_periods=3).std()
    zscore = (series - rolling_mean) / rolling_std

    anomalous_index = zscore[zscore.abs() > threshold].index

    return ZScoreResult(
        series=series, rolling_mean=rolling_mean, rolling_std=rolling_std,
        zscore=zscore, anomalous_index=anomalous_index,
    )


@dataclass
class IQRResult:
    lower_fence: float
    upper_fence: float
    outlier_mask: pd.Series


def iqr_outliers(series: pd.Series, multiplier: float = IQR_MULTIPLIER) -> IQRResult:
    """Tukey's-fences outlier detection: flag values outside
    [Q1 - multiplier*IQR, Q3 + multiplier*IQR].
    """
    q1, q3 = series.quantile([0.25, 0.75])
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    mask = (series < lower) | (series > upper)
    return IQRResult(lower_fence=lower, upper_fence=upper, outlier_mask=mask)


@dataclass
class IsolationForestResult:
    is_anomaly: pd.Series      # boolean, indexed like the input
    decision_score: pd.Series  # lower = more anomalous


def isolation_forest_anomalies(
    features: pd.DataFrame,
    contamination: float = ISOLATION_FOREST_CONTAMINATION,
    random_state: int = ISOLATION_FOREST_SEED,
) -> IsolationForestResult:
    """Multivariate anomaly detection on a numeric feature matrix.

    Args:
        features: Numeric feature columns only (already selected/engineered
            by the caller — this function doesn't know what the columns mean).
        contamination: Expected fraction of anomalies.
        random_state: Seed, for reproducibility.
    """
    X = features.fillna(0)
    model = IsolationForest(contamination=contamination, random_state=random_state, n_estimators=200)
    raw_labels = model.fit_predict(X)  # -1 = anomaly, 1 = normal
    decision = model.decision_function(X)

    return IsolationForestResult(
        is_anomaly=pd.Series(raw_labels == -1, index=features.index),
        decision_score=pd.Series(decision, index=features.index),
    )
