"""Data tools: CSV/JSON parsing, safe calculator, time, read-only SQLite."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import sqlite3
import statistics
import time
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field

from app.core.risk import RiskLevel
from app.files.fs import Access, FsError
from app.tools.base import Capability, ToolContext, ToolDefinition, ToolError
from app.tools.safeexpr import ExpressionError, evaluate

MAX_CSV_ROWS = 200_000
QUERY_TIMEOUT_S = 8.0


def _num(v: str) -> float | None:
    try:
        return float(v.replace(",", "")) if v.strip() not in ("", "nan", "NaN") else None
    except ValueError:
        return None


class ParseCsvArgs(BaseModel):
    path: str = Field(description="CSV file, e.g. 'files/sales.csv'.", max_length=500)
    delimiter: str | None = Field(
        default=None, max_length=1, description="Leave empty to detect automatically."
    )
    sample_rows: int = Field(default=5, ge=0, le=50)


async def parse_csv(ctx: ToolContext, a: ParseCsvArgs) -> dict[str, Any]:
    try:
        text, cut = ctx.fs.read_text(a.path, max_bytes=20_000_000)
    except FsError as e:
        raise ToolError(e.message, code=e.code) from e
    try:
        delim = a.delimiter or csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        delim = ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        header = next(reader)
    except StopIteration:
        raise ToolError("The CSV file is empty.", code="empty") from None
    cols: list[list[str]] = [[] for _ in header]
    rows = 0
    for row in reader:
        rows += 1
        if rows > MAX_CSV_ROWS:
            cut = True
            break
        for i in range(len(header)):
            cols[i].append(row[i] if i < len(row) else "")
    columns: list[dict[str, Any]] = []
    for name, values in zip(header, cols, strict=True):
        non_empty = [v for v in values if v.strip() != ""]
        nums = [n for n in (_num(v) for v in non_empty) if n is not None]
        info: dict[str, Any] = {
            "name": name,
            "nulls": len(values) - len(non_empty),
            "unique": len(set(non_empty)),
        }
        if non_empty and len(nums) == len(non_empty):
            info["type"] = "integer" if all(float(n).is_integer() for n in nums) else "number"
            info.update(
                min=min(nums),
                max=max(nums),
                mean=round(statistics.fmean(nums), 6),
                median=statistics.median(nums),
            )
        else:
            info["type"] = "text"
            info["top_values"] = (
                sorted({v for v in non_empty}, key=lambda v: -values.count(v))[:3]
                if len(set(non_empty)) <= 200
                else []
            )
        columns.append(info)
    sample = []
    for i in range(min(a.sample_rows, rows)):
        sample.append({h: (cols[j][i] if i < len(cols[j]) else "") for j, h in enumerate(header)})
    return {
        "path": a.path,
        "delimiter": delim,
        "rows": rows,
        "columns": columns,
        "sample": sample,
        "truncated": cut,
    }


class ParseJsonArgs(BaseModel):
    path: str | None = Field(
        default=None, description="JSON file to read, e.g. 'files/data.json'.", max_length=500
    )
    text: str | None = Field(default=None, description="Or JSON text directly.", max_length=1_000_000)
    pointer: str | None = Field(
        default=None, description="JSON Pointer to a part, like '/items/0/name'.", max_length=300
    )
    max_chars: int = Field(default=10_000, ge=100, le=100_000)


def _pointer(doc: Any, pointer: str) -> Any:
    if pointer in ("", "/"):
        return doc
    if not pointer.startswith("/"):
        raise ToolError("A JSON Pointer must start with '/'.", code="bad_pointer")
    cur = doc
    for raw in pointer[1:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        try:
            cur = cur[int(key)] if isinstance(cur, list) else cur[key]
        except (KeyError, IndexError, ValueError, TypeError):
            raise ToolError(f"Nothing at '{pointer}' (stopped at '{key}').", code="bad_pointer") from None
    return cur


def _shape(v: Any, depth: int = 0) -> Any:
    if isinstance(v, dict):
        return (
            {k: _shape(x, depth + 1) for k, x in list(v.items())[:15]}
            if depth < 3
            else f"object({len(v)} keys)"
        )
    if isinstance(v, list):
        return [f"list({len(v)})", _shape(v[0], depth + 1)] if v and depth < 3 else f"list({len(v)})"
    return type(v).__name__


async def parse_json(ctx: ToolContext, a: ParseJsonArgs) -> dict[str, Any]:
    if (a.path is None) == (a.text is None):
        raise ToolError("Give either 'path' or 'text', not both.", code="invalid_args")
    raw = a.text
    if a.path is not None:
        try:
            raw, _ = ctx.fs.read_text(a.path, max_bytes=5_000_000)
        except FsError as e:
            raise ToolError(e.message, code=e.code) from e
    try:
        doc = json.loads(raw or "")
    except json.JSONDecodeError as exc:
        raise ToolError(
            f"Invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}.", code="invalid_json"
        ) from None
    part = _pointer(doc, a.pointer) if a.pointer else doc
    dumped = json.dumps(part, ensure_ascii=False, indent=1)
    return {"shape": _shape(part), "value": dumped[: a.max_chars], "truncated": len(dumped) > a.max_chars}


class CalculatorArgs(BaseModel):
    expression: str = Field(
        description="Arithmetic like '(1200 * 1.08) / 12', or math like 'sqrt(2) * pi'. Functions: sqrt, log, exp, sin, cos, round, min, max, abs, floor, ceil…",
        min_length=1,
        max_length=500,
    )
    variables: dict[str, float | int | str | bool] = Field(default_factory=dict, max_length=30)


async def calculator(ctx: ToolContext, a: CalculatorArgs) -> dict[str, Any]:
    try:
        value = evaluate(a.expression, a.variables)
    except ExpressionError as e:
        raise ToolError(str(e), code="bad_expression") from e
    return {"expression": a.expression, "result": value}


class DateTimeArgs(BaseModel):
    timezone: str | None = Field(
        default=None, description="IANA name like 'Africa/Lagos'. Default UTC.", max_length=64
    )
    convert: str | None = Field(
        default=None,
        description="An ISO-8601 timestamp to convert into 'timezone' instead of showing the current time.",
        max_length=64,
    )


async def datetime_tool(ctx: ToolContext, a: DateTimeArgs) -> dict[str, Any]:
    try:
        zone = ZoneInfo(a.timezone) if a.timezone else UTC
    except (ZoneInfoNotFoundError, ValueError):
        raise ToolError(
            f"Unknown time zone '{a.timezone}'. Use an IANA name like 'Europe/Paris'.", code="bad_timezone"
        ) from None
    if a.convert:
        try:
            base = datetime.fromisoformat(a.convert.replace("Z", "+00:00"))
        except ValueError:
            raise ToolError(
                "Could not read that timestamp; use ISO-8601 like 2026-01-31T09:00:00+00:00.",
                code="bad_timestamp",
            ) from None
        if base.tzinfo is None:
            base = base.replace(tzinfo=UTC)
    else:
        base = datetime.now(UTC)
    local = base.astimezone(zone)
    return {
        "iso": local.isoformat(timespec="seconds"),
        "timezone": str(zone),
        "weekday": local.strftime("%A"),
        "utc": base.astimezone(UTC).isoformat(timespec="seconds"),
    }


class DatabaseQueryArgs(BaseModel):
    path: str = Field(description="SQLite file inside the project, e.g. 'files/app.db'.", max_length=500)
    sql: str = Field(
        description="One read-only SELECT (or WITH … SELECT) statement.", min_length=1, max_length=5000
    )
    max_rows: int = Field(default=100, ge=1, le=500)


_SELECT = re.compile(r"^\s*(?:--[^\n]*\n\s*|/\*.*?\*/\s*)*(select|with)\b", re.IGNORECASE | re.DOTALL)
# Recursive CTEs are read-only; the progress handler below bounds how long they can run.
_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


def _query_sync(db_path: str, sql: str, max_rows: int, timeout_s: float) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.set_authorizer(
            lambda action, *_: sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY
        )
        deadline = time.monotonic() + timeout_s
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 2000)
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(max_rows + 1)
        clean = [[f"<{len(v)} bytes>" if isinstance(v, bytes) else v for v in r] for r in rows[:max_rows]]
        return {"columns": cols, "rows": clean, "row_count": len(clean), "truncated": len(rows) > max_rows}
    finally:
        conn.close()


async def database_query(ctx: ToolContext, a: DatabaseQueryArgs) -> dict[str, Any]:
    if not _SELECT.match(a.sql):
        raise ToolError("Only SELECT queries are allowed.", code="read_only")
    try:
        _, path = ctx.fs.resolve(a.path, Access.READ)
    except FsError as e:
        raise ToolError(e.message, code=e.code) from e
    if path.suffix.lower() not in (".db", ".sqlite", ".sqlite3") or not path.is_file():
        raise ToolError("That is not a SQLite database file (.db, .sqlite, .sqlite3).", code="not_a_database")
    try:
        return await asyncio.to_thread(_query_sync, path.as_posix(), a.sql, a.max_rows, QUERY_TIMEOUT_S)
    except sqlite3.OperationalError as exc:
        msg = str(exc)
        raise ToolError(
            "The query ran too long and was stopped." if "interrupted" in msg else f"SQL error: {msg}",
            code="sql_error",
        ) from None
    except sqlite3.DatabaseError as exc:
        if "not authorized" in str(exc):
            raise ToolError(
                "That statement is not allowed. Only plain read-only SELECT queries can run.",
                code="read_only",
            ) from None
        raise ToolError(f"SQL error: {exc}", code="sql_error") from None


TOOLS = [
    ToolDefinition(
        "parse_csv",
        "Summarise a CSV file: columns, types, statistics and sample rows.",
        ParseCsvArgs,
        RiskLevel.SAFE,
        parse_csv,
        permissions=frozenset({Capability.FS_READ}),
        returns_untrusted=True,
        source_label=lambda a: f"file:{a.path}",
    ),
    ToolDefinition(
        "parse_json",
        "Parse a JSON file or text, optionally selecting a part with a JSON Pointer.",
        ParseJsonArgs,
        RiskLevel.SAFE,
        parse_json,
        permissions=frozenset({Capability.FS_READ}),
        returns_untrusted=True,
        source_label=lambda a: f"file:{a.path}" if a.path else "json:text",
    ),
    ToolDefinition(
        "calculator",
        "Evaluate arithmetic exactly. Prefer this to mental maths.",
        CalculatorArgs,
        RiskLevel.SAFE,
        calculator,
    ),
    ToolDefinition(
        "datetime",
        "Current date and time, or convert a timestamp to a time zone.",
        DateTimeArgs,
        RiskLevel.SAFE,
        datetime_tool,
    ),
    ToolDefinition(
        "database_query",
        "Run one read-only SELECT against a SQLite file in the project.",
        DatabaseQueryArgs,
        RiskLevel.SAFE,
        database_query,
        permissions=frozenset({Capability.DB_READ}),
        returns_untrusted=True,
        source_label=lambda a: f"db:{a.path}",
        timeout_s=15,
    ),
]
