from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

from .models import BenchmarkTask


def _open_text(path: Path):
    """
    Open plain text or gzip-compressed text files.

    Args:
        path, Path: file path ending in .gz for gzip or any other suffix for plain text.

    Returns:
        handle, TextIO: readable text file handle.
    """
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def load_humaneval_tasks(path: str | Path, *, limit: int | None = None, task_id: str | None = None) -> list[BenchmarkTask]:
    """
    Load OpenAI HumanEval-compatible tasks from JSONL or JSONL.GZ.

    Args:
        path, str | Path: input task file path.
        limit, int | None: optional maximum number of tasks to load.
        task_id, str | None: optional exact task id filter.

    Returns:
        tasks, list[BenchmarkTask]: loaded HumanEval task objects.
    """
    source_path = Path(path)
    tasks: list[BenchmarkTask] = []
    with _open_text(source_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            current_id = str(row.get("task_id", ""))
            if task_id and current_id != task_id:
                continue
            tasks.append(
                BenchmarkTask(
                    task_id=current_id,
                    source="humaneval",
                    prompt=str(row.get("prompt", "")),
                    metadata={
                        "entry_point": row.get("entry_point"),
                        "source_file": str(source_path),
                    },
                    test=row.get("test"),
                    entry_point=row.get("entry_point"),
                    canonical_solution=row.get("canonical_solution"),
                )
            )
            if limit and len(tasks) >= limit:
                break
    return tasks


def load_csv_tasks(path: str | Path, *, limit: int | None = None, task_id: str | None = None) -> list[BenchmarkTask]:
    """
    Load generic benchmark tasks from a CSV file.

    Args:
        path, str | Path: input CSV path with task_id and prompt columns.
        limit, int | None: optional maximum number of tasks to load.
        task_id, str | None: optional exact task id filter.

    Returns:
        tasks, list[BenchmarkTask]: loaded CSV task objects.
    """
    source_path = Path(path)
    tasks: list[BenchmarkTask] = []
    with source_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            current_id = str(row.get("task_id", ""))
            if task_id and current_id != task_id:
                continue
            metadata = {k: v for k, v in row.items() if k not in {"task_id", "prompt", "test", "entry_point", "canonical_solution"}}
            tasks.append(
                BenchmarkTask(
                    task_id=current_id,
                    source="csv",
                    prompt=str(row.get("prompt", "")),
                    metadata=metadata,
                    test=row.get("test") or None,
                    entry_point=row.get("entry_point") or None,
                    canonical_solution=row.get("canonical_solution") or None,
                )
            )
            if limit and len(tasks) >= limit:
                break
    return tasks


def load_tasks(
    provider: str,
    path: str | Path,
    *,
    limit: int | None = None,
    task_id: str | None = None,
) -> list[BenchmarkTask]:
    """
    Load tasks from a named provider.

    Args:
        provider, str: supported value humaneval or csv.
        path, str | Path: provider-specific task file path.
        limit, int | None: optional maximum number of tasks to load.
        task_id, str | None: optional exact task id filter.

    Returns:
        tasks, list[BenchmarkTask]: loaded tasks in provider order.
    """
    if provider == "humaneval":
        return load_humaneval_tasks(path, limit=limit, task_id=task_id)
    if provider == "csv":
        return load_csv_tasks(path, limit=limit, task_id=task_id)
    raise ValueError(f"Unsupported task provider: {provider}")
