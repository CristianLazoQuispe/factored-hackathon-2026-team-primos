"""Rules for SQL written by the LLM: read-only, allowlisted tables, one customer's rows.

`scope_query` parses the model's SQL and returns *new* SQL generated from the parsed tree, so what
runs is what was checked, not the original text. Every customer-owned table is replaced by a
subquery already filtered to the session customer, so nothing the model writes (a WHERE clause,
a join, a subquery, a CTE, a UNION) can reach another customer's rows. Pure function, no I/O.

Refused on purpose, with a message the model can act on:
- anything that is not one SELECT (writes, DDL, SHOW, several statements, SELECT ... INTO);
- tables outside `core`'s allowlist (`ops.*`, `pg_catalog`, `information_schema`, ...);
- CTEs that reuse a real table's name (they could hide a table from the rewrite);
- functions the model has no business calling. Functions sqlglot knows (SUM, DATE_TRUNC, ...) are
  allowed; unknown ones are refused unless listed in SAFE_FUNCTIONS. That default-deny is what
  stops `query_to_xml('select * from core.transactions')`, which runs SQL from a string.
"""

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

SCHEMA = "core"
OWNED = frozenset(  # every row carries customer_id: rewritten to the session customer's rows
    {
        "customers",
        "products",
        "transactions",
        "billing",
        "service_bills",
        "app_sessions",
        "customer_service_summary",
        "complaints",
    }
)
REFERENCE = frozenset({"fx_rates", "service_billers"})  # no customer data: readable as is
SAFE_FUNCTIONS = frozenset(
    {"age", "date_part", "to_char", "split_part", "initcap", "btrim", "ltrim", "rtrim"}
)
MAX_SQL_LENGTH = 4000
_WRITE_NODES = tuple(
    getattr(exp, name)
    for name in (
        "Insert",
        "Update",
        "Delete",
        "Merge",
        "Create",
        "Drop",
        "Alter",
        "Command",
        "Into",
        "Set",
        "Copy",
        "Grant",
        "TruncateTable",
        "Transaction",
        "Commit",
        "Rollback",
    )  # fmt: skip
    if hasattr(exp, name)
)
_PLAIN_TABLE_ARGS = {"this", "db", "alias"}


class PolicyViolation(ValueError):
    """The SQL is refused. The message is safe to show the model so it can correct itself."""


def scope_query(sql: str, customer_id: str) -> str:
    if not customer_id:
        raise PolicyViolation("No authenticated customer.")
    statement = _parse_single_select(sql)
    for node in statement.walk():
        node.comments = None  # nothing the model writes in a comment reaches the database
    _check_no_writes(statement)
    _check_functions(statement)
    _rewrite_tables(statement, customer_id)
    return statement.sql(dialect="postgres")


def _parse_single_select(sql: str) -> exp.Expression:
    text = (sql or "").strip()
    if not text:
        raise PolicyViolation("Write a SELECT query.")
    if len(text) > MAX_SQL_LENGTH:
        raise PolicyViolation(f"Query is longer than {MAX_SQL_LENGTH} characters.")
    try:
        parsed = [s for s in sqlglot.parse(text, dialect="postgres") if s is not None]
    except SqlglotError as error:
        raise PolicyViolation(f"Could not parse the query: {str(error).splitlines()[0]}") from None
    if len(parsed) != 1:
        raise PolicyViolation("Send exactly one statement.")
    if not isinstance(parsed[0], exp.Select | exp.SetOperation):
        raise PolicyViolation("Only SELECT queries are allowed.")
    return parsed[0]


def _check_no_writes(statement: exp.Expression) -> None:
    if statement.find(*_WRITE_NODES):
        raise PolicyViolation("Only read-only SELECT queries are allowed.")


def _check_functions(statement: exp.Expression) -> None:
    for function in statement.find_all(exp.Anonymous):
        if function.name.lower() not in SAFE_FUNCTIONS:
            raise PolicyViolation(f"Function {function.name}() is not allowed.")


def _rewrite_tables(statement: exp.Expression, customer_id: str) -> None:
    cte_names = {cte.alias.lower() for cte in statement.find_all(exp.CTE)}
    clash = cte_names & (OWNED | REFERENCE)
    if clash:
        raise PolicyViolation(f"Rename the CTE {sorted(clash)[0]!r}: it is a table name.")
    to_scope = []
    for table in statement.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            continue  # a table function; _check_functions already vetted it
        name = table.name.lower()
        if not table.db and name in cte_names:
            continue
        if table.catalog or (table.db and table.db.lower() != SCHEMA):
            raise PolicyViolation(f"Schema {table.db!r} is not available. Use the {SCHEMA} tables.")
        if name not in OWNED | REFERENCE:
            raise PolicyViolation(
                f"Table {table.name!r} is not available. "
                f"Available: {', '.join(sorted(OWNED | REFERENCE))}."
            )
        if {key for key, value in table.args.items() if value} - _PLAIN_TABLE_ARGS:
            raise PolicyViolation(f"Unsupported syntax on table {table.name!r}.")
        if name in OWNED:
            to_scope.append((table, name))
        else:  # reference table: only make sure it resolves to core, whatever the search_path
            table.set("this", exp.to_identifier(name))
            table.set("db", exp.to_identifier(SCHEMA))
    for table, name in to_scope:  # collected first: replacing while walking would revisit nodes
        own_rows = (
            exp.select("*")
            .from_(exp.table_(name, db=SCHEMA))
            .where(exp.column("customer_id").eq(exp.Literal.string(customer_id)))
        )
        table.replace(
            exp.Subquery(
                this=own_rows, alias=exp.TableAlias(this=exp.to_identifier(table.alias or name))
            )
        )
