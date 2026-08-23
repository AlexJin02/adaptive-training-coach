from __future__ import annotations

import ast
from pathlib import Path

from app import api


def test_route_module_has_no_direct_database_access() -> None:
    """Keep persistence mechanics in services, never FastAPI route handlers."""

    source_path = Path(api.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))

    sqlalchemy_imports: list[str] = []
    model_imports: list[str] = []
    forbidden_calls: list[str] = []
    mutation_methods = {
        "add",
        "add_all",
        "commit",
        "delete",
        "execute",
        "flush",
        "get",
        "refresh",
        "rollback",
        "scalar",
        "scalars",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            sqlalchemy_imports.extend(
                alias.name for alias in node.names if alias.name.startswith("sqlalchemy")
            )
            model_imports.extend(alias.name for alias in node.names if alias.name == "app.models")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").startswith("sqlalchemy"):
                sqlalchemy_imports.append(node.module or "sqlalchemy")
            if node.module == "app" and any(alias.name == "models" for alias in node.names):
                model_imports.append("app.models")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "db"
            and node.func.attr in mutation_methods
        ):
            forbidden_calls.append(f"db.{node.func.attr} at line {node.lineno}")

    assert sqlalchemy_imports == []
    assert model_imports == []
    assert forbidden_calls == []
