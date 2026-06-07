from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

from .code_processing import syntax_check
from .models import BenchmarkTask, EvaluationResult


def evaluate_none(task: BenchmarkTask, code: str) -> EvaluationResult:
    """
    Return a disabled evaluation result.

    Args:
        task, BenchmarkTask: task associated with the code.
        code, str: generated code, ignored.

    Returns:
        result, EvaluationResult: disabled evaluator marker.
    """
    return EvaluationResult(enabled=False, name="none", passed=None)


def evaluate_syntax(task: BenchmarkTask, code: str) -> EvaluationResult:
    """
    Evaluate final code by compiling it with Python.

    Args:
        task, BenchmarkTask: task associated with the code.
        code, str: generated Python code.

    Returns:
        result, EvaluationResult: pass/fail syntax result and elapsed time.
    """
    start = time.time()
    ok, error = syntax_check(code)
    return EvaluationResult(
        enabled=True,
        name="syntax",
        passed=ok,
        score=1.0 if ok else 0.0,
        elapsed_s=time.time() - start,
        error_type=None if ok else "SyntaxError",
        error_message=error or None,
    )


def evaluate_humaneval(task: BenchmarkTask, code: str, *, timeout_seconds: int = 5) -> EvaluationResult:
    """
    Evaluate final code against HumanEval tests in a subprocess.

    Args:
        task, BenchmarkTask: HumanEval task containing test and entry_point.
        code, str: generated Python code.
        timeout_seconds, int, > 0: subprocess timeout.

    Returns:
        result, EvaluationResult: pass/fail, timeout, stdout, and stderr details.
    """
    start = time.time()
    if not task.test or not task.entry_point:
        return EvaluationResult(
            enabled=True,
            name="humaneval",
            passed=False,
            score=0.0,
            elapsed_s=time.time() - start,
            error_type="MissingHumanEvalTest",
            error_message="Task has no test or entry_point field.",
        )

    test_code = f"""
{code}

{task.test}

check({task.entry_point})
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "candidate_test.py"
        path.write_text(test_code, encoding="utf-8")
        try:
            proc = subprocess.run(
                ["python3", str(path)],
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                cwd=tmpdir,
            )
        except subprocess.TimeoutExpired as exc:
            return EvaluationResult(
                enabled=True,
                name="humaneval",
                passed=False,
                score=0.0,
                elapsed_s=time.time() - start,
                error_type="TimeoutExpired",
                error_message=str(exc),
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
            )

    passed = proc.returncode == 0
    return EvaluationResult(
        enabled=True,
        name="humaneval",
        passed=passed,
        score=1.0 if passed else 0.0,
        elapsed_s=time.time() - start,
        error_type=None if passed else "TestFailure",
        error_message=None if passed else (proc.stderr.strip() or proc.stdout.strip()),
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def evaluate(task: BenchmarkTask, code: str, evaluator: str) -> EvaluationResult:
    """
    Dispatch to the configured evaluator.

    Args:
        task, BenchmarkTask: active task.
        code, str: generated code to evaluate.
        evaluator, str: supported value none, syntax, or humaneval.

    Returns:
        result, EvaluationResult: normalized evaluator output.
    """
    if evaluator == "none":
        return evaluate_none(task, code)
    if evaluator == "syntax":
        return evaluate_syntax(task, code)
    if evaluator == "humaneval":
        return evaluate_humaneval(task, code)
    raise ValueError(f"Unsupported evaluator: {evaluator}")
