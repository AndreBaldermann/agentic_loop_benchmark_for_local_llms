from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import AgentCallRecord, LoopRunResult

SUMMARY_FIELDS = [
    "run_id",
    "timestamp",
    "experiment_id",
    "task_provider",
    "task_id",
    "repetition",
    "coder_model",
    "reviewer_model",
    "feedback_mode",
    "stop_policy",
    "max_rounds",
    "rounds_used",
    "stop_reason",
    "final_reviewer_approved",
    "final_reviewer_score",
    "final_syntax_ok",
    "evaluator",
    "evaluator_passed",
    "evaluator_score",
    "evaluator_elapsed_s",
    "total_tokens",
    "total_prompt_tokens",
    "total_output_tokens",
    "total_wallclock_s",
    "total_load_duration_s",
    "total_model_execution_s",
    "coder_tokens",
    "reviewer_tokens",
    "coder_wallclock_s",
    "reviewer_wallclock_s",
    "coder_load_duration_s",
    "reviewer_load_duration_s",
    "code_changed_rounds",
    "unchanged_rounds",
    "stagnation_detected",
    "critical_issues_total",
    "suggestions_total",
    "final_code_chars",
    "final_code_lines",
    "final_code_file",
    "history_file",
]

AGENT_CALL_FIELDS = list(AgentCallRecord.__dataclass_fields__.keys())


def _sum_calls(calls: list[AgentCallRecord], role: str | None, attr: str) -> float:
    return sum(float(getattr(call, attr) or 0) for call in calls if role is None or call.agent_role == role)


def summary_row(result: LoopRunResult) -> dict[str, Any]:
    review = result.final_review or {}
    critical_total = 0
    suggestions_total = 0
    for item in result.history:
        item_review = item.get("review") or {}
        critical_total += len(item_review.get("critical_issues", []) or [])
        suggestions_total += len(item_review.get("suggestions", []) or [])

    calls = result.agent_calls
    return {
        "run_id": result.run_id,
        "timestamp": result.timestamp,
        "experiment_id": result.experiment.experiment_id,
        "task_provider": result.task.source,
        "task_id": result.task.task_id,
        "repetition": result.repetition,
        "coder_model": result.experiment.coder.model,
        "reviewer_model": result.experiment.reviewer.model if result.experiment.reviewer else "",
        "feedback_mode": result.experiment.feedback_mode,
        "stop_policy": result.experiment.stop_policy,
        "max_rounds": result.experiment.max_rounds,
        "rounds_used": result.rounds_used,
        "stop_reason": result.stop_reason,
        "final_reviewer_approved": review.get("approved"),
        "final_reviewer_score": review.get("score"),
        "final_syntax_ok": result.final_syntax_ok,
        "evaluator": result.evaluation.name,
        "evaluator_passed": result.evaluation.passed,
        "evaluator_score": result.evaluation.score,
        "evaluator_elapsed_s": result.evaluation.elapsed_s,
        "total_tokens": _sum_calls(calls, None, "used_tokens"),
        "total_prompt_tokens": _sum_calls(calls, None, "prompt_tokens"),
        "total_output_tokens": _sum_calls(calls, None, "output_tokens"),
        "total_wallclock_s": result.wallclock_total_s,
        "total_load_duration_s": _sum_calls(calls, None, "load_duration_s"),
        "total_model_execution_s": _sum_calls(calls, None, "prompt_eval_duration_s") + _sum_calls(calls, None, "eval_duration_s"),
        "coder_tokens": _sum_calls(calls, "Coder", "used_tokens"),
        "reviewer_tokens": _sum_calls(calls, "Reviewer", "used_tokens"),
        "coder_wallclock_s": _sum_calls(calls, "Coder", "wallclock_s"),
        "reviewer_wallclock_s": _sum_calls(calls, "Reviewer", "wallclock_s"),
        "coder_load_duration_s": _sum_calls(calls, "Coder", "load_duration_s"),
        "reviewer_load_duration_s": _sum_calls(calls, "Reviewer", "load_duration_s"),
        "code_changed_rounds": result.code_changed_rounds,
        "unchanged_rounds": result.unchanged_rounds,
        "stagnation_detected": result.stagnation_detected,
        "critical_issues_total": critical_total,
        "suggestions_total": suggestions_total,
        "final_code_chars": len(result.final_code),
        "final_code_lines": len(result.final_code.splitlines()),
        "final_code_file": result.final_code_file,
        "history_file": result.history_file,
    }


class ResultsWriter:
    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.artifacts_dir = self.output_dir / "artifacts"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.summary_path = self.output_dir / "summary.csv"
        self.agent_calls_path = self.output_dir / "agent_calls.csv"
        self._summary_initialized = False
        self._agent_calls_initialized = False

    def _append_row(self, path: Path, fields: list[str], row: dict[str, Any], initialized_attr: str) -> None:
        initialized = getattr(self, initialized_attr)
        file_exists = path.exists() and path.stat().st_size > 0
        with path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            if not initialized and not file_exists:
                writer.writeheader()
            writer.writerow(row)
        setattr(self, initialized_attr, True)

    def persist_artifacts(self, result: LoopRunResult) -> LoopRunResult:
        safe_task_id = result.task.task_id.replace("/", "_").replace(" ", "_")
        prefix = f"{result.run_id}__{result.experiment.experiment_id}__{safe_task_id}__rep{result.repetition}"
        code_path = self.artifacts_dir / f"{prefix}.py"
        history_path = self.artifacts_dir / f"{prefix}.history.json"
        code_path.write_text(result.final_code, encoding="utf-8")
        history_path.write_text(json.dumps(result.history, ensure_ascii=False, indent=2), encoding="utf-8")
        result.final_code_file = str(code_path)
        result.history_file = str(history_path)
        return result

    def write_result(self, result: LoopRunResult) -> None:
        result = self.persist_artifacts(result)
        self._append_row(self.summary_path, SUMMARY_FIELDS, summary_row(result), "_summary_initialized")
        for call in result.agent_calls:
            self._append_row(self.agent_calls_path, AGENT_CALL_FIELDS, asdict(call), "_agent_calls_initialized")
