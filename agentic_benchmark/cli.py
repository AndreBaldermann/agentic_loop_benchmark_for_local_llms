from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

from .config_loader import load_experiment_configs, validate_experiment_configs
from .loop_runner import print_interactive_summary, run_agentic_loop
from .ollama_client import unload_agent, warm_agent
from .metrics import ResultsWriter
from .reporting.pdf import generate_overview_pdf
from .models import AgentConfig, BenchmarkTask, ExperimentConfig
from .task_providers import load_tasks

DEFAULT_CONFIG = "configs/loop_configs.csv"


def build_default_experiment() -> ExperimentConfig:
    """
    Build the default interactive benchmark configuration.

    Args:
        None.

    Returns:
        experiment, ExperimentConfig: default Coder/Reviewer setup for interactive runs.
    """
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
    """
    Run the legacy interactive single-task workflow.

    Args:
        args, argparse.Namespace: parsed CLI arguments containing output_dir and verbose.

    Returns:
        exit_code, int, 0 or 1: process-style status code.
    """
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
    """
    Validate an experiment configuration CSV from the CLI.

    Args:
        args, argparse.Namespace: parsed CLI arguments containing config path.

    Returns:
        exit_code, int, 0 or 1: 0 when the config is valid, otherwise 1.
    """
    configs = load_experiment_configs(args.config)
    errors = validate_experiment_configs(configs)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {len(configs)} experiment configuration(s) loaded from {args.config}")
    return 0


def list_tasks(args: argparse.Namespace) -> int:
    """
    Print task identifiers from a supported task provider file.

    Args:
        args, argparse.Namespace: parsed CLI arguments containing provider, tasks, limit, and task_id.

    Returns:
        exit_code, int, 0: list operation completed.
    """
    tasks = load_tasks(args.provider, args.tasks, limit=args.limit, task_id=args.task_id)
    for task in tasks:
        print(f"{task.source}\t{task.task_id}\t{task.entry_point or ''}")
    print(f"Total: {len(tasks)}")
    return 0


def prepare_load_mode(config: ExperimentConfig, warmed: set[str]) -> None:
    """
    Apply warm or cold model-loading semantics for one benchmark run.

    Args:
        config, ExperimentConfig: experiment whose Coder/Reviewer models should be prepared.
        warmed, set[str]: mutable cache of models already warmed for this process.

    Returns:
        None.
    """
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


def resolve_pdf_output_path(output_dir: Path, pdf_output: str | None) -> Path:
    """
    Resolve the PDF report output path for run --pdf-report.

    Args:
        output_dir, Path: timestamped benchmark output directory.
        pdf_output, str | None: optional user-provided PDF path or directory.

    Returns:
        output_path, Path: concrete PDF file path.
    """
    if not pdf_output:
        return output_dir / "overview.pdf"
    output_path = Path(pdf_output)
    if output_path.exists() and output_path.is_dir():
        return output_path / "overview.pdf"
    if output_path.suffix.lower() != ".pdf":
        return output_path / "overview.pdf"
    return output_path


def infer_agent_calls_path(summary_path: Path, explicit_agent_calls: str | None = None) -> Path | None:
    """
    Resolve the optional agent_calls.csv path for PDF token aggregation.

    Args:
        summary_path, Path: summary.csv path supplied to the report command.
        explicit_agent_calls, str | None: optional user-provided agent_calls.csv path.

    Returns:
        agent_calls_path, Path | None: existing agent calls path, or None when unavailable.
    """
    if explicit_agent_calls:
        return Path(explicit_agent_calls)
    candidate = summary_path.parent / "agent_calls.csv"
    if summary_path.name != "agent_calls.csv" and candidate.exists():
        return candidate
    return None


def generate_pdf_report_for_run(
    summary_path: Path,
    output_path: Path,
    title: str,
    agent_calls_path: Path | None = None,
) -> int:
    """
    Generate an overview PDF and convert rendering errors into CLI status.

    Args:
        summary_path, Path: summary.csv produced by the benchmark run.
        output_path, Path: target PDF path.
        title, str: report title printed on each page.
        agent_calls_path, Path | None: optional agent_calls.csv path for R/TCT/TRT token aggregation.

    Returns:
        exit_code, int, 0 or 1: 0 when the PDF was written, otherwise 1.
    """
    try:
        written = generate_overview_pdf(summary_path, output_path, title=title, agent_calls_path=agent_calls_path)
    except (OSError, ValueError) as exc:
        print(f"ERROR: could not generate PDF report: {exc}")
        return 1
    print(f"Wrote PDF report: {written}")
    return 0


def run_benchmark(args: argparse.Namespace) -> int:
    """
    Run the benchmark matrix for all configured experiments and selected tasks.

    Args:
        args, argparse.Namespace: parsed CLI arguments for config, tasks, filters, output, and optional PDF reporting.

    Returns:
        exit_code, int, 0 or 1: 0 on successful benchmark completion, otherwise 1.
    """
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

    if args.pdf_report:
        pdf_output = resolve_pdf_output_path(output_dir, args.pdf_output)
        return generate_pdf_report_for_run(writer.summary_path, pdf_output, args.pdf_title, writer.agent_calls_path)
    return 0


def report_pdf(args: argparse.Namespace) -> int:
    """
    Generate a PDF overview report from summary.csv.

    Args:
        args, argparse.Namespace: parsed CLI arguments containing summary, output, and title.

    Returns:
        exit_code, int, 0 or 1: 0 when the PDF was written, otherwise 1.
    """
    summary_path = Path(args.summary)
    output_path = Path(args.output)
    if output_path.is_dir():
        output_path = output_path / "overview.pdf"
    agent_calls_path = infer_agent_calls_path(summary_path, args.agent_calls)
    return generate_pdf_report_for_run(summary_path, output_path, args.title, agent_calls_path)


def write_sample_config(args: argparse.Namespace) -> int:
    """
    Write a starter experiment configuration CSV.

    Args:
        args, argparse.Namespace: parsed CLI arguments containing destination path.

    Returns:
        exit_code, int, 0: sample config was written.
    """
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
    """
    Construct the command-line parser and all subcommands.

    Args:
        None.

    Returns:
        parser, argparse.ArgumentParser: parser for interactive, run, report, validation, task listing, and sample config commands.
    """
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
    run_parser.add_argument(
        "--pdf-report",
        action="store_true",
        help="Generate overview.pdf from this run's summary.csv after the benchmark completes.",
    )
    run_parser.add_argument(
        "--pdf-output",
        help="Optional PDF path or directory for --pdf-report; defaults to the run output directory.",
    )
    run_parser.add_argument(
        "--pdf-title",
        default="Agentic Benchmark Report",
        help="Title used for --pdf-report.",
    )
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

    pdf_parser = subparsers.add_parser("report-pdf", help="Generate an overview PDF from summary.csv.")
    pdf_parser.add_argument("--summary", required=True, help="Path to summary.csv from a benchmark run.")
    pdf_parser.add_argument("--output", required=True, help="Destination PDF path or existing output directory.")
    pdf_parser.add_argument("--agent-calls", help="Optional agent_calls.csv path for Coder/Reviewer token columns; inferred next to summary.csv when present.")
    pdf_parser.add_argument("--title", default="Agentic Benchmark Report")
    pdf_parser.set_defaults(func=report_pdf)

    sample_parser = subparsers.add_parser("write-sample-config", help="Write an example loop configuration CSV.")
    sample_parser.add_argument("--path", default=DEFAULT_CONFIG)
    sample_parser.set_defaults(func=write_sample_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    """
    CLI entry point used by both module execution and the compatibility script.

    Args:
        argv, list[str] | None: optional argument vector; None reads from sys.argv.

    Returns:
        exit_code, int, 0 or 1: process-style status code returned by the selected command.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        args = parser.parse_args(["interactive"] if argv is None else [*argv, "interactive"])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
