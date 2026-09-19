"""Paths, DB connection parameters, and detection thresholds."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs"

DB_PARAMS = dict(
    dbname="revenue_assurance_dq",
    user="postgres",
    password="postgres",
    host="localhost",
)


def db_url() -> str:
    p = DB_PARAMS
    return f"postgresql+psycopg2://{p['user']}:{p['password']}@{p['host']}/{p['dbname']}"


# --- Anomaly detection thresholds ---
ZSCORE_WINDOW = 6          # months of trailing history used as the rolling baseline
ZSCORE_THRESHOLD = 2.5     # |z| above this is flagged
IQR_MULTIPLIER = 1.5       # standard Tukey's-fences multiplier
ISOLATION_FOREST_CONTAMINATION = 0.01  # expected fraction of anomalies
ISOLATION_FOREST_SEED = 42

# Fixed display order for the DQ scorecard.
DQ_DIMENSIONS = ["Completeness", "Uniqueness", "Validity", "Consistency", "Timeliness"]
