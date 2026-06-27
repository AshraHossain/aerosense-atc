"""Postgres StateStore adapter for AeroCommand distributed deployment.

Stores scenario state as JSONB; supports concurrent reads and writes.
Requires Postgres running (usually via docker-compose).
"""

import json
from typing import Any, Dict, Optional

import psycopg

from core.ports import StateStore


class PostgresStateStore(StateStore):
    """JSONB-backed state store for durable scenario persistence."""

    def __init__(self, connection_string: str = "postgresql://user:password@localhost:5432/aerosense"):
        """Initialize connection pool."""
        self.connection_string = connection_string
        self._init_schema()

    def _init_schema(self) -> None:
        """Create table if it doesn't exist."""
        with psycopg.connect(self.connection_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scenario_state (
                        key TEXT PRIMARY KEY,
                        data JSONB NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                    """
                )
            conn.commit()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with psycopg.connect(self.connection_string) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM scenario_state WHERE key = %s", (key,))
                row = cur.fetchone()
                return row[0] if row else None

    def set(self, key: str, value: Dict[str, Any]) -> None:
        with psycopg.connect(self.connection_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scenario_state (key, data) VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
                    """,
                    (key, json.dumps(value)),
                )
            conn.commit()

    def update(self, key: str, updates: Dict[str, Any]) -> None:
        with psycopg.connect(self.connection_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE scenario_state
                    SET data = data || %s, updated_at = NOW()
                    WHERE key = %s
                    """,
                    (json.dumps(updates), key),
                )
            conn.commit()

    def delete(self, key: str) -> None:
        with psycopg.connect(self.connection_string) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM scenario_state WHERE key = %s", (key,))
            conn.commit()

    def exists(self, key: str) -> bool:
        with psycopg.connect(self.connection_string) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM scenario_state WHERE key = %s", (key,))
                return cur.fetchone() is not None
