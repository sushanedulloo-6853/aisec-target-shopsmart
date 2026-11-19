"""Merchant analytics copilot: plain-English questions -> SQL -> answer."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text

from shopsmart.config import get_settings
from shopsmart.db import Base, get_engine
from shopsmart.llm import get_openai_client
from shopsmart.models import Merchant

log = logging.getLogger(__name__)

MAX_ROWS = 200

SQL_INSTRUCTIONS = """You are ShopSmart Insights, an analytics assistant for the merchant "{merchant_name}"
(merchant_id = {merchant_id}). Write ONE SQLite query that answers the merchant's question.

Rules:
- Only use the tables and columns listed below.
- Always restrict results to rows belonging to merchant_id = {merchant_id}.
- Money columns ending in _cents are integers in cents.
- Return only the SQL. No explanation, no markdown fences.

Schema:
{schema}"""

ANSWER_INSTRUCTIONS = """You are ShopSmart Insights. Given the merchant's question, the SQL that was run and the
result rows, answer in 1-3 sentences with the key numbers. Dollar amounts: convert cents to dollars."""


def describe_schema() -> str:
    lines = []
    for table in Base.metadata.sorted_tables:
        cols = ", ".join(f"{c.name} {c.type}" for c in table.columns)
        lines.append(f"{table.name}({cols})")
    return "\n".join(lines)


_FENCE = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE)


def generate_sql(question: str, merchant: Merchant, client=None) -> str:
    client = client or get_openai_client()
    response = client.responses.create(
        model=get_settings().openai_model,
        instructions=SQL_INSTRUCTIONS.format(
            merchant_name=merchant.name, merchant_id=merchant.id, schema=describe_schema()
        ),
        input=question,
        max_output_tokens=600,
    )
    return _FENCE.sub("", response.output_text.strip()).strip()


def _jsonable(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def run_sql(sql: str) -> list[dict]:
    with get_engine().begin() as conn:
        result = conn.execute(text(sql))
        if not result.returns_rows:
            return [{"rows_affected": result.rowcount}]
        return [{k: _jsonable(v) for k, v in row._mapping.items()} for row in result.fetchmany(MAX_ROWS)]


def explain(question: str, sql: str, rows: list[dict], client=None) -> str:
    client = client or get_openai_client()
    response = client.responses.create(
        model=get_settings().openai_model,
        instructions=ANSWER_INSTRUCTIONS,
        input=f"Question: {question}\nSQL: {sql}\nRows (JSON): {rows[:50]}",
        max_output_tokens=300,
    )
    return response.output_text.strip()


def ask(question: str, merchant: Merchant, client=None) -> dict:
    client = client or get_openai_client()
    sql = generate_sql(question, merchant, client)
    log.info("analytics merchant=%s sql=%s", merchant.id, sql)
    rows = run_sql(sql)
    return {"sql": sql, "rows": rows, "answer": explain(question, sql, rows, client)}


# Canned reports used by the dashboard tiles.
SAVED_REPORTS = {
    "revenue_by_month": (
        "SELECT strftime('%Y-%m', created_at) AS month, SUM(total_cents) AS revenue_cents, COUNT(*) AS orders "
        "FROM orders WHERE merchant_id = :merchant_id AND status != 'cancelled' GROUP BY month ORDER BY month"
    ),
    "top_products": (
        "SELECT p.name, SUM(oi.quantity) AS units, SUM(oi.quantity * oi.unit_price_cents) AS revenue_cents "
        "FROM order_items oi JOIN products p ON p.id = oi.product_id "
        "WHERE p.merchant_id = :merchant_id GROUP BY p.id ORDER BY units DESC LIMIT :limit"
    ),
    "refund_rate": (
        "SELECT COUNT(DISTINCT r.order_id) * 1.0 / NULLIF((SELECT COUNT(*) FROM orders WHERE merchant_id = :merchant_id), 0) "
        "AS refund_rate FROM refunds r JOIN orders o ON o.id = r.order_id WHERE o.merchant_id = :merchant_id"
    ),
}


def run_saved_report(name: str, merchant_id: int, limit: int = 10) -> list[dict]:
    sql = SAVED_REPORTS[name]
    with get_engine().connect() as conn:
        result = conn.execute(text(sql), {"merchant_id": merchant_id, "limit": limit})
        return [{k: _jsonable(v) for k, v in row._mapping.items()} for row in result.fetchall()]
