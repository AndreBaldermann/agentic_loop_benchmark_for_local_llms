from __future__ import annotations

import ast
import re
import subprocess
import tempfile
from pathlib import Path


def strip_ansi(text: str) -> str:
    """
    Remove ANSI escape sequences from model output text.

    Args:
        text, str: raw model or terminal text.

    Returns:
        cleaned_text, str: text without ANSI escape sequences.
    """
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)


def estimate_tokens(text: str) -> int:
    """
    Estimate token count when the backend does not report tokens.

    Args:
        text, str: prompt or output text.

    Returns:
        tokens, int, >= 1: rough four-characters-per-token estimate.
    """
    return max(1, len(text) // 4)


def extract_python_code(text: str) -> str:
    """
    Extract Python code from a model response.

    Args:
        text, str: raw model response that may include Markdown fences or prose.

    Returns:
        code, str: best-effort Python source extracted from the response.
    """
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
    """
    Normalize generated code before comparison or validation.

    Args:
        code, str: Python source code.

    Returns:
        normalized_code, str: code with normalized line endings and trailing whitespace removed.
    """
    code = strip_ansi(code)
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in code.strip().splitlines()).strip()


def syntax_check(code: str) -> tuple[bool, str]:
    """
    Check whether Python code compiles.

    Args:
        code, str: Python source code to compile.

    Returns:
        result, tuple[bool, str]: success flag and stderr text when compilation fails.
    """
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
    """
    Parse Python code with the ast module.

    Args:
        code, str: Python source code to parse.

    Returns:
        result, tuple[bool, str]: success flag and formatted SyntaxError when parsing fails.
    """
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as exc:
        return False, f"{exc.__class__.__name__}: {exc}"
