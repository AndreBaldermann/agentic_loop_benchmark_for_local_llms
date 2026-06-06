from __future__ import annotations

import ast
import re
import subprocess
import tempfile
from pathlib import Path


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)


def estimate_tokens(text: str) -> int:
    """Very rough fallback estimate. Prefer backend-reported token counts."""
    return max(1, len(text) // 4)


def extract_python_code(text: str) -> str:
    text = strip_ansi(text).strip()

    fenced = re.findall(
        r"```(?:python|py)?\s*(.*?)```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fenced:
        return fenced[-1].strip()

    lines = text.splitlines()
    start_idx = None
    for i, line in enumerate(lines):
        if line.startswith(("import ", "from ", "#!/usr/bin/env python", "def ", "class ")):
            start_idx = i
            break

    if start_idx is not None:
        text = "\n".join(lines[start_idx:])

    return text.strip()


def normalize_code(code: str) -> str:
    code = strip_ansi(code)
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in code.strip().splitlines()).strip()


def syntax_check(code: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        path = f.name

    result = subprocess.run(
        ["python3", "-m", "py_compile", path],
        text=True,
        capture_output=True,
    )

    Path(path).unlink(missing_ok=True)

    if result.returncode == 0:
        return True, ""

    return False, result.stderr.strip()


def ast_check(code: str) -> tuple[bool, str]:
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as exc:
        return False, f"{exc.__class__.__name__}: {exc}"
