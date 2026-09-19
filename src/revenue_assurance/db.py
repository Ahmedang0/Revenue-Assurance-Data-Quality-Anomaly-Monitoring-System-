"""Thin PostgreSQL connection helpers. Kept as a single small module so every
other module depends on *this*, not on psycopg2/SQLAlchemy directly — makes
it a single place to change if the connection method ever needs to change.
"""

from __future__ import annotations

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from revenue_assurance.config import DB_PARAMS, db_url


def get_connection() -> psycopg2.extensions.connection:
    """Raw psycopg2 connection — used where explicit transaction control
    (commit/rollback) is needed, e.g. writing anomaly flags."""
    return psycopg2.connect(**DB_PARAMS)


def get_engine() -> Engine:
    """SQLAlchemy engine — used for pandas.read_sql calls."""
    return create_engine(db_url())
