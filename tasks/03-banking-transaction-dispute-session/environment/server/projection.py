"""Helpers for assembling tool results out of database rows.

A NULL column means the backend does not know the value, and the registries read
an absent field as unavailable, so `compact` drops None instead of emitting null.

JSON distinguishes 15 from 15.0 and the recorded results use both forms, so call
sites pick `as_int` or `as_float` rather than inferring it from the column type.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable


def compact(pairs: Iterable[tuple[str, Any]]) -> dict:
    """Build a dict from ordered pairs, dropping any whose value is None."""
    return {key: value for key, value in pairs if value is not None}


def as_int(value) -> int | None:
    """Render a numeric column as a JSON integer."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            raise ValueError(f"{value} is not integral and cannot render as int")
        return int(value)
    return int(value)


def as_float(value) -> float | None:
    """Render a numeric column as a JSON float."""
    if value is None:
        return None
    return float(value)


def as_list_always(value) -> list:
    """Render a Postgres array column, keeping an empty array as []."""
    return [] if value is None else list(value)
