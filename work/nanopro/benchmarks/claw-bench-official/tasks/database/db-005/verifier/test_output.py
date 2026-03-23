"""Verifier for db-005: Query Optimization."""

import json
import re
import sqlite3
from pathlib import Path

import pytest


SCHEMA_TABLES = {
    "customers": ["id", "name", "email", "phone", "country", "created_at", "is_active"],
    "products": ["id", "name", "description", "price", "category", "stock_quantity", "created_at", "is_available"],
    "orders": ["id", "customer_id", "order_date", "total_amount", "status", "shipping_address"],
    "order_items": ["id", "order_id", "product_id", "quantity", "unit_price"],
}


@pytest.fixture
def workspace(request):
    return Path(request.config.getoption("--workspace"))


@pytest.fixture
def schema_sql(workspace):
    path = workspace / "schema.sql"
    assert path.exists(), "schema.sql not found in workspace"
    return path.read_text()


@pytest.fixture
def optimized_sql(workspace):
    path = workspace / "optimized_queries.sql"
    assert path.exists(), "optimized_queries.sql not found in workspace"
    return path.read_text()


@pytest.fixture
def optimized_queries(optimized_sql):
    parts = re.split(r"--\s*Query\s+\d+", optimized_sql)
    queries = [p.strip() for p in parts if p.strip()]
    return queries


@pytest.fixture
def index_recs(workspace):
    path = workspace / "index_recommendations.json"
    assert path.exists(), "index_recommendations.json not found in workspace"
    return json.loads(path.read_text())


@pytest.fixture
def db_connection(schema_sql):
    conn = sqlite3.connect(":memory:")
    conn.executescript(schema_sql)
    yield conn
    conn.close()


# ── Core checks (weight 3) ──────────────────────────────────────────────────


@pytest.mark.weight(3)
def test_optimized_queries_file_exists(workspace):
    assert (workspace / "optimized_queries.sql").exists(), "optimized_queries.sql not found"


@pytest.mark.weight(3)
def test_index_recommendations_file_exists(workspace):
    assert (workspace / "index_recommendations.json").exists(), "index_recommendations.json not found"


@pytest.mark.weight(3)
def test_optimized_has_three_queries(optimized_sql):
    markers = re.findall(r"--\s*Query\s+\d+", optimized_sql)
    assert len(markers) == 3, f"Expected 3 '-- Query N' markers, found {len(markers)}"


@pytest.mark.weight(3)
def test_query1_valid_sql(db_connection, optimized_queries):
    assert len(optimized_queries) >= 1, "No queries found"
    try:
        db_connection.execute(f"EXPLAIN {optimized_queries[0]}")
    except sqlite3.Error as e:
        pytest.fail(f"Query 1 is not valid SQL: {e}")


@pytest.mark.weight(3)
def test_query2_valid_sql(db_connection, optimized_queries):
    assert len(optimized_queries) >= 2, "Less than 2 queries found"
    try:
        db_connection.execute(f"EXPLAIN {optimized_queries[1]}")
    except sqlite3.Error as e:
        pytest.fail(f"Query 2 is not valid SQL: {e}")


@pytest.mark.weight(3)
def test_query3_valid_sql(db_connection, optimized_queries):
    assert len(optimized_queries) >= 3, "Less than 3 queries found"
    try:
        db_connection.execute(f"EXPLAIN {optimized_queries[2]}")
    except sqlite3.Error as e:
        pytest.fail(f"Query 3 is not valid SQL: {e}")


@pytest.mark.weight(3)
def test_index_recs_is_array(index_recs):
    assert isinstance(index_recs, list), "index_recommendations.json must be a JSON array"


@pytest.mark.weight(3)
def test_index_recs_minimum_count(index_recs):
    assert len(index_recs) >= 3, f"Need at least 3 index recommendations, found {len(index_recs)}"


@pytest.mark.weight(3)
def test_index_recs_required_fields(index_recs):
    for i, rec in enumerate(index_recs):
        for field in ("table", "columns", "reason"):
            assert field in rec, f"Recommendation {i} missing '{field}' field"


@pytest.mark.weight(3)
def test_index_recs_valid_tables(index_recs):
    valid_tables = set(SCHEMA_TABLES.keys())
    for i, rec in enumerate(index_recs):
        assert rec["table"] in valid_tables, (
            f"Recommendation {i} references unknown table '{rec['table']}'"
        )


@pytest.mark.weight(3)
def test_index_recs_valid_columns(index_recs):
    for i, rec in enumerate(index_recs):
        table = rec["table"]
        if table not in SCHEMA_TABLES:
            continue
        valid_cols = set(SCHEMA_TABLES[table])
        for col in rec["columns"]:
            assert col in valid_cols, (
                f"Recommendation {i}: column '{col}' not in table '{table}'"
            )


@pytest.mark.weight(3)
def test_no_select_star(optimized_queries):
    for i, q in enumerate(optimized_queries):
        normalized = re.sub(r"\s+", " ", q.upper())
        assert "SELECT *" not in normalized, (
            f"Query {i+1} still uses SELECT *"
        )


# ── Bonus checks (weight 1) ──────────────────────────────────────────────────


@pytest.mark.weight(1)
def test_no_lower_upper_in_where(optimized_queries):
    for i, q in enumerate(optimized_queries):
        upper = q.upper()
        has_lower = bool(re.search(r"\bLOWER\s*\(", upper))
        has_upper = bool(re.search(r"\bUPPER\s*\(", upper))
        assert not (has_lower or has_upper), (
            f"Query {i+1} wraps column in LOWER()/UPPER() preventing index usage"
        )


@pytest.mark.weight(1)
def test_no_unnecessary_distinct(optimized_queries):
    for i, q in enumerate(optimized_queries):
        upper = q.upper().strip()
        if "GROUP BY" in upper:
            assert "DISTINCT" not in upper, (
                f"Query {i+1} uses DISTINCT with GROUP BY which is redundant"
            )


@pytest.mark.weight(1)
def test_query2_uses_join(optimized_queries):
    assert len(optimized_queries) >= 2, "Less than 2 queries found"
    upper = optimized_queries[1].upper()
    assert "JOIN" in upper, "Query 2 should use an explicit JOIN instead of a subquery"


@pytest.mark.weight(1)
def test_query2_no_subquery(optimized_queries):
    assert len(optimized_queries) >= 2, "Less than 2 queries found"
    upper = optimized_queries[1].upper()
    has_subquery = bool(re.search(r"WHERE.*\(\s*SELECT", upper))
    assert not has_subquery, "Query 2 should not use a subquery; prefer JOIN"


@pytest.mark.weight(1)
def test_index_recs_columns_is_list(index_recs):
    for i, rec in enumerate(index_recs):
        assert isinstance(rec["columns"], list), (
            f"Recommendation {i}: 'columns' must be a list"
        )
        assert len(rec["columns"]) >= 1, (
            f"Recommendation {i}: 'columns' must have at least one entry"
        )


@pytest.mark.weight(1)
def test_index_recs_reason_not_empty(index_recs):
    for i, rec in enumerate(index_recs):
        assert isinstance(rec["reason"], str) and len(rec["reason"].strip()) > 10, (
            f"Recommendation {i}: 'reason' must be a meaningful explanation"
        )
