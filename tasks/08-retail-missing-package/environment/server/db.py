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
    ("support_case", "WST481662"): "8cf648a4-ca60-4387-bc11-ec38f426123a",
    ("notification", "notification-8cf648a4-ca60-4387-bc11-ec38f426123a"): "521527dc-8856-4b33-8e08-69658b1ca80b",
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
    return str(uuid.uuid5(ID_NAMESPACE, f"retail:{kind}:{name}"))


def allocate_named(cur, entity_type: str, scope: str = "") -> tuple[str, str]:
    """Issue the next name for an entity type and its id, advancing the allocator.

    Some names are quoted to the customer, so both halves are handed back.
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
    name = row["template"].format(n=row["issued"])
    return name, derive_id(entity_type, name)


def allocate_id(cur, entity_type: str, scope: str = "") -> str:
    return allocate_named(cur, entity_type, scope)[1]


class ToolRefusal(Exception):
    """A domain precondition was not met. Surfaces as HTTP 409."""

    def __init__(self, message: str, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class NotFound(Exception):
    """A referenced entity does not exist. Surfaces as HTTP 404."""
