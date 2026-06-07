# agentic_loop_benchmark_for_local_llms

A local benchmark runner for comparing agentic Coder/Reviewer loop configurations across interchangeable task providers such as HumanEval-style JSONL files.

## Modes

### Interactive compatibility mode

```bash
python3 basis_agentic_coding_loop.py

# Non-interactive task text also works and does not load HumanEval:
python3 basis_agentic_coding_loop.py --prompt "Write a function that adds two numbers."
```

### Validate loop configurations

```bash
python3 -m agentic_benchmark.cli validate-config --config configs/loop_configs.csv
```

### Run a benchmark

```bash
python3 -m agentic_benchmark.cli run \
  --config configs/loop_configs.csv \
  --tasks data/humaneval/HumanEval.jsonl.gz \
  --limit 10 \
  --pdf-report
```

The benchmark writes a timestamped result directory containing:

- `summary.csv`: one row per task/configuration/repetition
- `agent_calls.csv`: one row per concrete Coder or Reviewer model call
- `artifacts/`: final generated code and per-run JSON history

### Generate overview PDF

```bash
python3 -m agentic_benchmark.cli report-pdf \
  --summary results/run_YYYYMMDD_HHMMSS/summary.csv \
  --agent-calls results/run_YYYYMMDD_HHMMSS/agent_calls.csv \
  --output reports/overview.pdf

# Or generate overview.pdf directly after a benchmark run:
python3 -m agentic_benchmark.cli run \
  --config configs/loop_configs.csv \
  --tasks HumanEval.jsonl.gz \
  --limit 1 \
  --pdf-report
```

The PDF overview subdivides every task/experiment cell into `R` (rounds/max rounds), `TCT` (total generated Coder tokens), and `TRT` (total generated Reviewer tokens).

## CLI reference

See [docs/cli.md](docs/cli.md) for the full command reference, option descriptions, examples, and the CLI help smoke-test command.

## Configuration CSV

`configs/loop_configs.csv` defines Coder/Reviewer model pairs, context sizes, per-role timeouts, temperatures, max rounds, feedback mode, stop policy, load mode, repetitions, and evaluator.

Reviewer models are optional, so Coder-only loops can be compared against Coder/Reviewer loops.

## Evaluators

The benchmark focuses on agentic-loop behavior, timing, tokens, and interaction metrics. Evaluators are optional and configurable per row:

- `none`: do not evaluate generated code
- `syntax`: run a local Python syntax check
- `humaneval`: run HumanEval tests in a subprocess with timeout


## Failure handling and fair loading

For fair per-task comparisons the sample config uses `load_mode=cold`, which unloads Coder and Reviewer models before each task/repetition. Within a task, the loop can still run multiple Coder/Reviewer iterations using the configured context windows.

Model call failures, including Ollama URL errors, invalid JSON, backend errors, and timeouts, are recorded as failed agent calls instead of aborting the whole benchmark. Failed calls get zero backend token counts and zero backend execution/load durations, plus `call_failed`, `error_type`, and `error_message` fields in `agent_calls.csv`.
