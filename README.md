# agentic_loop_benchmark_for_local_llms

# Friendly Start :-)

A beginner-friendly local tool for trying and benchmarking **agentic Coder/Reviewer loops** with local Ollama models.

How to directly use it in Ubuntu:

Prepare Environment:
1. git clone https://github.com/AndreBaldermann/agentic_loop_benchmark_for_local_llms.git
2. cd agentic_loop_benchmark_for_local_llms
3. python -m venv .venv
4. pip install -r requirements.txt

Now you need local llms. Install ollama if you dont have it, yet:

curl -fsSL https://ollama.com/install.sh | sh
ollama --version

Install llms for running the demo without editing. Requires ca. 77 GB of memory:

ollama pull qwen3-coder-next
ollama pull gemma4:26b-a4b-it-q4_K_M
ollama pull deepseek-coder-v2
ollama pull qwen2.5:32b
ollama pull llama3.2:3b
ollama pull llama3.2:1b
ollama pull llama3.1:8b

Run the demo:

python3 basis_agentic_coding_loop.py \
  --config configs/loop_configs.csv \
  --prompt "Write a Python function add_two(x) that returns x + 2." \
  --pdf-report

Open the PDF-File under report/interactive_{date_time}/summary.pdf

# Friendly config

Open configs/loop_configs.csv

It should be largely self-explanatory:

The agentic loop currently consists of a coder and a reviewer.
Each row is a different experiment where you define specifics about the coder and reviewer behavior

Tokens? What's a token? 
LLMs neither predict the next letter nor the next word. They predict reusable letter combinations. Like the word "predict" 
consists of 2 tokens: "pre" and "dict". For source code the tokens are shorter than for natural language. 

The config file:

experiment_id       : Just an arbitrary name you can choose
task_provider       : relevant for "benchmark run" command. HumanEval 
                      is a standard test set of 164 tasks by OpenAI.
coder_model         : put in the LLMs you want to test. Find options 
                      on your system by executing command "ollama list"
reviewer model      : analog to the coder_model, see above
coder ctx           : coder context window. 32k tokens is a good start. 
                      Most local llms should be more capable
reviewer_ctx:       : reviewer context window
coder_num_predict   : maximum length of response before model stops 
                      execution. Good for short simple codes.
reviewer_num_predict: analog to the coder_num_predict, see above
coder_temperature   : creativity of the llm. Also may lead to 
                      hallucinations. For the coder a value of 
                      0.1 to 0.3 is generally considered good practice
reviewer_temperature: analog to the coder_num_predict, see above
max_rounds          : maximum number of unsuccesful code / reviewer 
                      interactions before the test is forcefully stopped.
max_same_code_rounds: Like in chess. Repeat the same move twice, game over.

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
- `overview.pdf` when `--pdf-report` is used

## 4. Generate overview PDF later

```bash
python3 -m agentic_benchmark.cli report-pdf \
  --summary results/run_YYYYMMDD_HHMMSS/summary.csv \
  --agent-calls results/run_YYYYMMDD_HHMMSS/agent_calls.csv \
  --output reports/overview.pdf
```

The PDF overview subdivides every task/experiment cell into `R` (rounds/max rounds), `TCT` (total generated Coder tokens), and `TRT` (total generated Reviewer tokens).

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
