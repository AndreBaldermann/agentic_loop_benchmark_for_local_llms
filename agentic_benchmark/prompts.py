from __future__ import annotations

import json
from typing import Any

from .models import BenchmarkTask
from .review_parser import compact_feedback

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


def format_task(task: BenchmarkTask) -> str:
    """
    Render a provider-neutral task block for prompts.

    Args:
        task, BenchmarkTask: task id, prompt, entry point, and metadata.

    Returns:
        task_text, str: formatted task description for Coder and Reviewer prompts.
    """
    metadata = json.dumps(task.metadata, ensure_ascii=False, indent=2) if task.metadata else "{}"
    parts = [
        f"TASK SOURCE: {task.source}",
        f"TASK ID: {task.task_id}",
        "AUFGABE:",
        task.prompt,
    ]
    if task.entry_point:
        parts.extend(["ENTRY POINT:", task.entry_point])
    parts.extend(["METADATA:", metadata])
    return "\n".join(parts)


def feedback_for_mode(
    feedback_mode: str,
    review: dict[str, Any] | None,
    syntax_error: str | None,
) -> str:
    """
    Render feedback according to the experiment feedback mode.

    Args:
        feedback_mode, str: one of none, compact_json, full_json, critical_only, suggestions_only.
        review, dict[str, Any] | None: previous Reviewer output.
        syntax_error, str | None: latest syntax error.

    Returns:
        feedback, str: text inserted into the next Coder prompt.
    """
    if feedback_mode == "none":
        return "Feedback ist für diese Konfiguration deaktiviert."
    if feedback_mode == "critical_only":
        issues = review.get("critical_issues", []) if review else []
        return json.dumps({"syntax_error": syntax_error or None, "critical_issues": issues}, ensure_ascii=False, indent=2)
    if feedback_mode == "suggestions_only":
        suggestions = review.get("suggestions", []) if review else []
        return json.dumps({"syntax_error": syntax_error or None, "suggestions": suggestions}, ensure_ascii=False, indent=2)
    if feedback_mode == "full_json":
        return json.dumps({"syntax_error": syntax_error or None, "review": review}, ensure_ascii=False, indent=2)
    return compact_feedback(review, syntax_error)


def make_coder_prompt(
    task: BenchmarkTask,
    code: str,
    review: dict[str, Any] | None,
    syntax_error: str | None,
    *,
    feedback_mode: str = "compact_json",
    template_name: str = "coder_default",
) -> str:
    """
    Build the prompt sent to the Coder agent.

    Args:
        task, BenchmarkTask: task being solved.
        code, str: current candidate code from the previous round.
        review, dict[str, Any] | None: previous Reviewer feedback.
        syntax_error, str | None: current local syntax error.
        feedback_mode, str: feedback rendering strategy.
        template_name, str: Coder prompt template identifier.

    Returns:
        prompt, str: complete Coder prompt that requests Python code only.
    """
    feedback = feedback_for_mode(feedback_mode, review, syntax_error)
    task_text = format_task(task)

    if template_name == "coder_minimal":
        return f"""
{task.prompt}

AKTUELLER CODE:
{code if code else "Noch kein Code vorhanden."}

FEEDBACK:
{feedback}

{SYSTEM_RULES}
""".strip()

    return f"""
Du bist ein erfahrener Python-Entwickler in einem agentischen Coder/Reviewer-Loop.
Dein Ziel ist, die Aufgabe unter Berücksichtigung des Feedbacks zu lösen.

{task_text}

AKTUELLER CODE:
{code if code else "Noch kein Code vorhanden."}

KOMPAKTES FEEDBACK:
{feedback}

{SYSTEM_RULES}

Erstelle jetzt eine vollständige, syntaktisch gültige und verbesserte Python-Datei.
Die Antwort muss direkt mit Python-Code beginnen.
""".strip()


def make_reviewer_prompt(
    task: BenchmarkTask,
    code: str,
    syntax_ok: bool,
    syntax_error: str,
    *,
    template_name: str = "reviewer_default",
) -> str:
    """
    Build the prompt sent to the Reviewer agent.

    Args:
        task, BenchmarkTask: task being reviewed.
        code, str: generated code to review.
        syntax_ok, bool: local syntax validation result.
        syntax_error, str: local syntax error text, or empty string.
        template_name, str: Reviewer prompt template identifier.

    Returns:
        prompt, str: complete Reviewer prompt that requests JSON only.
    """
    task_text = format_task(task)
    strictness = "sehr knapp" if template_name == "reviewer_minimal" else "streng und hilfreich"

    return f"""
Du bist ein {strictness}er Senior Code Reviewer für Python, PyTorch und KI-Code.
Du bist Teil eines agentischen Loops: Dein Feedback beeinflusst die nächste Coder-Runde.

{task_text}

ZU PRÜFENDER CODE:
{code}

LOKALER SYNTAXCHECK:
syntax_ok = {syntax_ok}
syntax_error = {syntax_error or "None"}

Bewerte nach:
- Korrektheit bezogen auf die Aufgabe
- Erfüllung der Aufgabe
- Lesbarkeit
- Python Best Practices
- Fehlerbehandlung
- Wartbarkeit
- Risiken durch Halluzinationen oder fehlende Teile

Regeln:
- Antworte ausschließlich mit einem validen JSON-Objekt.
- Keine Markdown-Codeblöcke.
- Kein Thinking.
- Kein Text vor oder nach dem JSON.
- Wenn syntax_ok false ist, muss approved false sein.
- approved=true wenn keine kritischen funktionalen Fehler mehr erkennbar sind.
- Stilfragen, Benennungen, Kommentare, Type-Hints und optionale Best Practices dürfen approved=true NICHT verhindern.
- critical_issues dürfen nur echte Fehler enthalten.
- Behaupte keine fehlenden Methoden oder Klassen, ohne sie im Code geprüft zu haben.

JSON-Schema:
{{
  "approved": false,
  "score": 0,
  "critical_issues": ["..."],
  "suggestions": ["..."]
}}
""".strip()
