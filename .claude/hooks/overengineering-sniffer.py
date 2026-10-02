#!/usr/bin/env python3
"""PostToolUse/Write|Edit: advisory sniffer for over-engineering and silent failures.

Never blocks. Exits 0 always, surfacing at most five findings as a warning to the user and
as context to the model. Heuristics, not verdicts — read the line before acting.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

MAX_FINDINGS = 5
CODE_SUFFIXES = {".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".go", ".java"}

SECRETISH = re.compile(
    r"""(?:os\.getenv|os\.environ\.get)\(\s*["'][^"']*"""
    r"""(?:SECRET|KEY|TOKEN|PASSWORD|PASSWD|CREDENTIAL|PROJECT|BUCKET|URL|URI|DSN)"""
    r"""[^"']*["']\s*,""",
    re.IGNORECASE,
)
MARKERS = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b|\b(jira|sprint)\b", re.IGNORECASE)
SPANISH_ACCENT = re.compile(r"[áéíóúÁÉÍÓÚñÑ¿¡]")
SPANISH_WORDS = re.compile(
    r"\b(que|para|con|este|esta|porque|cuando|entonces|debe|cada|según|pero|desde|"
    r"todos|todas|hacia|aunque)\b",
    re.IGNORECASE,
)
DOMAIN_ALLOW = re.compile(
    r"\b(cuit|importe\w*|numero_op|adjunto\w*|conciliaci\w*|ErrorNegocio|ErrorSistema|"
    r"ProcesadoParcial|Reintento)\b",
    re.IGNORECASE,
)
HANDLED = re.compile(r"logger|log\.|logging|raise|report|noqa|warn|print\(")


def comment_text(line: str) -> str:
    if "#" in line:
        return line.split("#", 1)[1]
    if "//" in line:
        return line.split("//", 1)[1]
    return ""


def except_blocks(lines: list[str]) -> list[tuple[int, list[str]]]:
    blocks = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not re.match(r"except\b.*:", stripped):
            continue
        indent = len(line) - len(line.lstrip())
        body = []
        for follow in lines[i + 1 :]:
            if not follow.strip():
                continue
            if len(follow) - len(follow.lstrip()) <= indent:
                break
            body.append(follow)
        blocks.append((i + 1, body))
    return blocks


def sniff(path: Path, text: str) -> list[str]:
    lines = text.splitlines()
    is_test = "test" in path.name
    out: list[str] = []

    for lineno, body in except_blocks(lines):
        joined = " ".join(body)
        if body and all(b.strip() in {"pass", "...", "return", "return None"} for b in body):
            out.append(f"{path.name}:{lineno} except swallows the failure silently (no log, no raise)")
        elif "Exception" in lines[lineno - 1] and not HANDLED.search(joined):
            out.append(
                f"{path.name}:{lineno} broad except with no log or re-raise — "
                "is this a declared edge?"
            )

    for i, line in enumerate(lines, start=1):
        if SECRETISH.search(line):
            out.append(
                f"{path.name}:{i} config fallback for a secret/env var — "
                "the deploy sets it; fail at boot instead"
            )
        if MARKERS.search(line):
            out.append(f"{path.name}:{i} TODO/FIXME or issue reference in code — tickets live in commits")
        comment = comment_text(line)
        if comment and not DOMAIN_ALLOW.search(comment):
            if SPANISH_ACCENT.search(comment) or len(SPANISH_WORDS.findall(comment)) >= 2:
                out.append(f"{path.name}:{i} comment looks like Spanish — prose is English")
        if not is_test and re.search(r"\btime\.sleep\(|\bawait asyncio\.sleep\(", line):
            out.append(f"{path.name}:{i} sleep in production code — wait on a condition, not a clock")

    if re.search(r"@abstractmethod|\(ABC\)|\(Protocol\)", text):
        bases = set(re.findall(r"class\s+(\w+)\s*\((?:ABC|Protocol)\)", text))
        implementations = sum(
            1 for base in bases for _ in re.finditer(rf"class\s+\w+\s*\(\s*{base}\b", text)
        )
        if bases and implementations <= 1:
            out.append(
                f"{path.name} abstract base with {implementations} implementation — "
                "use the concrete class"
            )

    if is_test:
        asserts = re.findall(r"\bassert\w*", text)
        if asserts and all(a.startswith("assert_") for a in asserts):
            out.append(
                f"{path.name} the only assertions are on mocks — this verifies the mock, not our code"
            )

    return out


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
    if path.suffix not in CODE_SUFFIXES or not path.is_file():
        sys.exit(0)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        sys.exit(0)

    findings = sniff(path, text)[:MAX_FINDINGS]
    if not findings:
        sys.exit(0)
    body = "\n".join(f"- {f}" for f in findings)
    print(
        json.dumps(
            {
                "systemMessage": f"over-engineering sniffer:\n{body}",
                "suppressOutput": True,
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        "Advisory only (not a block). Heuristic findings in the file just "
                        f"written — verify each before changing anything:\n{body}\n"
                        "Guidance: refining-ideas."
                    ),
                },
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
