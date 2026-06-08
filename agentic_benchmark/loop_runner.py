from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from .code_processing import ast_check, extract_python_code, normalize_code, syntax_check
from .evaluators import evaluate
from .models import AgentCallRecord, BenchmarkTask, ExperimentConfig, LoopRunResult, ModelCallResult
from .ollama_client import run_agent
from .prompts import make_coder_prompt, make_reviewer_prompt
from .review_parser import parse_review


def make_run_id() -> str:
    """
    Create a unique UTC timestamp-based run identifier.

    Args:
        None.

    Returns:
        run_id, str: sortable identifier including date, time, and microseconds.
    """
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def print_block(title: str, text: str) -> None:
    """
    Print a titled debug block for verbose prompt inspection.

    Args:
        title, str: block title.
        text, str: block contents.

    Returns:
        None.
    """
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)
    print(text)
    print("=" * 100 + "\n")


def make_call_record(
    *,
    run_id: str,
    experiment: ExperimentConfig,
    task: BenchmarkTask,
    repetition: int,
    round_no: int,
    prompt: str,
    result: ModelCallResult,
    syntax_ok_after_coder: bool | None = None,
    code_changed: bool | None = None,
    reviewer_approved: bool | None = None,
    reviewer_score: int | None = None,
    critical_issues_count: int | None = None,
    suggestions_count: int | None = None,
    stop_reason_if_any: str | None = None,
) -> AgentCallRecord:
    """
    Convert one model call result into a CSV-ready agent call record.

    Args:
        run_id, str: unique run identifier.
        experiment, ExperimentConfig: active experiment settings.
        task, BenchmarkTask: active task.
        repetition, int, >= 1: repetition index.
        round_no, int, >= 1: loop round index.
        prompt, str: prompt sent to the model.
        result, ModelCallResult: normalized backend response.

    Returns:
        record, AgentCallRecord: flattened per-call telemetry.
    """
    return AgentCallRecord(
        run_id=run_id,
        experiment_id=experiment.experiment_id,
        task_provider=task.source,
        task_id=task.task_id,
        repetition=repetition,
        round_no=round_no,
        agent_role=result.role,
        agent_model=result.model,
        num_ctx=result.num_ctx,
        temperature=experiment.coder.temperature if result.role == "Coder" else (experiment.reviewer.temperature if experiment.reviewer else 0.0),
        num_predict=result.num_predict,
        json_mode=result.json_mode,
        prompt_chars=len(prompt),
        output_chars=result.chars,
        prompt_tokens=result.prompt_tokens,
        output_tokens=result.output_tokens,
        used_tokens=result.used_tokens,
        wallclock_s=result.wallclock_s,
        total_duration_s=result.total_duration_s,
        load_duration_s=result.load_duration_s,
        prompt_eval_duration_s=result.prompt_eval_duration_s,
        eval_duration_s=result.eval_duration_s,
        feedback_mode=experiment.feedback_mode,
        stop_policy=experiment.stop_policy,
        syntax_ok_after_coder=syntax_ok_after_coder,
        code_changed=code_changed,
        reviewer_approved=reviewer_approved,
        reviewer_score=reviewer_score,
        critical_issues_count=critical_issues_count,
        suggestions_count=suggestions_count,
        stop_reason_if_any=stop_reason_if_any,
        call_failed=result.failed,
        error_type=result.error_type,
        error_message=result.error_message,
    )


def should_stop(
    *,
    experiment: ExperimentConfig,
    round_no: int,
    syntax_ok: bool,
    review: dict | None,
    same_code_count: int,
) -> str | None:
    """
    Evaluate stop conditions after one loop round.

    Args:
        experiment, ExperimentConfig: stop-policy and max-round settings.
        round_no, int, >= 1: current loop round.
        syntax_ok, bool: latest local syntax result.
        review, dict | None: latest Reviewer result.
        same_code_count, int, >= 0: consecutive unchanged-code counter.

    Returns:
        stop_reason, str | None: reason to stop, or None to continue.
    """
    approved = bool(review and review.get("approved"))
    if experiment.stop_policy == "fixed_rounds":
        return "fixed_rounds_complete" if round_no >= experiment.max_rounds else None
    if experiment.stop_policy == "max_rounds_only":
        return None
    if experiment.stop_policy == "single_coder_round":
        return "single_coder_round_complete"
    if experiment.stop_policy == "reviewer_approved" and approved:
        return "reviewer_approved"
    if experiment.stop_policy == "reviewer_approved_and_syntax_ok" and syntax_ok and approved:
        return "reviewer_approved_and_syntax_ok"
    if experiment.stop_policy == "stagnation_or_approved":
        if syntax_ok and approved:
            return "reviewer_approved_and_syntax_ok"
        if same_code_count >= experiment.max_same_code_rounds:
            return "stagnation_detected"
    elif same_code_count >= experiment.max_same_code_rounds:
        return "stagnation_detected"
    return None


def run_agentic_loop(
    task: BenchmarkTask,
    experiment: ExperimentConfig,
    *,
    repetition: int = 1,
    verbose: bool = False,
) -> LoopRunResult:
    """
    Execute the iterative Coder/Reviewer workflow for one task.

    Flow:
        1. Coder generates or revises a candidate solution.
        2. Local syntax and AST checks validate the candidate.
        3. Reviewer optionally evaluates the candidate and emits feedback.
        4. Feedback is returned to the next Coder round.
        5. Repeat until stop condition, failure, stagnation, or max_rounds.

    Args:
        task, BenchmarkTask: task to solve.
        experiment, ExperimentConfig: agent, loop, feedback, and evaluator settings.
        repetition, int, >= 1: repetition index for repeated benchmark runs.
        verbose, bool: whether to print prompts and debug blocks.

    Returns:
        result, LoopRunResult: final code, review, evaluation, metrics, and call history.
    """
    run_id = make_run_id()
    timestamp = datetime.now(timezone.utc).isoformat()
    history: list[dict] = []
    agent_calls: list[AgentCallRecord] = []
    code = ""
    last_review = None
    same_code_count = 0
    code_changed_rounds = 0
    unchanged_rounds = 0
    stop_reason = "max_rounds_reached"
    final_syntax_ok = False
    final_syntax_error = "Noch kein Code vorhanden."
    start = time.time()

    # Invariant: round_no is 1-based so CSV rows match human-readable
    # benchmark logs and can be compared directly with max_rounds.
    for round_no in range(1, experiment.max_rounds + 1):
        previous_code = code

        # --------------------------------------------------
        # Generate candidate solution
        # --------------------------------------------------
        prev_syntax_ok, prev_syntax_error = syntax_check(code) if code else (
            False,
            "Noch kein Code vorhanden.",
        )
        coder_prompt = make_coder_prompt(
            task,
            code,
            last_review,
            None if prev_syntax_ok else prev_syntax_error,
            feedback_mode=experiment.feedback_mode,
            template_name=experiment.coder_prompt_template,
        )
        if verbose:
            print_block(f"{run_id} RUNDE {round_no} - CODER PROMPT", coder_prompt)
        coder_result = run_agent(experiment.coder, coder_prompt)
        raw_code = coder_result.output

        # Failed model calls are benchmark data, not process errors.
        # They get zero backend metrics and stop only this task run.
        if coder_result.failed:
            code = ""
            syntax_ok = False
            syntax_error = coder_result.error_message or "Coder model call failed."
            ast_ok = False
            ast_error = syntax_error
        else:
            code = normalize_code(extract_python_code(raw_code))
            syntax_ok, syntax_error = syntax_check(code)
            ast_ok, ast_error = ast_check(code)

        if not ast_ok and not syntax_error:
            syntax_ok = False
            syntax_error = ast_error
        final_syntax_ok = syntax_ok
        final_syntax_error = syntax_error

        # Code stagnation is measured after normalization so trailing
        # whitespace or line-ending differences do not count as progress.
        changed = normalize_code(previous_code) != normalize_code(code)
        if changed:
            code_changed_rounds += 1
            same_code_count = 0
        elif previous_code:
            unchanged_rounds += 1
            same_code_count += 1
        else:
            same_code_count = 0

        coder_call_record = make_call_record(
            run_id=run_id,
            experiment=experiment,
            task=task,
            repetition=repetition,
            round_no=round_no,
            prompt=coder_prompt,
            result=coder_result,
            syntax_ok_after_coder=syntax_ok,
            code_changed=changed,
        )
        agent_calls.append(coder_call_record)

        if coder_result.failed:
            # Stop immediately because Reviewer feedback would be meaningless
            # without a candidate solution to inspect.
            stop_reason = "coder_model_call_failed"
            history.append(
                {
                    "round": round_no,
                    "coder_runtime": coder_result.wallclock_s,
                    "reviewer_runtime": 0.0,
                    "syntax_ok": syntax_ok,
                    "syntax_error": syntax_error,
                    "changed": changed,
                    "score": None,
                    "approved": None,
                    "code": code,
                    "review": None,
                    "coder_raw_output": raw_code,
                    "reviewer_raw_output": "",
                    "coder_metrics": coder_result.__dict__,
                    "reviewer_metrics": None,
                }
            )
            break

        # --------------------------------------------------
        # Review generated solution
        # --------------------------------------------------
        review = None
        reviewer_raw_output = ""
        reviewer_result = None
        if experiment.reviewer and experiment.stop_policy != "single_coder_round":
            review_prompt = make_reviewer_prompt(
                task,
                code,
                syntax_ok,
                syntax_error,
                template_name=experiment.reviewer_prompt_template,
            )
            if verbose:
                print_block(f"{run_id} RUNDE {round_no} - REVIEWER PROMPT", review_prompt)
            reviewer_result = run_agent(experiment.reviewer, review_prompt)
            reviewer_raw_output = reviewer_result.output
            if reviewer_result.failed:
                # Preserve a review-shaped object so downstream history,
                # CSV aggregation, and feedback code can stay schema-stable.
                review = {
                    "approved": False,
                    "score": 0,
                    "critical_issues": [reviewer_result.error_message or "Reviewer model call failed."],
                    "suggestions": [],
                }
            else:
                review = parse_review(reviewer_result.output)
            if not syntax_ok:
                # Local syntax validation is an invariant stronger than model
                # opinion: syntactically invalid code can never be approved.
                review["approved"] = False
                review["score"] = min(review.get("score", 0), 20)
                if syntax_error and syntax_error not in review["critical_issues"]:
                    review["critical_issues"].insert(0, f"Lokaler Syntaxcheck fehlgeschlagen: {syntax_error}")
            last_review = review
            agent_calls.append(
                make_call_record(
                    run_id=run_id,
                    experiment=experiment,
                    task=task,
                    repetition=repetition,
                    round_no=round_no,
                    prompt=review_prompt,
                    result=reviewer_result,
                    reviewer_approved=review.get("approved"),
                    reviewer_score=review.get("score"),
                    critical_issues_count=len(review.get("critical_issues", [])),
                    suggestions_count=len(review.get("suggestions", [])),
                )
            )
        else:
            last_review = review

        # --------------------------------------------------
        # Persist round history
        # --------------------------------------------------
        history.append(
            {
                "round": round_no,
                "coder_runtime": coder_result.wallclock_s,
                "reviewer_runtime": reviewer_result.wallclock_s if reviewer_result else 0.0,
                "syntax_ok": syntax_ok,
                "syntax_error": syntax_error,
                "changed": changed,
                "score": review.get("score") if review else None,
                "approved": review.get("approved") if review else None,
                "code": code,
                "review": review,
                "coder_raw_output": raw_code,
                "reviewer_raw_output": reviewer_raw_output,
                "coder_metrics": coder_result.__dict__,
                "reviewer_metrics": reviewer_result.__dict__ if reviewer_result else None,
            }
        )

        # --------------------------------------------------
        # Decide whether this task run should continue
        # --------------------------------------------------
        if reviewer_result and reviewer_result.failed:
            stop = "reviewer_model_call_failed"
        else:
            stop = should_stop(
                experiment=experiment,
                round_no=round_no,
                syntax_ok=syntax_ok,
                review=review,
                same_code_count=same_code_count,
            )
        if stop:
            stop_reason = stop
            break

    # --------------------------------------------------
    # Evaluate final artifact and return aggregate result
    # --------------------------------------------------
    evaluation = evaluate(task, code, experiment.evaluator)
    wallclock_total_s = time.time() - start
    stagnation_detected = stop_reason == "stagnation_detected"
    if agent_calls:
        last_call = agent_calls[-1]
        agent_calls[-1] = AgentCallRecord(
            **{**last_call.__dict__, "stop_reason_if_any": stop_reason}
        )

    return LoopRunResult(
        run_id=run_id,
        timestamp=timestamp,
        experiment=experiment,
        task=task,
        repetition=repetition,
        rounds_used=len(history),
        stop_reason=stop_reason,
        final_code=code,
        final_syntax_ok=final_syntax_ok,
        final_syntax_error=final_syntax_error,
        final_review=last_review,
        evaluation=evaluation,
        agent_calls=agent_calls,
        history=history,
        wallclock_total_s=wallclock_total_s,
        code_changed_rounds=code_changed_rounds,
        unchanged_rounds=unchanged_rounds,
        stagnation_detected=stagnation_detected,
    )


def print_interactive_summary(result: LoopRunResult) -> None:
    """
    Print a human-readable summary for one interactive run.

    Args:
        result, LoopRunResult: completed interactive run.

    Returns:
        None.
    """
    print("\n" + "#" * 100)
    print("AGENTENSITZUNG BEENDET")
    print("#" * 100)
    print(f"Run ID: {result.run_id}")
    print(f"Gesamtzeit: {result.wallclock_total_s:.2f} Sekunden")
    print(f"Stop Reason: {result.stop_reason}")
    print(f"Evaluator: {result.evaluation.name} passed={result.evaluation.passed}")
    for item in result.history:
        print(
            f"Runde {item['round']} | "
            f"Coder: {item['coder_runtime']:.2f}s | "
            f"Reviewer: {item['reviewer_runtime']:.2f}s | "
            f"Syntax: {item['syntax_ok']} | "
            f"Score: {item['score']} | "
            f"Approved: {item['approved']} | "
            f"Changed: {item['changed']}"
        )
