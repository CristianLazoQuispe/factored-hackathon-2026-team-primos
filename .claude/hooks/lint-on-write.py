#!/usr/bin/env python3
"""PostToolUse/Write|Edit: run the project's own linter on the file just written.

Blocks (exit 2) only when a configured linter reports a problem in that file. If the
project has no linter, or the linter itself fails to run, this exits 0 and says nothing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PY = {".py", ".pyi"}
JS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
RUFF_CONFIG = ("ruff.toml", ".ruff.toml")
ESLINT_CONFIG = (
    "eslint.config.js", "eslint.config.mjs", "eslint.config.ts",
    ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
)


def project_root(path: Path, markers: tuple[str, ...]) -> Path | None:
    for parent in [path.parent, *path.parents]:
        if any((parent / marker).exists() for marker in markers):
            return parent
        if (parent / "pyproject.toml").exists():
            try:
                text = (parent / "pyproject.toml").read_text(encoding="utf-8")
            except OSError:
                text = ""
            if "[tool.ruff" in text and markers is RUFF_CONFIG:
                return parent
        if (parent / ".git").exists():
            return None
    return None


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=25, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return 0, ""  # the linter itself is broken or missing: not the writer's problem
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)
    raw = (payload.get("tool_input") or {}).get("file_path") or (
        payload.get("tool_response") or {}
    ).get("filePath")
    if not raw:
        sys.exit(0)
    path = Path(raw)
    if not path.is_file():
        sys.exit(0)

    findings: list[str] = []
    if path.suffix in PY:
        root = project_root(path, RUFF_CONFIG)
        if root:
            for cmd in (
                ["ruff", "check", "--force-exclude", str(path)],
                ["ruff", "format", "--check", "--force-exclude", str(path)],
            ):
                code, out = run(cmd, root)
                if code != 0 and out:
                    findings.append(out)
    elif path.suffix in JS:
        root = project_root(path, ESLINT_CONFIG)
        if root:
            code, out = run(["npx", "--no-install", "eslint", str(path)], root)
            if code != 0 and out and "not found" not in out.lower():
                findings.append(out)

    if not findings:
        sys.exit(0)
    print(f"Linter findings in {path.name} — fix them now:", file=sys.stderr)
    print("\n".join(findings)[:4000], file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
