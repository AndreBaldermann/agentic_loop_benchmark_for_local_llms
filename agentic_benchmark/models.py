from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for a single Ollama-backed agent role."""

    role: str
    model: str
    num_ctx: int
    temperature: float
    num_predict: int
    json_mode: bool = False
    keep_alive: str = "10m"
    timeout_seconds: int = 600


@dataclass(frozen=True)
class ExperimentConfig:
    """Configuration for a complete agentic loop experiment."""

    experiment_id: str
    task_provider: str
    coder: AgentConfig
    reviewer: AgentConfig | None
    max_rounds: int = 5
    max_same_code_rounds: int = 2
    feedback_mode: str = "compact_json"
    stop_policy: str = "reviewer_approved_and_syntax_ok"
    coder_prompt_template: str = "coder_default"
    reviewer_prompt_template: str = "reviewer_default"
    load_mode: str = "as_is"
    repetitions: int = 1
    evaluator: str = "syntax"


@dataclass(frozen=True)
class BenchmarkTask:
    """A task from an interchangeable benchmark provider."""

    task_id: str
    source: str
    prompt: str
    metadata: dict[str, Any] = field(default_factory=dict)
    test: str | None = None
    entry_point: str | None = None
    canonical_solution: str | None = None


@dataclass(frozen=True)
class ModelCallResult:
    """Normalized response and metrics for a single model call."""

    output: str
    wallclock_s: float
    chars: int
    words: int
    prompt_estimated_tokens: int
    num_ctx: int
    num_predict: int
    json_mode: bool
    model: str
    role: str
    total_duration_s: float = 0.0
    load_duration_s: float = 0.0
    prompt_eval_count: int = 0
    prompt_eval_duration_s: float = 0.0
    eval_count: int = 0
    eval_duration_s: float = 0.0
    failed: bool = False
    error_type: str | None = None
    error_message: str | None = None

    @property
    def prompt_tokens(self) -> int:
        if self.failed:
            return 0
        return self.prompt_eval_count or self.prompt_estimated_tokens

    @property
    def output_tokens(self) -> int:
        if self.failed:
            return 0
        return self.eval_count

    @property
    def used_tokens(self) -> int:
        return self.prompt_tokens + self.output_tokens

    @property
    def model_execution_s(self) -> float:
        return self.prompt_eval_duration_s + self.eval_duration_s


@dataclass(frozen=True)
class EvaluationResult:
    """Optional evaluator result for a generated artifact."""

    enabled: bool
    name: str
    passed: bool | None
    score: float | None = None
    elapsed_s: float = 0.0
    error_type: str | None = None
    error_message: str | None = None
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class AgentCallRecord:
    """CSV-friendly record for one concrete agent call."""

    run_id: str
    experiment_id: str
    task_provider: str
    task_id: str
    repetition: int
    round_no: int
    agent_role: str
    agent_model: str
    num_ctx: int
    temperature: float
    num_predict: int
    json_mode: bool
    prompt_chars: int
    output_chars: int
    prompt_tokens: int
    output_tokens: int
    used_tokens: int
    wallclock_s: float
    total_duration_s: float
    load_duration_s: float
    prompt_eval_duration_s: float
    eval_duration_s: float
    feedback_mode: str
    stop_policy: str
    syntax_ok_after_coder: bool | None = None
    code_changed: bool | None = None
    reviewer_approved: bool | None = None
    reviewer_score: int | None = None
    critical_issues_count: int | None = None
    suggestions_count: int | None = None
    stop_reason_if_any: str | None = None
    call_failed: bool = False
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class LoopRunResult:
    """Final result and telemetry for one task/config/repetition run."""

    run_id: str
    timestamp: str
    experiment: ExperimentConfig
    task: BenchmarkTask
    repetition: int
    rounds_used: int
    stop_reason: str
    final_code: str
    final_syntax_ok: bool
    final_syntax_error: str
    final_review: dict[str, Any] | None
    evaluation: EvaluationResult
    agent_calls: list[AgentCallRecord]
    history: list[dict[str, Any]]
    wallclock_total_s: float
    code_changed_rounds: int
    unchanged_rounds: int
    stagnation_detected: bool
    final_code_file: str = ""
    history_file: str = ""
