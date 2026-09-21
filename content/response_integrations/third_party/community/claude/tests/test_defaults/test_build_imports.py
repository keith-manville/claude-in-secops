"""Guard against imports that break once `mp build` flattens the integration.

The build copies every module under `core/` into a single `Managers/` directory and every
action into `ActionsScripts/`, then rewrites relative imports to `from <module> import ...`.
Imports that reference a nested package path (for example `from .api.api_client import ...`)
are rewritten to a path that no longer exists in the flat layout and fail at runtime in SecOps
with `ModuleNotFoundError`. This test enforces a layout the rewriter handles.
"""

from __future__ import annotations

import ast
import pathlib

from .. import common

SOURCE_DIRS: tuple[str, ...] = ("actions", "core")


def _python_files(directory: pathlib.Path) -> list[pathlib.Path]:
    return sorted(path for path in directory.rglob("*.py") if ".venv" not in path.parts)


def test_core_has_no_subpackages() -> None:
    core: pathlib.Path = common.INTEGRATION_PATH / "core"
    subpackages: list[str] = [
        str(path.relative_to(core)) for path in core.iterdir() if path.is_dir() and not path.name.startswith("__")
    ]
    assert subpackages == [], f"core/ must stay flat, found subpackages: {subpackages}"


def test_relative_imports_survive_flattening() -> None:
    flat_modules: set[str] = {
        path.stem for directory in SOURCE_DIRS for path in _python_files(common.INTEGRATION_PATH / directory)
    }
    problems: list[str] = []
    for directory in SOURCE_DIRS:
        for path in _python_files(common.INTEGRATION_PATH / directory):
            tree: ast.Module = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or node.level == 0:
                    continue

                parts: list[str] = (node.module or "").split(".")
                if parts and parts[0] == "core":
                    parts = parts[1:]

                if len(parts) != 1 or parts[0] not in flat_modules:
                    location: str = f"{path.relative_to(common.INTEGRATION_PATH)}:{node.lineno}"
                    problems.append(f"{location}: from {'.' * node.level}{node.module} import ...")

    assert problems == [], "Relative imports must point at a single module inside core/ or actions/:\n" + "\n".join(
        problems
    )
