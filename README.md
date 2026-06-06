# agentic_loop_benchmark_for_local_llms

A local benchmark runner for comparing agentic Coder/Reviewer loop configurations across interchangeable task providers such as HumanEval-style JSONL files.

## Modes

### Interactive compatibility mode

```bash
python3 basis_agentic_coding_loop.py
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
  --limit 10
```

The benchmark writes a timestamped result directory containing:

- `summary.csv`: one row per task/configuration/repetition
- `agent_calls.csv`: one row per concrete Coder or Reviewer model call
- `artifacts/`: final generated code and per-run JSON history

## Configuration CSV

`configs/loop_configs.csv` defines Coder/Reviewer model pairs, context sizes, temperatures, max rounds, feedback mode, stop policy, load mode, repetitions, and evaluator.

Reviewer models are optional, so Coder-only loops can be compared against Coder/Reviewer loops.

## Evaluators

The benchmark focuses on agentic-loop behavior, timing, tokens, and interaction metrics. Evaluators are optional and configurable per row:

- `none`: do not evaluate generated code
- `syntax`: run a local Python syntax check
- `humaneval`: run HumanEval tests in a subprocess with timeout
