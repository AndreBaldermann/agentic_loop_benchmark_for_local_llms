#!/usr/bin/env python3

import ast
import json
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

CODER = "qwen3-coder-next:latest"
REVIEWER = "qwen3-coder-next:latest"

MAX_ROUNDS = 50
MAX_SAME_CODE_ROUNDS = 2
TIMEOUT_SECONDS = 600

OLLAMA_API_URL = "http://localhost:11434/api/generate"

# Per-role inference settings. These are sent to Ollama on every local API call.
# Check the active value with: ollama ps
CODER_CTX = 32768
REVIEWER_CTX = 16384

CODER_NUM_PREDICT = 4096
REVIEWER_NUM_PREDICT = 2048

CODER_TEMPERATURE = 0.1
REVIEWER_TEMPERATURE = 0.0


@dataclass(frozen=True)
class AgentConfig:
    """Configuration for a single Ollama-backed agent role."""

    role: str
    model: str
    num_ctx: int
    temperature: float
    num_predict: int
    json_mode: bool = False


CODER_AGENT = AgentConfig(
    role="Coder",
    model=CODER,
    num_ctx=CODER_CTX,
    temperature=CODER_TEMPERATURE,
    num_predict=CODER_NUM_PREDICT,
)
REVIEWER_AGENT = AgentConfig(
    role="Reviewer",
    model=REVIEWER,
    num_ctx=REVIEWER_CTX,
    temperature=REVIEWER_TEMPERATURE,
    num_predict=REVIEWER_NUM_PREDICT,
    json_mode=True,
)

AGENTS = {
    CODER_AGENT.role: CODER_AGENT,
    REVIEWER_AGENT.role: REVIEWER_AGENT,
}

MAX_FEEDBACK_ITEMS = 6
MAX_FEEDBACK_CHARS = 4000

SYSTEM_RULES = """
Wichtige Regeln:
- Gib keinen Markdown-Codeblock zurück.
- Gib keinen Text vor oder nach dem Code zurück.
- Gib ausschließlich vollständigen, lauffähigen Python-Code zurück.
- Keine ```python fences.
- Keine Erklärungen.
- Keine Thinking-Ausgabe.
- Keine Zeilenumbrüche innerhalb von Variablennamen, Strings oder Funktionsargumenten.
- Berücksichtige das Reviewer-Feedback konkret.
"""


def print_block(title: str, text: str):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)
    print(text)
    print("=" * 100 + "\n")


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)


def estimate_tokens(text: str) -> int:
    """Very rough estimate. Code often needs more tokens than prose."""
    return max(1, len(text) // 4)


def ollama(
    model: str,
    prompt: str,
    *,
    num_ctx: int,
    temperature: float,
    num_predict: int,
    json_mode: bool = False,
) -> dict[str, Any]:
    """Call local Ollama via HTTP API so each agent can get its own context size."""
    start = time.time()

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "num_ctx": num_ctx,
            "temperature": temperature,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_predict": num_predict,
        },
    }

    # Ollama JSON mode is useful for the reviewer. It strongly reduces
    # Markdown fences and free-form text, but we still keep parse_review robust.
    if json_mode:
        payload["format"] = "json"

    request = urllib.request.Request(
        OLLAMA_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Ollama API call failed. Is Ollama running? URL={OLLAMA_API_URL}. Error: {exc}"
        ) from exc

    elapsed = time.time() - start

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned invalid JSON: {raw[:1000]}") from exc

    if "error" in data:
        raise RuntimeError(str(data["error"]))

    output = strip_ansi(str(data.get("response", "")).strip())

    return {
        "output": output,
        "runtime": elapsed,
        "chars": len(output),
        "words": len(output.split()),
        "prompt_estimated_tokens": estimate_tokens(prompt),
        "num_ctx": num_ctx,
        "num_predict": num_predict,
        "json_mode": json_mode,
    }


def run_agent(config: AgentConfig, prompt: str) -> dict[str, Any]:
    """Run an agent role using its configuration."""
    return ollama(
        config.model,
        prompt,
        num_ctx=config.num_ctx,
        temperature=config.temperature,
        num_predict=config.num_predict,
        json_mode=config.json_mode,
    )


def extract_python_code(text: str) -> str:
    text = strip_ansi(text).strip()

    fenced = re.findall(
        r"```(?:python|py)?\s*(.*?)```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fenced:
        return fenced[-1].strip()

    lines = text.splitlines()

    start_idx = None
    for i, line in enumerate(lines):
        if line.startswith(("import ", "from ", "#!/usr/bin/env python")):
            start_idx = i
            break

    if start_idx is not None:
        text = "\n".join(lines[start_idx:])

    return text.strip()


def normalize_code(code: str) -> str:
    code = strip_ansi(code)
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in code.strip().splitlines()).strip()


def syntax_check(code: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        path = f.name

    result = subprocess.run(
        ["python3", "-m", "py_compile", path],
        text=True,
        capture_output=True,
    )

    Path(path).unlink(missing_ok=True)

    if result.returncode == 0:
        return True, ""

    return False, result.stderr.strip()


def ast_check(code: str) -> tuple[bool, str]:
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as exc:
        return False, f"{exc.__class__.__name__}: {exc}"


def find_json_objects(text: str) -> list[str]:
    objects = []
    stack = []
    start = None
    in_string = False
    escape = False

    for i, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            if not stack:
                start = i
            stack.append(char)

        elif char == "}":
            if stack:
                stack.pop()
                if not stack and start is not None:
                    objects.append(text[start : i + 1])
                    start = None

    return objects


def extract_review_json(text: str) -> dict[str, Any] | None:
    text = strip_ansi(text).strip()

    fenced = re.findall(
        r"```(?:json)?\s*(.*?)```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    candidates = fenced + find_json_objects(text)

    for candidate in reversed(candidates):
        try:
            data = json.loads(candidate.strip())
        except json.JSONDecodeError:
            continue

        if isinstance(data, dict) and "approved" in data:
            return data

    return None


def clean_list(value: Any, max_items: int = MAX_FEEDBACK_ITEMS) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [str(item) for item in value]
    else:
        items = [str(value)]

    cleaned = []
    for item in items:
        item = strip_ansi(item).strip()
        item = re.sub(r"\s+", " ", item)
        if item:
            cleaned.append(item)

    return cleaned[:max_items]


def parse_review(text: str) -> dict[str, Any]:
    data = extract_review_json(text)

    if data is None:
        fallback = strip_ansi(text).strip()
        fallback = fallback[-MAX_FEEDBACK_CHARS:]

        return {
            "approved": fallback.upper().startswith("APPROVED"),
            "score": 0,
            "critical_issues": ["Reviewer output was not valid JSON."],
            "suggestions": [
                "Reviewer muss ausschließlich ein valides JSON-Objekt ohne Markdown und ohne Thinking-Text zurückgeben.",
                fallback,
            ],
        }

    score = data.get("score", 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0

    return {
        "approved": bool(data.get("approved", False)),
        "score": max(0, min(100, score)),
        "critical_issues": clean_list(data.get("critical_issues")),
        "suggestions": clean_list(data.get("suggestions", data.get("recommendations"))),
    }


def compact_feedback(review: dict[str, Any] | None, syntax_error: str | None) -> str:
    if not review and not syntax_error:
        return "Noch kein Reviewer-Feedback vorhanden."

    payload = {
        "syntax_error": syntax_error or None,
        "approved": review.get("approved") if review else False,
        "score": review.get("score") if review else 0,
        "critical_issues": review.get("critical_issues", [])[:MAX_FEEDBACK_ITEMS] if review else [],
        "suggestions": review.get("suggestions", [])[:MAX_FEEDBACK_ITEMS] if review else [],
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if len(text) > MAX_FEEDBACK_CHARS:
        text = text[:MAX_FEEDBACK_CHARS] + "\n... gekürzt ..."

    return text


def make_coder_prompt(
    task: str,
    code: str,
    review: dict[str, Any] | None,
    syntax_error: str | None,
) -> str:
    feedback = compact_feedback(review, syntax_error)

    return f"""
Du bist ein erfahrener Python-Entwickler.

AUFGABE:
{task}

AKTUELLER CODE:
{code if code else "Noch kein Code vorhanden."}

KOMPAKTES FEEDBACK:
{feedback}

{SYSTEM_RULES}

Erstelle jetzt eine vollständige, syntaktisch gültige und verbesserte Python-Datei.
Die Antwort muss direkt mit Python-Code beginnen.
""".strip()


def make_reviewer_prompt(task: str, code: str, syntax_ok: bool, syntax_error: str) -> str:
    return f"""
Du bist ein strenger Senior Code Reviewer für Python, PyTorch und KI-Code.

AUFGABE:
{task}

ZU PRÜFENDER CODE:
{code}

LOKALER SYNTAXCHECK:
syntax_ok = {syntax_ok}
syntax_error = {syntax_error or "None"}

Bewerte nach:
- Korrektheit
- Erfüllung der Aufgabe
- Lesbarkeit
- Python Best Practices
- Fehlerbehandlung
- Wartbarkeit
- didaktischer Qualität
- Risiken durch Halluzinationen oder fehlende Teile

Regeln:
- Antworte ausschließlich mit einem validen JSON-Objekt.
- Keine Markdown-Codeblöcke.
- Kein Thinking.
- Kein Text vor oder nach dem JSON.
- Wenn syntax_ok false ist, muss approved false sein.
- approved=true wenn keine kritischen funktionalen Fehler mehr existieren.
- Stilfragen, Benennungen, Kommentare, Type-Hints und optionale Best Practices dürfen approved=true NICHT verhindern.
- critical_issues dürfen nur echte Fehler enthalten:
  * Syntaxfehler
  * Laufzeitfehler
  * mathematische Fehler
  * Architekturfehler
  * falsche Tensor-Shapes
  * fehlende Kernfunktionalität
- Behaupte keine fehlenden Methoden oder Klassen, ohne sie im Code geprüft zu haben.

JSON-Schema:
{{
  "approved": false,
  "score": 0,
  "critical_issues": ["..."],
  "suggestions": ["..."]
}}
""".strip()


def save_text(path: str, text: str):
    Path(path).write_text(text, encoding="utf-8")


def main():
    task = input("\nAufgabe für die Agenten:\n> ").strip()

    history = []
    code = ""
    last_review = None
    same_code_count = 0

    session_start = time.time()

    print("\nStarte Agentenschleife...")
    for agent in AGENTS.values():
        print(f"{agent.role:<8}: {agent.model}")
    print(f"Max Runden: {MAX_ROUNDS}")
    for agent in AGENTS.values():
        print(f"{agent.role:<8} Kontext: {agent.num_ctx} tokens")
    print(f"Ollama API       : {OLLAMA_API_URL}")

    for round_no in range(1, MAX_ROUNDS + 1):
        print("\n" + "#" * 100)
        print(f"RUNDE {round_no}")
        print("#" * 100)

        previous_code = code

        prev_syntax_ok, prev_syntax_error = syntax_check(code) if code else (
            False,
            "Noch kein Code vorhanden.",
        )

        coder_prompt = make_coder_prompt(
            task=task,
            code=code,
            review=last_review,
            syntax_error=None if prev_syntax_ok else prev_syntax_error,
        )

        print_block(f"RUNDE {round_no} - CODER PROMPT", coder_prompt)

        coder_result = run_agent(CODER_AGENT, coder_prompt)

        raw_code = coder_result["output"]
        code = normalize_code(extract_python_code(raw_code))

        print(f"Coder Laufzeit : {coder_result['runtime']:.2f}s")
        print(f"Coder Wörter   : {coder_result['words']}")
        print(f"Coder Zeichen  : {coder_result['chars']}")
        print(f"Coder Prompt est.: {coder_result['prompt_estimated_tokens']} tokens / ctx {coder_result['num_ctx']}")

        print_block(f"RUNDE {round_no} - CODER RAW OUTPUT", raw_code)
        print_block(f"RUNDE {round_no} - EXTRACTED CODE", code)

        syntax_ok, syntax_error = syntax_check(code)
        ast_ok, ast_error = ast_check(code)

        if not ast_ok and not syntax_error:
            syntax_ok = False
            syntax_error = ast_error

        review_prompt = make_reviewer_prompt(
            task=task,
            code=code,
            syntax_ok=syntax_ok,
            syntax_error=syntax_error,
        )

        print_block(f"RUNDE {round_no} - REVIEWER PROMPT", review_prompt)

        reviewer_result = run_agent(REVIEWER_AGENT, review_prompt)
        review = parse_review(reviewer_result["output"])

        if not syntax_ok:
            review["approved"] = False
            review["score"] = min(review.get("score", 0), 20)
            if syntax_error and syntax_error not in review["critical_issues"]:
                review["critical_issues"].insert(0, f"Lokaler Syntaxcheck fehlgeschlagen: {syntax_error}")

        last_review = review

        print(f"Reviewer Laufzeit : {reviewer_result['runtime']:.2f}s")
        print(f"Reviewer Wörter   : {reviewer_result['words']}")
        print(f"Reviewer Zeichen  : {reviewer_result['chars']}")
        print(f"Reviewer Prompt est.: {reviewer_result['prompt_estimated_tokens']} tokens / ctx {reviewer_result['num_ctx']}")

        print_block(f"RUNDE {round_no} - REVIEWER RAW OUTPUT", reviewer_result["output"])
        print_block(
            f"RUNDE {round_no} - REVIEW PARSED",
            json.dumps(review, ensure_ascii=False, indent=2),
        )

        changed = normalize_code(previous_code) != normalize_code(code)

        if not changed and previous_code:
            same_code_count += 1
        else:
            same_code_count = 0

        history.append({
            "round": round_no,
            "coder_runtime": coder_result["runtime"],
            "reviewer_runtime": reviewer_result["runtime"],
            "syntax_ok": syntax_ok,
            "syntax_error": syntax_error,
            "changed": changed,
            "score": review["score"],
            "approved": review["approved"],
            "code": code,
            "review": review,
            "coder_raw_output": raw_code,
            "reviewer_raw_output": reviewer_result["output"],
        })

        if syntax_ok and review["approved"]:
            print("\nReviewer hat APPROVED zurückgegeben und lokaler Syntaxcheck ist OK.")
            break

        if same_code_count >= MAX_SAME_CODE_ROUNDS:
            print("\nAbbruch: Code stagniert trotz Feedback.")
            break

    total_runtime = time.time() - session_start

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = f"result_{timestamp}.py"
    history_file = f"history_{timestamp}.json"

    save_text(result_file, code)
    save_text(history_file, json.dumps(history, ensure_ascii=False, indent=2))

    print("\n" + "#" * 100)
    print("AGENTENSITZUNG BEENDET")
    print("#" * 100)
    print(f"Gesamtzeit: {total_runtime:.2f} Sekunden")

    for item in history:
        print(
            f"Runde {item['round']} | "
            f"Coder: {item['coder_runtime']:.2f}s | "
            f"Reviewer: {item['reviewer_runtime']:.2f}s | "
            f"Syntax: {item['syntax_ok']} | "
            f"Score: {item['score']} | "
            f"Approved: {item['approved']} | "
            f"Changed: {item['changed']}"
        )

    print(f"\nFinaler Code gespeichert in:\n{result_file}")
    print(f"\nHistorie gespeichert in:\n{history_file}")


if __name__ == "__main__":
    main()
