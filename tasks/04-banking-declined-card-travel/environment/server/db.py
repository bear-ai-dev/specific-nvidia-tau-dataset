"""Database access for the tool server.

One connection per request with autocommit off, so a handler that raises leaves
no partial mutation behind. Rows come back as dicts.
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

DSN = os.environ.get(
    "TOOL_DB_DSN",
    "host=127.0.0.1 port=5432 dbname=voiceenv user=voiceenv password=voiceenv",
)

# Same namespace the seed generator uses.
ID_NAMESPACE = uuid.UUID("7b8ad81e-4376-52a6-be30-158fb0ac90bb")

# Ids the dataset pins; the rest are derived.
PINNED = {
    ("transaction", "hotel-authorization-840"): "f96da295-2259-4311-b31d-661ab6053092",
    ("notice", "travel-notice-colin-portland"): "31d46fb6-e721-4a9c-b54d-6c631dbe9686",
    ("verification", "verification-colin-reeves-card"): "308f6850-19d3-4667-9f16-97bc37d46902",
}


@contextmanager
def transaction():
    """Yield a dict cursor inside a transaction, committing on clean exit."""
    conn = psycopg2.connect(DSN)
    try:
        conn.autocommit = False
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def one(cur, sql: str, params: tuple = ()) -> dict | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None


def all_rows(cur, sql: str, params: tuple = ()) -> list[dict]:
    cur.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def scalar(cur, sql: str, params: tuple = ()):
    cur.execute(sql, params)
    row = cur.fetchone()
    if row is None:
        return None
    return list(row.values())[0]


def scenario_value(cur, key: str) -> str | None:
    return scalar(cur, "SELECT value FROM scenario WHERE key = %s", (key,))


def derive_id(kind: str, name: str) -> str:
    pinned = PINNED.get((kind, name))
    if pinned is not None:
        return pinned
    return str(uuid.uuid5(ID_NAMESPACE, f"banking:{kind}:{name}"))


def allocate_id(cur, entity_type: str, scope: str = "") -> str:
    """Issue the next identifier for an entity type, advancing the allocator.

    The template names the allocation; the id handed out is its UUID.
    """
    row = one(
        cur,
        """
        UPDATE id_allocator
           SET next_value = next_value + 1
         WHERE entity_type = %s AND scope = %s
        RETURNING next_value - 1 AS issued, template
        """,
        (entity_type, scope),
    )
    if row is None:
        raise KeyError(f"no allocator for entity_type={entity_type!r} scope={scope!r}")
    return derive_id(entity_type, row["template"].format(n=row["issued"]))


class ToolRefusal(Exception):
    """A domain precondition was not met. Surfaces as HTTP 409."""

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFound(Exception):
    """A referenced entity does not exist. Surfaces as HTTP 404."""
