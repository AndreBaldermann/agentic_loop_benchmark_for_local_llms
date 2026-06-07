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
    """
    Defines one benchmark matrix row.

    The experiment combines agent settings, loop behavior, feedback strategy,
    loading mode, repetition count, and final evaluator. A benchmark run is
    the Cartesian product of ExperimentConfig rows and loaded tasks.
    """

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
    """
    Represents one benchmark task independent of its provider.

    HumanEval, CSV, and future task providers normalize their inputs into
    this class so the loop runner can stay provider-agnostic. Optional test
    fields are used only by evaluators that need them.
    """

    task_id: str
    source: str
    prompt: str
    metadata: dict[str, Any] = field(default_factory=dict)
    test: str | None = None
    entry_point: str | None = None
    canonical_solution: str | None = None


@dataclass(frozen=True)
class ModelCallResult:
    """
    Stores the normalized result of one Ollama call.

    Successful calls preserve backend timing and token metrics. Failed calls
    deliberately carry zero backend metrics and a failure flag so one bad
    model response can be recorded without aborting the full benchmark.
    """

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
        """
        Return input token count for CSV aggregation.

        Returns:
            prompt_tokens, int, >= 0: backend prompt count, fallback estimate,
            or 0 for failed calls.
        """
        if self.failed:
            return 0
        return self.prompt_eval_count or self.prompt_estimated_tokens

    @property
    def output_tokens(self) -> int:
        """
        Return output token count for CSV aggregation.

        Returns:
            output_tokens, int, >= 0: backend generation count, or 0 for
            failed calls.
        """
        if self.failed:
            return 0
        return self.eval_count

    @property
    def used_tokens(self) -> int:
        """
        Return total tokens attributed to this call.

        Returns:
            used_tokens, int, >= 0: prompt_tokens plus output_tokens.
        """
        return self.prompt_tokens + self.output_tokens

    @property
    def model_execution_s(self) -> float:
        """
        Return prompt-processing plus generation time.

        Returns:
            seconds, float, >= 0.0: prompt_eval_duration_s plus eval_duration_s.
        """
        return self.prompt_eval_duration_s + self.eval_duration_s


@dataclass(frozen=True)
class EvaluationResult:
    """
    Describes optional post-loop evaluation of final generated code.

    The benchmark focuses on loop behavior, so evaluation may be disabled.
    When enabled, this class captures pass/fail, scores, timings, and process
    output from syntax or HumanEval evaluators.
    """

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
    """
    Flattens one Coder or Reviewer call for agent_calls.csv.

    Each row records prompt/output sizes, token counts, timing data, failure
    state, and loop metadata. The invariant is one AgentCallRecord per model
    request that belongs to a measured task run.
    """

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
    """
    Aggregates the complete outcome of one task/config/repetition run.

    The result keeps final code, stop reason, optional evaluation, per-call
    records, and rich JSON history. ResultsWriter later persists this object
    into summary CSV rows and artifact files.
    """

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
