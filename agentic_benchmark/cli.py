from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from .config_loader import load_experiment_configs, validate_experiment_configs
from .loop_runner import print_interactive_summary, run_agentic_loop
from .ollama_client import unload_agent, warm_agent
from .metrics import ResultsWriter
from .models import AgentConfig, BenchmarkTask, ExperimentConfig
from .task_providers import load_tasks

DEFAULT_CONFIG = "configs/loop_configs.csv"


def build_default_experiment() -> ExperimentConfig:
    coder = AgentConfig(
        role="Coder",
        model="qwen3-coder-next:latest",
        num_ctx=32768,
        temperature=0.1,
        num_predict=4096,
    )
    reviewer = AgentConfig(
        role="Reviewer",
        model="qwen3-coder-next:latest",
        num_ctx=16384,
        temperature=0.0,
        num_predict=2048,
        json_mode=True,
    )
    return ExperimentConfig(
        experiment_id="interactive_default",
        task_provider="interactive",
        coder=coder,
        reviewer=reviewer,
        max_rounds=50,
        max_same_code_rounds=2,
        feedback_mode="compact_json",
        stop_policy="reviewer_approved_and_syntax_ok",
        evaluator="syntax",
    )


def interactive(args: argparse.Namespace) -> int:
    task_text = input("\nAufgabe für die Agenten:\n> ").strip()
    task = BenchmarkTask(task_id="interactive", source="interactive", prompt=task_text)
    result = run_agentic_loop(task, build_default_experiment(), verbose=args.verbose)
    output_dir = Path(args.output_dir) / datetime.now().strftime("interactive_%Y%m%d_%H%M%S")
    writer = ResultsWriter(output_dir)
    writer.write_result(result)
    print_interactive_summary(result)
    print(f"\nFinaler Code gespeichert in:\n{result.final_code_file}")
    print(f"\nHistorie gespeichert in:\n{result.history_file}")
    print(f"\nSummary CSV:\n{writer.summary_path}")
    print(f"\nAgent Calls CSV:\n{writer.agent_calls_path}")
    return 0


def validate_config(args: argparse.Namespace) -> int:
    configs = load_experiment_configs(args.config)
    errors = validate_experiment_configs(configs)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {len(configs)} experiment configuration(s) loaded from {args.config}")
    return 0


def list_tasks(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.provider, args.tasks, limit=args.limit, task_id=args.task_id)
    for task in tasks:
        print(f"{task.source}\t{task.task_id}\t{task.entry_point or ''}")
    print(f"Total: {len(tasks)}")
    return 0


def prepare_load_mode(config: ExperimentConfig, warmed: set[str]) -> None:
    agents = [config.coder] + ([config.reviewer] if config.reviewer else [])
    if config.load_mode == "warm":
        for agent in agents:
            key = f"{config.experiment_id}:{agent.role}:{agent.model}"
            if key not in warmed:
                print(f"Warming {agent.role} model for {config.experiment_id}: {agent.model}")
                result = warm_agent(agent)
                if result.failed:
                    print(f"WARNING: warm-up failed for {agent.role} model {agent.model}: {result.error_message}")
                warmed.add(key)
    elif config.load_mode == "cold":
        for agent in agents:
            print(f"Unloading {agent.role} model for cold run: {agent.model}")
            result = unload_agent(agent)
            if result.failed:
                print(f"WARNING: unload failed for {agent.role} model {agent.model}: {result.error_message}")


def run_benchmark(args: argparse.Namespace) -> int:
    configs = load_experiment_configs(args.config)
    errors = validate_experiment_configs(configs)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    tasks_by_provider: dict[str, list[BenchmarkTask]] = {}
    output_dir = Path(args.output_dir) / datetime.now().strftime("run_%Y%m%d_%H%M%S")
    writer = ResultsWriter(output_dir)

    if args.copy_config:
        config_snapshot = output_dir / Path(args.config).name
        config_snapshot.write_text(Path(args.config).read_text(encoding="utf-8"), encoding="utf-8")

    total_runs = 0
    warmed_models: set[str] = set()
    for config in configs:
        provider = config.task_provider
        if provider not in tasks_by_provider:
            tasks_by_provider[provider] = load_tasks(provider, args.tasks, limit=args.limit, task_id=args.task_id)
        tasks = tasks_by_provider[provider]
        for task in tasks:
            for repetition in range(1, config.repetitions + 1):
                total_runs += 1
                print(
                    f"[{total_runs}] experiment={config.experiment_id} task={task.task_id} "
                    f"rep={repetition}/{config.repetitions}"
                )
                prepare_load_mode(config, warmed_models)
                result = run_agentic_loop(task, config, repetition=repetition, verbose=args.verbose)
                writer.write_result(result)
                print(
                    f"  stop={result.stop_reason} rounds={result.rounds_used} "
                    f"syntax={result.final_syntax_ok} eval={result.evaluation.passed} "
                    f"time={result.wallclock_total_s:.2f}s"
                )

    print(f"\nWrote summary: {writer.summary_path}")
    print(f"Wrote agent calls: {writer.agent_calls_path}")
    print(f"Wrote artifacts: {writer.artifacts_dir}")
    return 0


def write_sample_config(args: argparse.Namespace) -> int:
    path = Path(args.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "experiment_id",
        "task_provider",
        "coder_model",
        "reviewer_model",
        "coder_ctx",
        "reviewer_ctx",
        "coder_num_predict",
        "reviewer_num_predict",
        "coder_timeout_seconds",
        "reviewer_timeout_seconds",
        "coder_temperature",
        "reviewer_temperature",
        "max_rounds",
        "max_same_code_rounds",
        "feedback_mode",
        "stop_policy",
        "coder_prompt_template",
        "reviewer_prompt_template",
        "keep_alive",
        "load_mode",
        "repetitions",
        "evaluator",
    ]
    rows = [
        {
            "experiment_id": "qwen_self_review",
            "task_provider": "humaneval",
            "coder_model": "qwen3-coder-next:latest",
            "reviewer_model": "qwen3-coder-next:latest",
            "coder_ctx": "32768",
            "reviewer_ctx": "16384",
            "coder_num_predict": "4096",
            "reviewer_num_predict": "2048",
            "coder_timeout_seconds": "600",
            "reviewer_timeout_seconds": "600",
            "coder_temperature": "0.1",
            "reviewer_temperature": "0.0",
            "max_rounds": "5",
            "max_same_code_rounds": "2",
            "feedback_mode": "compact_json",
            "stop_policy": "reviewer_approved_and_syntax_ok",
            "coder_prompt_template": "coder_default",
            "reviewer_prompt_template": "reviewer_default",
            "keep_alive": "10m",
            "load_mode": "cold",
            "repetitions": "1",
            "evaluator": "syntax",
        },
        {
            "experiment_id": "qwen_no_review",
            "task_provider": "humaneval",
            "coder_model": "qwen3-coder-next:latest",
            "reviewer_model": "",
            "coder_ctx": "32768",
            "reviewer_ctx": "0",
            "coder_num_predict": "4096",
            "reviewer_num_predict": "0",
            "coder_timeout_seconds": "600",
            "reviewer_timeout_seconds": "600",
            "coder_temperature": "0.1",
            "reviewer_temperature": "0.0",
            "max_rounds": "1",
            "max_same_code_rounds": "1",
            "feedback_mode": "none",
            "stop_policy": "single_coder_round",
            "coder_prompt_template": "coder_default",
            "reviewer_prompt_template": "",
            "keep_alive": "10m",
            "load_mode": "cold",
            "repetitions": "1",
            "evaluator": "syntax",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote sample config to {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agentic loop benchmark runner for local LLMs.")
    subparsers = parser.add_subparsers(dest="command", required=False)

    interactive_parser = subparsers.add_parser("interactive", help="Run the legacy single-task interactive loop.")
    interactive_parser.add_argument("--output-dir", default="results")
    interactive_parser.add_argument("--verbose", action="store_true")
    interactive_parser.set_defaults(func=interactive)

    run_parser = subparsers.add_parser("run", help="Run a task-provider benchmark over all CSV configurations.")
    run_parser.add_argument("--config", default=DEFAULT_CONFIG)
    run_parser.add_argument("--provider", default="humaneval", help="Deprecated; provider is read from config rows.")
    run_parser.add_argument("--tasks", required=True, help="Path to HumanEval JSONL(.gz) or CSV task file.")
    run_parser.add_argument("--output-dir", default="results")
    run_parser.add_argument("--limit", type=int)
    run_parser.add_argument("--task-id")
    run_parser.add_argument("--verbose", action="store_true")
    run_parser.add_argument("--copy-config", action="store_true", default=True)
    run_parser.add_argument("--no-copy-config", action="store_false", dest="copy_config")
    run_parser.set_defaults(func=run_benchmark)

    validate_parser = subparsers.add_parser("validate-config", help="Validate loop configuration CSV.")
    validate_parser.add_argument("--config", default=DEFAULT_CONFIG)
    validate_parser.set_defaults(func=validate_config)

    list_parser = subparsers.add_parser("list-tasks", help="List tasks from a provider file.")
    list_parser.add_argument("--provider", default="humaneval", choices=["humaneval", "csv"])
    list_parser.add_argument("--tasks", required=True)
    list_parser.add_argument("--limit", type=int)
    list_parser.add_argument("--task-id")
    list_parser.set_defaults(func=list_tasks)

    sample_parser = subparsers.add_parser("write-sample-config", help="Write an example loop configuration CSV.")
    sample_parser.add_argument("--path", default=DEFAULT_CONFIG)
    sample_parser.set_defaults(func=write_sample_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        args = parser.parse_args(["interactive"] if argv is None else [*argv, "interactive"])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
