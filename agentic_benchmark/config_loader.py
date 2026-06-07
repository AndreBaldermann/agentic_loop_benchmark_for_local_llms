from __future__ import annotations

import csv
from pathlib import Path

from .models import AgentConfig, ExperimentConfig


def _required(row: dict[str, str], key: str) -> str:
    value = (row.get(key) or "").strip()
    if not value:
        raise ValueError(f"Missing required config value: {key}")
    return value


def _int(row: dict[str, str], key: str, default: int = 0) -> int:
    value = (row.get(key) or "").strip()
    return int(value) if value else default


def _float(row: dict[str, str], key: str, default: float = 0.0) -> float:
    value = (row.get(key) or "").strip()
    return float(value) if value else default


def load_experiment_configs(path: str | Path) -> list[ExperimentConfig]:
    configs: list[ExperimentConfig] = []
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            keep_alive = (row.get("keep_alive") or "10m").strip()
            coder = AgentConfig(
                role="Coder",
                model=_required(row, "coder_model"),
                num_ctx=_int(row, "coder_ctx", 32768),
                temperature=_float(row, "coder_temperature", 0.1),
                num_predict=_int(row, "coder_num_predict", 4096),
                json_mode=False,
                keep_alive=keep_alive,
                timeout_seconds=_int(row, "coder_timeout_seconds", 600),
            )
            reviewer_model = (row.get("reviewer_model") or "").strip()
            reviewer = None
            if reviewer_model:
                reviewer = AgentConfig(
                    role="Reviewer",
                    model=reviewer_model,
                    num_ctx=_int(row, "reviewer_ctx", 16384),
                    temperature=_float(row, "reviewer_temperature", 0.0),
                    num_predict=_int(row, "reviewer_num_predict", 2048),
                    json_mode=True,
                    keep_alive=keep_alive,
                    timeout_seconds=_int(row, "reviewer_timeout_seconds", 600),
                )
            configs.append(
                ExperimentConfig(
                    experiment_id=_required(row, "experiment_id"),
                    task_provider=(row.get("task_provider") or "humaneval").strip(),
                    coder=coder,
                    reviewer=reviewer,
                    max_rounds=_int(row, "max_rounds", 5),
                    max_same_code_rounds=_int(row, "max_same_code_rounds", 2),
                    feedback_mode=(row.get("feedback_mode") or "compact_json").strip(),
                    stop_policy=(row.get("stop_policy") or "reviewer_approved_and_syntax_ok").strip(),
                    coder_prompt_template=(row.get("coder_prompt_template") or "coder_default").strip(),
                    reviewer_prompt_template=(row.get("reviewer_prompt_template") or "reviewer_default").strip(),
                    load_mode=(row.get("load_mode") or "as_is").strip(),
                    repetitions=_int(row, "repetitions", 1),
                    evaluator=(row.get("evaluator") or "syntax").strip(),
                )
            )
    return configs


def validate_experiment_configs(configs: list[ExperimentConfig]) -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()
    valid_feedback = {"none", "compact_json", "full_json", "critical_only", "suggestions_only"}
    valid_stop = {
        "single_coder_round",
        "reviewer_approved",
        "reviewer_approved_and_syntax_ok",
        "stagnation_or_approved",
        "max_rounds_only",
        "fixed_rounds",
    }
    valid_eval = {"none", "syntax", "humaneval"}
    valid_load = {"as_is", "warm", "cold"}
    for config in configs:
        if config.experiment_id in ids:
            errors.append(f"Duplicate experiment_id: {config.experiment_id}")
        ids.add(config.experiment_id)
        if config.max_rounds < 1:
            errors.append(f"{config.experiment_id}: max_rounds must be >= 1")
        if config.repetitions < 1:
            errors.append(f"{config.experiment_id}: repetitions must be >= 1")
        if config.coder.timeout_seconds < 1:
            errors.append(f"{config.experiment_id}: coder_timeout_seconds must be >= 1")
        if config.reviewer and config.reviewer.timeout_seconds < 1:
            errors.append(f"{config.experiment_id}: reviewer_timeout_seconds must be >= 1")
        if config.feedback_mode not in valid_feedback:
            errors.append(f"{config.experiment_id}: unsupported feedback_mode {config.feedback_mode}")
        if config.stop_policy not in valid_stop:
            errors.append(f"{config.experiment_id}: unsupported stop_policy {config.stop_policy}")
        if config.evaluator not in valid_eval:
            errors.append(f"{config.experiment_id}: unsupported evaluator {config.evaluator}")
        if config.load_mode not in valid_load:
            errors.append(f"{config.experiment_id}: unsupported load_mode {config.load_mode}")
        if config.stop_policy.startswith("reviewer") and config.reviewer is None:
            errors.append(f"{config.experiment_id}: reviewer stop_policy requires reviewer_model")
    return errors
