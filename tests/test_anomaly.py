"""Unit tests for revenue_assurance.anomaly — all pure, no DB/plotting needed."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from revenue_assurance.anomaly import iqr_outliers, isolation_forest_anomalies, rolling_zscore


class TestRollingZScore:
    def test_excludes_current_point_from_its_own_baseline(self):
        """Regression test for a real bug found during development: including
        month M in its own rolling baseline dilutes the exact anomaly you're
        trying to detect. The baseline for index i must be computed only from
        points strictly before i.
        """
        series = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 1000.0], name="revenue")
        result = rolling_zscore(series, window=6, threshold=2.5)

        # The rolling mean at the last (shock) index should equal the mean of
        # the 6 PRECEDING points (10..60), not include 1000 itself.
        last_idx = series.index[-1]
        expected_prior_mean = series.iloc[:6].mean()  # 10,20,30,40,50,60
        assert result.rolling_mean[last_idx] == pytest.approx(expected_prior_mean)

    def test_detects_shock_on_top_of_a_trend(self):
        """A steadily growing series with one shock month should flag exactly
        that month — this mirrors the real dataset's demand-shock scenario.
        """
        trend = np.linspace(1000, 6000, 18)
        series = pd.Series(trend, index=[f"2023-{i+1:02d}" if i < 12 else f"2024-{i-11:02d}" for i in range(18)])
        shock_idx = series.index[12]
        series[shock_idx] = series[shock_idx] * 1.6  # inject a clear shock

        result = rolling_zscore(series, window=6, threshold=2.5)

        assert shock_idx in result.anomalous_index

    def test_no_anomalies_on_a_smooth_trend(self):
        series = pd.Series(np.linspace(1000, 2000, 15))
        result = rolling_zscore(series, window=6, threshold=2.5)
        assert len(result.anomalous_index) == 0

    def test_short_series_does_not_crash(self):
        # min_periods=3 means the first couple of points simply can't be scored.
        series = pd.Series([100.0, 110.0])
        result = rolling_zscore(series, window=6, threshold=2.5)
        assert len(result.anomalous_index) == 0


class TestIQROutliers:
    def test_flags_values_outside_fences(self):
        series = pd.Series([10, 11, 12, 13, 14, 15, 16, 100])  # 100 is a clear outlier
        result = iqr_outliers(series)

        assert result.outlier_mask.iloc[-1] == True  # noqa: E712
        assert result.outlier_mask.iloc[:-1].sum() == 0

    def test_fences_widen_with_larger_multiplier(self):
        series = pd.Series([10, 11, 12, 13, 14, 15, 16, 30])
        tight = iqr_outliers(series, multiplier=1.5)
        wide = iqr_outliers(series, multiplier=3.0)

        assert wide.upper_fence > tight.upper_fence


class TestIsolationForestAnomalies:
    def test_flags_obvious_multivariate_outlier(self):
        rng = np.random.default_rng(0)
        normal = pd.DataFrame({
            "amount": rng.normal(100, 5, size=200),
            "deviation": rng.normal(0, 2, size=200),
        })
        outlier = pd.DataFrame({"amount": [900.0], "deviation": [800.0]})
        features = pd.concat([normal, outlier], ignore_index=True)

        result = isolation_forest_anomalies(features, contamination=0.02)

        assert result.is_anomaly.iloc[-1] == True  # noqa: E712
        # The obvious outlier should have one of the lowest (most anomalous) decision scores.
        assert result.decision_score.iloc[-1] == result.decision_score.min()
