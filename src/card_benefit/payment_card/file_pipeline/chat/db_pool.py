"""Opt-in, lazy PostgreSQL query pool for the fp_chat adapter."""
from __future__ import annotations

import atexit
import os
from typing import Callable


class PoolQueryRunner:
    """Run read queries through one lazy pool, with one fresh-connection fallback."""

    def __init__(self, original_run_query: Callable):
        self._original_run_query = original_run_query
        self._pool = None
        self._atexit_registered = False

    def _close(self):
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    def _get_pool(self):
        if self._pool is None:
            url = os.getenv("DB_URL")
            if not url:
                raise RuntimeError("DB_URL 환경 변수가 필요합니다.")
            from psycopg_pool import ConnectionPool  # noqa: PLC0415

            self._pool = ConnectionPool(
                conninfo=url,
                kwargs={
                    "autocommit": True,
                    "row_factory": __import__("psycopg.rows", fromlist=["dict_row"]).dict_row,
                    "prepare_threshold": None,
                    "connect_timeout": 10,
                },
                min_size=1,
                max_size=4,
                max_idle=60,
                max_lifetime=300,
                check=ConnectionPool.check_connection,
                open=False,
            )
            self._pool.open()
            if not self._atexit_registered:
                atexit.register(self._close)
                self._atexit_registered = True
        return self._pool

    @staticmethod
    def _is_connection_error(exc: Exception) -> bool:
        import psycopg  # noqa: PLC0415

        return isinstance(exc, psycopg.Error)

    def _pool_query(self, query: str, params: dict | None):
        pool = self._get_pool()
        with pool.connection() as conn:
            try:
                return conn.execute(query, params or {}).fetchall()
            except Exception as exc:
                if self._is_connection_error(exc):
                    conn.close()
                raise

    def __call__(self, query: str, params: dict | None = None) -> list[dict]:
        for _ in range(2):
            try:
                return self._pool_query(query, params)
            except Exception as exc:
                if not self._is_connection_error(exc):
                    raise
        return self._original_run_query(query, params)
