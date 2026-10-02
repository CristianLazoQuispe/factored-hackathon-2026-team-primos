"""Hexagonal dependency rule: domain and application never import adapters or frameworks."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "app"
FRAMEWORKS = {
    "fastapi",
    "starlette",
    "langchain",
    "langgraph",
    "fastmcp",
    "telegram",
    "psycopg",
    "duckdb",
    "polars",
    "httpx",
    "boto3",
    "langfuse",
}
FORBIDDEN = {
    "domain": FRAMEWORKS | {"app.adapters", "app.application"},
    "application": FRAMEWORKS | {"app.adapters"},
}


def imported_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            modules |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("layer", FORBIDDEN)
def test_layer_does_not_depend_outward(layer: str) -> None:
    violations = [
        f"{path.relative_to(PACKAGE)} imports {module}"
        for path in (PACKAGE / layer).rglob("*.py")
        for module in imported_modules(path)
        if any(module == banned or module.startswith(f"{banned}.") for banned in FORBIDDEN[layer])
    ]
    assert not violations, violations
