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

Run the legacy single-task Coder/Reviewer loop. The task is read from stdin and results are written to a timestamped directory.

```bash
python3 -m agentic_benchmark.cli interactive --output-dir results --verbose
```

Options:

| Option | Default | Meaning |
|---|---:|---|
| `--output-dir` | `results` | Base directory for generated result folders. |
| `--verbose` | `false` | Print prompts and verbose loop details. |

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
| `--pdf-output` | run output directory | Optional PDF path or directory for `--pdf-report`. |
| `--pdf-title` | `Agentic Benchmark Report` | Title used in the generated PDF report. |
| `--provider` | `humaneval` | Deprecated; task provider is read from config rows. |

Output:

- `summary.csv`: one row per task/configuration/repetition.
- `agent_calls.csv`: one row per concrete Coder or Reviewer model call.
- `artifacts/`: generated code and JSON history files.

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

Generate a first overview PDF from a benchmark `summary.csv`. Rows are `task_id`, columns are `experiment_id`, and each cell shows `rounds_used / max_rounds`.

```bash
python3 -m agentic_benchmark.cli report-pdf \
  --summary results/run_20260607_120000/summary.csv \
  --output reports/run_20260607_120000/overview.pdf
```

Options:

| Option | Default | Meaning |
|---|---:|---|
| `--summary` | required | Path to `summary.csv` from a benchmark run. |
| `--output` | required | Destination PDF path, or an existing directory where `overview.pdf` is written. |
| `--title` | `Agentic Benchmark Report` | Title printed on the PDF pages. |

Generate the same PDF directly during a benchmark run:

```bash
python3 -m agentic_benchmark.cli run \
  --config configs/loop_configs.csv \
  --tasks HumanEval.jsonl.gz \
  --limit 1 \
  --pdf-report
```

Color rules:

- `rounds_used = 1`: green.
- Intermediate `rounds_used`: interpolated between green and red.
- `rounds_used = max_rounds`: red, unless overridden by a stop reason below.
- `stagnation_detected`: gray.
- `max_rounds_reached`: blue.

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
