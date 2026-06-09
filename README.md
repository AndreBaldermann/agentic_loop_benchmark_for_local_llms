# agentic_loop_benchmark_for_local_llms

A beginner-friendly local tool for trying and benchmarking **agentic Coder/Reviewer loops** with local Ollama models.

The easiest entry point is **interactive mode**: write any programming task and run every Coder/Reviewer setup listed in `configs/loop_configs.csv` on that same prompt. When you want repeatable structured experiments later, use `run` with a task file such as HumanEval.

## 1. First run: interactive mode

Use this first. You do **not** need a HumanEval file and you do **not** need to understand the benchmark runner yet. Interactive mode reads the same config CSV as the benchmark runner, so you can test any prompt against all Coder/Reviewer combinations listed in `configs/loop_configs.csv`.

Very small checklist:

1. Download or clone this repository.
2. Open a terminal in this folder.
3. Make sure Ollama is running and the model names in `configs/loop_configs.csv` exist locally.
4. Run one of the commands below.

```bash
python3 basis_agentic_coding_loop.py \
  --config configs/loop_configs.csv \
  --prompt "Write a Python function add_two(x) that returns x + 2." \
  --pdf-report
```

That runs the prompt once for every row in `configs/loop_configs.csv`, writes CSV/artifacts under `results/interactive_YYYYMMDD_HHMMSS/`, copies the config CSV into that result folder, and writes the PDF overview under `reports/interactive_YYYYMMDD_HHMMSS/overview.pdf`. The equivalent module command also works without explicitly writing `interactive`:

```bash
python3 -m agentic_benchmark.cli \
  --config configs/loop_configs.csv \
  --prompt "Write a Python function add_two(x) that returns x + 2." \
  --pdf-report
```

If you only want to try one row, add `--experiment-id`:

```bash
python3 basis_agentic_coding_loop.py \
  --config configs/loop_configs.csv \
  --experiment-id qwen_self_review \
  --prompt "Write a Python function add_two(x) that returns x + 2."
```

For longer prompts, write the task into a text file and pass it in:

```bash
python3 basis_agentic_coding_loop.py \
  --config configs/loop_configs.csv \
  --prompt-file my_task.txt
```

You can see or edit available agent combinations here:

```bash
configs/loop_configs.csv
```

Important columns in that CSV:

- `experiment_id`: the short name you can optionally pass to `--experiment-id`
- `coder_model`: Ollama model used as the Coder
- `reviewer_model`: Ollama model used as the Reviewer; leave empty for Coder-only runs
- `max_rounds`: maximum Coder/Reviewer loop iterations
- `feedback_mode`, `stop_policy`, `evaluator`: loop behavior

Interactive results are written to `results/interactive_YYYYMMDD_HHMMSS/` and include generated code, history, `summary.csv`, `agent_calls.csv`, and a copy of the config CSV. When `--pdf-report` is used, the overview PDF is written to the matching `reports/interactive_YYYYMMDD_HHMMSS/` directory.

## 2. Validate loop configurations

Before running many experiments, check that the CSV is valid:

```bash
python3 -m agentic_benchmark.cli validate-config --config configs/loop_configs.csv
```

## 3. Structured benchmark run

Use this when you want repeatable tests over a task corpus such as HumanEval:

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
- a snapshot copy of the config CSV
- `reports/run_YYYYMMDD_HHMMSS/overview.pdf` when `--pdf-report` is used

## 4. Generate overview PDF later

```bash
python3 -m agentic_benchmark.cli report-pdf \
  --summary results/run_YYYYMMDD_HHMMSS/summary.csv \
  --agent-calls results/run_YYYYMMDD_HHMMSS/agent_calls.csv \
  --output reports/overview.pdf
```

The PDF overview contains multiple matrix tables with the same task/experiment layout: `R/TCT/TRT` for rounds and generated tokens, `TTNL/TTC/TTR` for execution time without model loading, `TTL/TLC/TLR` for load time, `ATPS/CTPS/RTPS` for generated-token throughput, `FC/TO/ERR` for failures, `SYN/APP/EVAL` for quality signals, and `Q/QPS/QPK` for simple efficiency views. Use `--pdf-transpose` or `report-pdf --transpose` to swap tasks and experiments. Wide reports automatically switch from A4 landscape to A3/A2/A1/A0 as the number of visible columns grows.

## CLI reference

See [docs/cli.md](docs/cli.md) for the full command reference, option descriptions, examples, and the CLI help smoke-test command.

## Evaluators

The benchmark focuses on agentic-loop behavior, timing, tokens, and interaction metrics. Evaluators are optional and configurable per row:

- `none`: do not evaluate generated code
- `syntax`: run a local Python syntax check
- `humaneval`: run HumanEval tests in a subprocess with timeout

## Failure handling and fair loading

For fair per-task comparisons the sample config uses `load_mode=cold`, which unloads Coder and Reviewer models before each task/repetition. Within a task, the loop can still run multiple Coder/Reviewer iterations using the configured context windows.

Model call failures, including Ollama URL errors, invalid JSON, backend errors, and timeouts, are recorded as failed agent calls instead of aborting the whole benchmark. Failed calls get zero backend token counts and zero backend execution/load durations, plus `call_failed`, `error_type`, and `error_message` fields in `agent_calls.csv`.
