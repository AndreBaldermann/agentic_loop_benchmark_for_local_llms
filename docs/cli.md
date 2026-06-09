# CLI Reference

This project exposes its command line interface through:

```bash
python3 -m agentic_benchmark.cli <command> [options]
```

For backwards compatibility, the legacy entrypoint still works:

```bash
python3 basis_agentic_coding_loop.py
```

If no subcommand is provided, the CLI defaults to `interactive` mode.

## Commands

### `interactive`

Run one user-provided task across experiment rows from the same config CSV used by structured benchmarks. The task is always treated as `task_id=interactive`/`source=interactive`; it is never loaded from HumanEval unless you explicitly use the `run` command. Task text can come from `--prompt`, `--prompt-file`, piped stdin, or a multi-line terminal prompt.

```bash
python3 -m agentic_benchmark.cli interactive \
  --config configs/loop_configs.csv \
  --prompt "Write a function that adds two numbers." \
  --output-dir results \
  --pdf-report \
  --verbose

# Backwards-compatible default: no subcommand also means interactive.
python3 basis_agentic_coding_loop.py \
  --config configs/loop_configs.csv \
  --prompt "Write a function that adds two numbers." \
  --pdf-report
```

If `--experiment-id` is omitted, every row from `--config` is run against the same prompt. Add `--experiment-id qwen_self_review` only when you want to try one row. This is the easiest way to try arbitrary prompts with arbitrary Coder/Reviewer combinations before learning the structured `run` command.

Options:

| Option | Default | Meaning |
|---|---:|---|
| `--config` | `configs/loop_configs.csv` | Experiment configuration CSV used to choose Coder/Reviewer settings. |
| `--experiment-id` | all config rows | Optional experiment row filter. |
| `--output-dir` | `results` | Base directory for generated result folders. |
| `--verbose` | `false` | Print prompts and verbose loop details. |
| `--prompt` | none | Inline task text for non-interactive usage. |
| `--prompt-file` | none | Text file containing the task, useful for multi-line prompts. |
| `--pdf-report` | `false` | Generate `overview.pdf` from this interactive run's `summary.csv` after all config rows complete. |
| `--pdf-output` | `reports/<interactive-run>/overview.pdf` | Optional PDF path or directory for `--pdf-report`. |
| `--pdf-title` | `Agentic Benchmark Report` | Title used in the generated PDF report. |
| `--pdf-transpose` | `false` | Swap task and experiment axes in the generated PDF report. |

### `run`

Run the benchmark matrix over all experiment rows in a CSV config and all selected tasks from a task provider file.

```bash
python3 -m agentic_benchmark.cli run \
  --config configs/loop_configs.csv \
  --tasks data/humaneval/HumanEval.jsonl.gz \
  --limit 10 \
  --pdf-report
```

Options:

| Option | Default | Meaning |
|---|---:|---|
| `--config` | `configs/loop_configs.csv` | Experiment configuration CSV. |
| `--tasks` | required | HumanEval JSONL/GZ or CSV task file. |
| `--output-dir` | `results` | Base directory for timestamped benchmark output. |
| `--limit` | none | Run only the first N loaded tasks. |
| `--task-id` | none | Run only the task with this exact ID. |
| `--verbose` | `false` | Print prompts and verbose loop details. |
| `--copy-config` | `true` | Copy the config CSV into the result directory. |
| `--no-copy-config` | `false` | Disable config snapshot copying. |
| `--pdf-report` | `false` | Generate `overview.pdf` from this run's `summary.csv` after the benchmark completes. |
| `--pdf-output` | `reports/<run>/overview.pdf` | Optional PDF path or directory for `--pdf-report`. |
| `--pdf-title` | `Agentic Benchmark Report` | Title used in the generated PDF report. |
| `--pdf-transpose` | `false` | Swap task and experiment axes in the generated PDF report. |
| `--provider` | `humaneval` | Deprecated; task provider is read from config rows. |

Output:

- `summary.csv`: one row per task/configuration/repetition.
- `agent_calls.csv`: one row per concrete Coder or Reviewer model call.
- `artifacts/`: generated code and JSON history files.
- a snapshot copy of the config CSV when `--copy-config` is enabled.
- `reports/<run>/overview.pdf` when `--pdf-report` is used without `--pdf-output`.

### `validate-config`

Validate an experiment configuration CSV without running any model calls.

```bash
python3 -m agentic_benchmark.cli validate-config --config configs/loop_configs.csv
```

Options:

| Option | Default | Meaning |
|---|---:|---|
| `--config` | `configs/loop_configs.csv` | Config file to validate. |

### `list-tasks`

List tasks from a task provider file.

```bash
python3 -m agentic_benchmark.cli list-tasks \
  --provider humaneval \
  --tasks data/humaneval/HumanEval.jsonl.gz \
  --limit 5
```

Options:

| Option | Default | Meaning |
|---|---:|---|
| `--provider` | `humaneval` | Task provider type: `humaneval` or `csv`. |
| `--tasks` | required | Task file to inspect. |
| `--limit` | none | Print only the first N tasks. |
| `--task-id` | none | Print only the task with this exact ID. |

### `report-pdf`

Generate an overview PDF from a benchmark `summary.csv`. Rows are `task_id` and columns are `experiment_id` by default; use `--transpose` to swap the axes when there are many task or experiment columns. The report contains several matrices with the same layout: `R/TCT/TRT` for rounds and generated tokens, `TTNL/TTC/TTR` for execution time without model loading, `TTL/TLC/TLR` for load time, `ATPS/CTPS/RTPS` for generated-token throughput, `FC/TO/ERR` for failures, `SYN/APP/EVAL` for quality signals, and `Q/QPS/QPK` for simple efficiency views. Reports automatically choose A3/A2/A1/A0 landscape for increasingly wide column counts.

```bash
python3 -m agentic_benchmark.cli report-pdf \
  --summary results/run_20260607_120000/summary.csv \
  --agent-calls results/run_20260607_120000/agent_calls.csv \
  --output reports/run_20260607_120000/overview.pdf
```

Options:

| Option | Default | Meaning |
|---|---:|---|
| `--summary` | required | Path to `summary.csv` from a benchmark run. |
| `--output` | required | Destination PDF path, or an existing directory where `overview.pdf` is written. |
| `--agent-calls` | inferred next to `summary.csv` | Optional `agent_calls.csv` path used to aggregate token, timing, loading, throughput, reliability, and quality columns. |
| `--title` | `Agentic Benchmark Report` | Title printed on the PDF pages. |
| `--transpose` | `false` | Swap task and experiment axes in the generated PDF report. |

Generate the same PDF directly during an interactive prompt run:

```bash
python3 -m agentic_benchmark.cli \
  --prompt "write a function that adds 2 numbers in python" \
  --pdf-report
```

Generate the same PDF directly during a structured benchmark run:

```bash
python3 -m agentic_benchmark.cli run \
  --config configs/loop_configs.csv \
  --tasks HumanEval.jsonl.gz \
  --limit 1 \
  --pdf-report \
  --pdf-transpose
```

Color rules:

- `R` with `rounds_used = 1`: green.
- Intermediate `R`: interpolated between green and red.
- `R` with `rounds_used = max_rounds`: red, unless overridden by a stop reason below.
- `stagnation_detected`: gray.
- `max_rounds_reached`: blue.
- `TCT` and `TRT`: minimum positive token total is green and maximum positive token total is red.
- `TCT` or `TRT` with `0` tokens: blue, which highlights timeouts, failures, or disabled roles.
- `TTNL`, `TTC`, and `TTR`: minimum positive execution time is green and maximum positive execution time is red.
- `TTNL`, `TTC`, or `TTR` with `0` seconds: blue, which highlights missing timing data, failures, or disabled roles.
- `TTL`, `TLC`, and `TLR`: minimum positive loading time is green and maximum positive loading time is red; `0` seconds is blue.
- `ATPS`, `CTPS`, and `RTPS`: highest throughput is green, lowest positive throughput is red, and `0` is blue.
- `FC`, `TO`, and `ERR`: zero failures is green; larger failure, timeout, or distinct-error counts move toward red.
- `SYN`, `APP`, and `EVAL`: higher quality rates are greener; missing values are gray.
- `Q`, `QPS`, and `QPK`: higher simple quality/efficiency scores are greener; missing quality is gray and zero efficiency is blue.

### `write-sample-config`

Write an example experiment configuration CSV.

```bash
python3 -m agentic_benchmark.cli write-sample-config --path configs/loop_configs.csv
```

Options:

| Option | Default | Meaning |
|---|---:|---|
| `--path` | `configs/loop_configs.csv` | Destination path for the sample config. |

## Configuration CSV

The CSV config is the main benchmark control surface. It defines Coder and Reviewer models, context windows, per-role timeouts, generation limits, temperatures, max loop rounds, feedback behavior, stop policy, load mode, repetitions, and evaluator.

The repository includes a starter config at `configs/loop_configs.csv`.

## Help smoke tests

The test suite contains small CLI help tests that guard the documented command surface from accidental drift. Run them with:

```bash
python3 -m unittest discover -s tests
```
