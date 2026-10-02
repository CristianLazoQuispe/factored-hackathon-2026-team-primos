"""Domain: the bank's rules as plain Python (disputes, autonomy tiers, escalation, checks).

No I/O and no framework imports (no FastAPI, LangChain, psycopg, DuckDB): every rule here is
a pure function or value object, unit-tested without mocks. tests/test_architecture.py enforces it.
"""
