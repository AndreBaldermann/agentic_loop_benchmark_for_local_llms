from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PAGE_WIDTH = 842.0
PAGE_HEIGHT = 595.0
PAGE_SIZES_LANDSCAPE = {
    "A4": (842.0, 595.0),
    "A3": (1191.0, 842.0),
    "A2": (1684.0, 1191.0),
    "A1": (2384.0, 1684.0),
    "A0": (3370.0, 2384.0),
}
MARGIN = 28.0
TITLE_FONT_SIZE = 16
BODY_FONT_SIZE = 7
HEADER_FONT_SIZE = 7
ROW_HEIGHT = 18.0
TASK_COL_WIDTH = 150.0
MIN_EXPERIMENT_GROUP_WIDTH = 78.0
MAX_EXPERIMENT_GROUP_WIDTH = 132.0
SUB_COLUMNS = ("R", "TCT", "TRT")
TIME_SUB_COLUMNS = ("TTNL", "TTC", "TTR")
LOAD_SUB_COLUMNS = ("TTL", "TLC", "TLR")
TPS_SUB_COLUMNS = ("ATPS", "CTPS", "RTPS")
RELIABILITY_SUB_COLUMNS = ("FC", "TO", "ERR")
QUALITY_SUB_COLUMNS = ("SYN", "APP", "EVAL")
EFFICIENCY_SUB_COLUMNS = ("Q", "QPS", "QPK")
GREEN = (0.35, 0.82, 0.35)
RED = (0.90, 0.25, 0.25)
GRAY = (0.66, 0.66, 0.66)
BLUE = (0.35, 0.60, 0.95)


@dataclass(frozen=True)
class OverviewCell:
    """
    Aggregated table cell for one task/experiment pair.

    The overview PDF can receive multiple repetitions for the same task and
    experiment. The cell stores an averaged rounds_used value while preserving
    stop reasons for priority coloring.
    """

    rounds_used: float
    max_rounds: int
    stop_reasons: tuple[str, ...]
    repetitions: int
    coder_tokens: float = 0.0
    reviewer_tokens: float = 0.0
    total_execution_s: float = 0.0
    coder_execution_s: float = 0.0
    reviewer_execution_s: float = 0.0
    total_load_s: float = 0.0
    coder_load_s: float = 0.0
    reviewer_load_s: float = 0.0
    failed_calls: float = 0.0
    timeout_calls: float = 0.0
    error_type_count: float = 0.0
    syntax_ok_rate: float | None = None
    approval_rate: float | None = None
    evaluator_pass_rate: float | None = None

    @property
    def rounds_label(self) -> str:
        """
        Render the visible rounds cell label.

        Returns:
            label, str: rounds_used/max_rounds, including n when repetitions > 1.
        """
        rounds = int(self.rounds_used) if self.rounds_used.is_integer() else round(self.rounds_used, 1)
        suffix = f" n={self.repetitions}" if self.repetitions > 1 else ""
        return f"{rounds}/{self.max_rounds}{suffix}"

    def coder_tokens_label(self) -> str:
        """
        Render the visible Coder-token cell label.

        Returns:
            label, str: rounded total Coder tokens for the task/experiment.
        """
        return str(int(round(self.coder_tokens)))

    def reviewer_tokens_label(self) -> str:
        """
        Render the visible Reviewer-token cell label.

        Returns:
            label, str: rounded total Reviewer tokens for the task/experiment.
        """
        return str(int(round(self.reviewer_tokens)))

    def total_execution_label(self) -> str:
        """
        Render total no-load model execution time.

        Returns:
            label, str: total Coder+Reviewer execution seconds excluding model loading.
        """
        return seconds_label(self.total_execution_s)

    def coder_execution_label(self) -> str:
        """
        Render Coder no-load model execution time.

        Returns:
            label, str: Coder execution seconds excluding model loading.
        """
        return seconds_label(self.coder_execution_s)

    def reviewer_execution_label(self) -> str:
        """
        Render Reviewer no-load model execution time.

        Returns:
            label, str: Reviewer execution seconds excluding model loading.
        """
        return seconds_label(self.reviewer_execution_s)

    def total_load_label(self) -> str:
        """
        Render total model loading time.

        Returns:
            label, str: total Coder+Reviewer load seconds.
        """
        return seconds_label(self.total_load_s)

    def coder_load_label(self) -> str:
        """
        Render Coder model loading time.

        Returns:
            label, str: Coder load seconds.
        """
        return seconds_label(self.coder_load_s)

    def reviewer_load_label(self) -> str:
        """
        Render Reviewer model loading time.

        Returns:
            label, str: Reviewer load seconds.
        """
        return seconds_label(self.reviewer_load_s)

    def combined_tps_label(self) -> str:
        """
        Render combined generated-token throughput.

        Returns:
            label, str: Coder+Reviewer output tokens per no-load execution second.
        """
        return rate_label(self.combined_tps)

    def coder_tps_label(self) -> str:
        """
        Render Coder generated-token throughput.

        Returns:
            label, str: Coder output tokens per no-load execution second.
        """
        return rate_label(self.coder_tps)

    def reviewer_tps_label(self) -> str:
        """
        Render Reviewer generated-token throughput.

        Returns:
            label, str: Reviewer output tokens per no-load execution second.
        """
        return rate_label(self.reviewer_tps)

    def failed_calls_label(self) -> str:
        """
        Render failed model call count.

        Returns:
            label, str: rounded failed call count.
        """
        return count_label(self.failed_calls)

    def timeout_calls_label(self) -> str:
        """
        Render timeout call count.

        Returns:
            label, str: rounded timeout count.
        """
        return count_label(self.timeout_calls)

    def error_type_count_label(self) -> str:
        """
        Render distinct error type count.

        Returns:
            label, str: rounded distinct error type count.
        """
        return count_label(self.error_type_count)

    def syntax_rate_label(self) -> str:
        """
        Render syntax success rate.

        Returns:
            label, str: percent-like syntax success rate or dash when unknown.
        """
        return percent_label(self.syntax_ok_rate)

    def approval_rate_label(self) -> str:
        """
        Render reviewer approval rate.

        Returns:
            label, str: percent-like approval rate or dash when unknown.
        """
        return percent_label(self.approval_rate)

    def evaluator_pass_rate_label(self) -> str:
        """
        Render evaluator pass rate.

        Returns:
            label, str: percent-like evaluator pass rate or dash when unknown.
        """
        return percent_label(self.evaluator_pass_rate)

    def quality_score_label(self) -> str:
        """
        Render combined quality score.

        Returns:
            label, str: average of available syntax/approval/evaluator rates.
        """
        return percent_label(self.quality_score)

    def quality_per_second_label(self) -> str:
        """
        Render quality score per no-load execution second.

        Returns:
            label, str: quality points per second.
        """
        return rate_label(self.quality_per_second)

    def quality_per_1k_tokens_label(self) -> str:
        """
        Render quality score per thousand generated tokens.

        Returns:
            label, str: quality points per 1k generated output tokens.
        """
        return rate_label(self.quality_per_1k_tokens)

    @property
    def combined_output_tokens(self) -> float:
        """
        Return generated Coder plus Reviewer tokens.

        Returns:
            tokens, float, >= 0.0: total generated output tokens.
        """
        return self.coder_tokens + self.reviewer_tokens

    @property
    def combined_tps(self) -> float:
        """
        Return combined generated tokens per no-load execution second.

        Returns:
            tokens_per_second, float, >= 0.0: throughput or 0.0 when timing is missing.
        """
        return safe_divide(self.combined_output_tokens, self.total_execution_s)

    @property
    def coder_tps(self) -> float:
        """
        Return Coder generated tokens per Coder no-load execution second.

        Returns:
            tokens_per_second, float, >= 0.0: Coder throughput or 0.0 when timing is missing.
        """
        return safe_divide(self.coder_tokens, self.coder_execution_s)

    @property
    def reviewer_tps(self) -> float:
        """
        Return Reviewer generated tokens per Reviewer no-load execution second.

        Returns:
            tokens_per_second, float, >= 0.0: Reviewer throughput or 0.0 when timing is missing.
        """
        return safe_divide(self.reviewer_tokens, self.reviewer_execution_s)

    @property
    def quality_score(self) -> float | None:
        """
        Return average quality across available quality indicators.

        Returns:
            score, float | None: average of available rates in 0.0..1.0, or None when unknown.
        """
        values = [
            value
            for value in (self.syntax_ok_rate, self.approval_rate, self.evaluator_pass_rate)
            if value is not None
        ]
        if not values:
            return None
        return average(values)

    @property
    def quality_per_second(self) -> float:
        """
        Return quality score per no-load execution second.

        Returns:
            score_per_second, float, >= 0.0: quality/time efficiency or 0.0 when unavailable.
        """
        return safe_divide(self.quality_score or 0.0, self.total_execution_s)

    @property
    def quality_per_1k_tokens(self) -> float:
        """
        Return quality score per thousand generated output tokens.

        Returns:
            score_per_1k_tokens, float, >= 0.0: quality/token efficiency or 0.0 when unavailable.
        """
        return safe_divide((self.quality_score or 0.0) * 1000.0, self.combined_output_tokens)

    @property
    def label(self) -> str:
        """
        Render the legacy combined cell label.

        Returns:
            label, str: rounds_used/max_rounds for compatibility with older callers.
        """
        return self.rounds_label


class SimplePdf:
    """
    Minimal PDF writer for text, filled rectangles, and stroked rectangles.

    The writer intentionally avoids external dependencies so reports can be
    generated in the current standard-library-only project. It supports only
    the drawing primitives needed for the benchmark overview table.
    """

    def __init__(self, *, page_width: float = PAGE_WIDTH, page_height: float = PAGE_HEIGHT) -> None:
        """
        Initialize an empty PDF document.

        Args:
            page_width, float: PDF media box width in points.
            page_height, float: PDF media box height in points.
        """
        self.page_width = page_width
        self.page_height = page_height
        self.pages: list[list[str]] = []

    def add_page(self, commands: list[str]) -> None:
        """
        Append one PDF page content stream.

        Args:
            commands, list[str]: PDF drawing commands for one page.

        Returns:
            None.
        """
        self.pages.append(commands)

    def write(self, path: str | Path) -> None:
        """
        Write the complete PDF document to disk.

        Args:
            path, str | Path: destination PDF path.

        Returns:
            None.
        """
        objects: list[str] = []
        catalog_id = 1
        pages_id = 2
        font_id = 3
        next_id = 4
        page_ids: list[int] = []
        content_ids: list[int] = []

        for commands in self.pages:
            page_ids.append(next_id)
            content_ids.append(next_id + 1)
            next_id += 2

        objects.append(f"{catalog_id} 0 obj\n<< /Type /Catalog /Pages {pages_id} 0 R >>\nendobj\n")
        kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
        objects.append(f"{pages_id} 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>\nendobj\n")
        objects.append(f"{font_id} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

        for page_id, content_id, commands in zip(page_ids, content_ids, self.pages):
            content = "\n".join(commands).encode("latin-1", errors="replace")
            objects.append(
                f"{page_id} 0 obj\n"
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {self.page_width:.0f} {self.page_height:.0f}] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>\n"
                "endobj\n"
            )
            objects.append(
                f"{content_id} 0 obj\n<< /Length {len(content)} >>\nstream\n"
                + content.decode("latin-1")
                + "\nendstream\nendobj\n"
            )

        data = "%PDF-1.4\n".encode("latin-1")
        offsets = [0]
        for obj in objects:
            offsets.append(len(data))
            data += obj.encode("latin-1", errors="replace")
        xref_offset = len(data)
        data += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
        for offset in offsets[1:]:
            data += f"{offset:010d} 00000 n \n".encode("latin-1")
        data += (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("latin-1")
        Path(path).write_bytes(data)


def escape_pdf_text(text: Any) -> str:
    """
    Escape text for a PDF literal string.

    Args:
        text, Any: value to render as text.

    Returns:
        escaped, str: PDF-safe literal string contents.
    """
    value = str(text)
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_command(x: float, y: float, text: Any, *, size: int = BODY_FONT_SIZE) -> str:
    """
    Build a PDF text drawing command.

    Args:
        x, float: left coordinate in PDF points.
        y, float: baseline coordinate in PDF points.
        text, Any: text value to draw.
        size, int: font size in points.

    Returns:
        command, str: PDF text command.
    """
    return f"0 0 0 rg BT /F1 {size} Tf {x:.2f} {y:.2f} Td ({escape_pdf_text(text)}) Tj ET"


def fill_rect_command(x: float, y: float, width: float, height: float, color: tuple[float, float, float]) -> str:
    """
    Build a filled rectangle command.

    Args:
        x, float: left coordinate in points.
        y, float: bottom coordinate in points.
        width, float: rectangle width in points.
        height, float: rectangle height in points.
        color, tuple[float, float, float]: RGB values in range 0.0..1.0.

    Returns:
        command, str: PDF fill command.
    """
    r, g, b = color
    return f"{r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} {width:.2f} {height:.2f} re f"


def stroke_rect_command(x: float, y: float, width: float, height: float) -> str:
    """
    Build a stroked rectangle command.

    Args:
        x, float: left coordinate in points.
        y, float: bottom coordinate in points.
        width, float: rectangle width in points.
        height, float: rectangle height in points.

    Returns:
        command, str: PDF stroke command.
    """
    return f"0.75 0.75 0.75 RG {x:.2f} {y:.2f} {width:.2f} {height:.2f} re S"


def line_command(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    color: tuple[float, float, float] = (0.0, 0.0, 0.0),
    width: float = 0.8,
) -> str:
    """
    Build a stroked line command.

    Args:
        x1, float: start x coordinate in points.
        y1, float: start y coordinate in points.
        x2, float: end x coordinate in points.
        y2, float: end y coordinate in points.
        color, tuple[float, float, float]: RGB stroke color in range 0.0..1.0.
        width, float: stroke width in points.

    Returns:
        command, str: PDF line stroke command.
    """
    r, g, b = color
    return f"{width:.2f} w {r:.3f} {g:.3f} {b:.3f} RG {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S 1 w"


def truncate_text(text: str, max_chars: int) -> str:
    """
    Truncate text for a fixed-width table cell.

    Args:
        text, str: original text.
        max_chars, int, >= 1: maximum character count.

    Returns:
        truncated, str: original text or ellipsis-shortened text.
    """
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)] + "…"


def seconds_label(value: float) -> str:
    """
    Render seconds compactly for dense PDF table cells.

    Args:
        value, float, >= 0.0: elapsed seconds.

    Returns:
        label, str: seconds rounded to two decimals for small values, one decimal for larger values.
    """
    if value <= 0:
        return "0"
    if value < 10:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.1f}".rstrip("0").rstrip(".")


def count_label(value: float) -> str:
    """
    Render count-like metrics compactly.

    Args:
        value, float, >= 0.0: count value that may be averaged over repetitions.

    Returns:
        label, str: integer-like label or one decimal place for fractional averages.
    """
    rounded = round(value)
    if abs(value - rounded) < 0.05:
        return str(int(rounded))
    return f"{value:.1f}".rstrip("0").rstrip(".")


def rate_label(value: float) -> str:
    """
    Render rate-like metrics compactly.

    Args:
        value, float, >= 0.0: rate value.

    Returns:
        label, str: compact rate label.
    """
    if value <= 0:
        return "0"
    if value < 10:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if value < 100:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    return str(int(round(value)))


def percent_label(value: float | None) -> str:
    """
    Render a 0.0..1.0 rate as a dense table value.

    Args:
        value, float | None: quality rate or None when unavailable.

    Returns:
        label, str: percentage without the percent sign, or dash when unknown.
    """
    if value is None:
        return "-"
    return str(int(round(100 * value)))


def safe_divide(numerator: float, denominator: float) -> float:
    """
    Divide numeric values with a zero-denominator fallback.

    Args:
        numerator, float: numerator value.
        denominator, float: denominator value.

    Returns:
        quotient, float, >= 0.0: numerator / denominator or 0.0.
    """
    if denominator <= 0:
        return 0.0
    return max(0.0, numerator / denominator)


def parse_int(value: Any, default: int = 0) -> int:
    """
    Parse an integer value from CSV data.

    Args:
        value, Any: CSV string or numeric value.
        default, int: fallback value when parsing fails.

    Returns:
        parsed, int: parsed integer or default.
    """
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default


def load_summary_rows(summary_path: str | Path) -> list[dict[str, str]]:
    """
    Load summary.csv rows.

    Args:
        summary_path, str | Path: path to benchmark summary.csv.

    Returns:
        rows, list[dict[str, str]]: CSV rows preserving file order.
    """
    with Path(summary_path).open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def parse_float(value: Any, default: float = 0.0) -> float:
    """
    Parse a float value from CSV data.

    Args:
        value, Any: CSV string or numeric value.
        default, float: fallback value when parsing fails.

    Returns:
        parsed, float: parsed float or default.
    """
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def parse_bool_rate(value: Any) -> float | None:
    """
    Parse CSV truth values into numeric quality rates.

    Args:
        value, Any: CSV value such as True/False, 1/0, yes/no, or empty.

    Returns:
        rate, float | None: 1.0 for truthy, 0.0 for falsey, None when missing.
    """
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "pass", "passed"}:
        return 1.0
    if normalized in {"false", "0", "no", "n", "fail", "failed"}:
        return 0.0
    return None


def average_optional(values: list[float | None]) -> float | None:
    """
    Average optional numeric rates while ignoring unknown values.

    Args:
        values, list[float | None]: possibly missing rates.

    Returns:
        average_value, float | None: arithmetic mean of known values, or None.
    """
    known = [value for value in values if value is not None]
    if not known:
        return None
    return average(known)


def latest_bool_rate(rows: list[dict[str, str]], key: str) -> float | None:
    """
    Read the last available boolean rate from ordered agent-call rows.

    Args:
        rows, list[dict[str, str]]: rows for one logical attempt.
        key, str: boolean CSV field to inspect.

    Returns:
        rate, float | None: last parsed rate, or None when all rows are empty.
    """
    for row in reversed(rows):
        rate = parse_bool_rate(row.get(key))
        if rate is not None:
            return rate
    return None


def row_error_type(row: dict[str, str]) -> str:
    """
    Return a normalized error type from an agent call row.

    Args:
        row, dict[str, str]: agent_calls.csv row.

    Returns:
        error_type, str: normalized error type, or empty string when absent.
    """
    return str(row.get("error_type") or "").strip()


def row_is_timeout(row: dict[str, str]) -> bool:
    """
    Detect timeout-like failed calls from error type/message fields.

    Args:
        row, dict[str, str]: agent_calls.csv row.

    Returns:
        is_timeout, bool: True when the row looks like a timeout failure.
    """
    text = f"{row.get('error_type', '')} {row.get('error_message', '')}".lower()
    return "timeout" in text or "timed out" in text


def row_identity(row: dict[str, str]) -> tuple[str, str]:
    """
    Build a stable identity for one logical benchmark attempt.

    Args:
        row, dict[str, str]: summary.csv or agent_calls.csv row.

    Returns:
        identity, tuple[str, str]: run/repetition pair used to group per-call rows.
    """
    return (row.get("run_id", ""), row.get("repetition", ""))


def row_has_value(row: dict[str, str], key: str) -> bool:
    """
    Check whether a CSV row contains a non-empty value.

    Args:
        row, dict[str, str]: CSV row to inspect.
        key, str: field name to check.

    Returns:
        has_value, bool: True when the field exists and is not an empty string.
    """
    return row.get(key, "") not in ("", None)


def execution_value_for_role(row: dict[str, str], role: str | None = None) -> float:
    """
    Read no-load model execution seconds from a CSV row.

    Args:
        row, dict[str, str]: summary.csv or agent_calls.csv row.
        role, str | None: optional role filter; use Coder, Reviewer, or None for totals.

    Returns:
        seconds, float, >= 0.0: prompt-evaluation plus generation time, excluding model loading.
    """
    if role is not None and row.get("agent_role", "").lower() not in ("", role.lower()):
        return 0.0

    # agent_calls.csv stores Ollama's load_duration_s separately. The no-load
    # execution invariant is prompt_eval_duration_s + eval_duration_s.
    prompt_eval_s = parse_float(row.get("prompt_eval_duration_s"), 0.0)
    eval_s = parse_float(row.get("eval_duration_s"), 0.0)
    if prompt_eval_s or eval_s:
        return prompt_eval_s + eval_s

    if role is None:
        return parse_float(row.get("total_model_execution_s"), 0.0)

    normalized_role = role.lower()
    wallclock_s = parse_float(row.get(f"{normalized_role}_wallclock_s"), 0.0)
    load_s = parse_float(row.get(f"{normalized_role}_load_duration_s"), 0.0)
    return max(0.0, wallclock_s - load_s)


def token_value_for_role(row: dict[str, str], role: str) -> float:
    """
    Read the token value for one agent role from a CSV row.

    Args:
        row, dict[str, str]: summary.csv or agent_calls.csv row.
        role, str: role name, either Coder or Reviewer.

    Returns:
        tokens, float, >= 0.0: generated-token count when available, otherwise total role tokens.
    """
    normalized_role = role.lower()
    if row.get("agent_role", "").lower() == normalized_role:
        # Prefer generated tokens from agent_calls.csv. Older screenshots may
        # contain empty output_tokens, so fall back to used_tokens only when the
        # generated-token column is absent.
        if row_has_value(row, "output_tokens"):
            return parse_float(row.get("output_tokens"), 0.0)
        return parse_float(row.get("used_tokens"), 0.0)
    return parse_float(row.get(f"{normalized_role}_tokens"), 0.0)


def average(values: list[float]) -> float:
    """
    Average numeric values with a safe empty-list fallback.

    Args:
        values, list[float]: values to average.

    Returns:
        average_value, float: arithmetic mean, or 0.0 for an empty list.
    """
    return sum(values) / max(1, len(values))


def aggregate_summary_bucket(bucket: list[dict[str, str]]) -> OverviewCell:
    """
    Aggregate normal summary.csv rows for one task/experiment pair.

    Args:
        bucket, list[dict[str, str]]: rows sharing task_id and experiment_id.

    Returns:
        cell, OverviewCell: averaged rounds/max-rounds/token display data.
    """
    rounds_values = [parse_int(row.get("rounds_used"), 0) for row in bucket]
    max_values = [parse_int(row.get("max_rounds"), 1) for row in bucket]
    max_rounds = max(max_values) if max_values else 1
    stop_reasons = tuple(row.get("stop_reason", "") for row in bucket)
    return OverviewCell(
        rounds_used=average([float(value) for value in rounds_values]),
        max_rounds=max_rounds,
        stop_reasons=stop_reasons,
        repetitions=len(bucket),
        coder_tokens=average([token_value_for_role(row, "Coder") for row in bucket]),
        reviewer_tokens=average([token_value_for_role(row, "Reviewer") for row in bucket]),
        total_execution_s=average([execution_value_for_role(row) for row in bucket]),
        coder_execution_s=average([execution_value_for_role(row, "Coder") for row in bucket]),
        reviewer_execution_s=average([execution_value_for_role(row, "Reviewer") for row in bucket]),
        total_load_s=average([parse_float(row.get("total_load_duration_s"), 0.0) for row in bucket]),
        coder_load_s=average([parse_float(row.get("coder_load_duration_s"), 0.0) for row in bucket]),
        reviewer_load_s=average([parse_float(row.get("reviewer_load_duration_s"), 0.0) for row in bucket]),
        failed_calls=average([parse_float(row.get("model_call_failures"), 0.0) for row in bucket]),
        timeout_calls=average([1.0 if "timeout" in str(row.get("model_call_error_types", "")).lower() else 0.0 for row in bucket]),
        error_type_count=average([
            float(len([item for item in str(row.get("model_call_error_types", "")).split(";") if item]))
            for row in bucket
        ]),
        syntax_ok_rate=average_optional([parse_bool_rate(row.get("final_syntax_ok")) for row in bucket]),
        approval_rate=average_optional([parse_bool_rate(row.get("final_reviewer_approved")) for row in bucket]),
        evaluator_pass_rate=average_optional([parse_bool_rate(row.get("evaluator_passed")) for row in bucket]),
    )


def aggregate_agent_call_bucket(bucket: list[dict[str, str]]) -> OverviewCell:
    """
    Aggregate agent_calls.csv-style rows for one task/experiment pair.

    Args:
        bucket, list[dict[str, str]]: per-agent-call rows sharing task_id and experiment_id.

    Returns:
        cell, OverviewCell: display data derived from per-attempt round and token sums.
    """
    attempts: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in bucket:
        attempts.setdefault(row_identity(row), []).append(row)

    # agent_calls.csv contains one row per concrete Coder/Reviewer call. For
    # the overview matrix, those rows must collapse back into one benchmark
    # attempt; otherwise Coder+Reviewer calls from the same round look like
    # separate repetitions and distort R/TCT/TRT values.
    rounds_values = [max(parse_int(row.get("round_no"), 0) for row in rows) for rows in attempts.values()]
    coder_token_values = [sum(token_value_for_role(row, "Coder") for row in rows) for rows in attempts.values()]
    reviewer_token_values = [sum(token_value_for_role(row, "Reviewer") for row in rows) for rows in attempts.values()]
    coder_execution_values = [sum(execution_value_for_role(row, "Coder") for row in rows) for rows in attempts.values()]
    reviewer_execution_values = [sum(execution_value_for_role(row, "Reviewer") for row in rows) for rows in attempts.values()]
    total_execution_values = [coder_s + reviewer_s for coder_s, reviewer_s in zip(coder_execution_values, reviewer_execution_values)]
    coder_load_values = [sum(parse_float(row.get("load_duration_s"), 0.0) for row in rows if row.get("agent_role", "").lower() == "coder") for rows in attempts.values()]
    reviewer_load_values = [sum(parse_float(row.get("load_duration_s"), 0.0) for row in rows if row.get("agent_role", "").lower() == "reviewer") for rows in attempts.values()]
    total_load_values = [coder_s + reviewer_s for coder_s, reviewer_s in zip(coder_load_values, reviewer_load_values)]
    failed_values = [sum(1.0 for row in rows if parse_bool_rate(row.get("call_failed")) == 1.0) for rows in attempts.values()]
    timeout_values = [sum(1.0 for row in rows if row_is_timeout(row)) for rows in attempts.values()]
    error_type_count_values = [float(len({row_error_type(row) for row in rows if row_error_type(row)})) for rows in attempts.values()]
    syntax_values = [latest_bool_rate(rows, "syntax_ok_after_coder") for rows in attempts.values()]
    approval_values = [latest_bool_rate(rows, "reviewer_approved") for rows in attempts.values()]
    fallback_max_rounds = max(rounds_values) if rounds_values else 1
    max_values = [parse_int(row.get("max_rounds"), 0) for row in bucket if row_has_value(row, "max_rounds")]
    max_rounds = max(max_values) if max_values else fallback_max_rounds
    stop_reasons = tuple(row.get("stop_reason", "") for row in bucket if row_has_value(row, "stop_reason"))
    return OverviewCell(
        rounds_used=average([float(value) for value in rounds_values]),
        max_rounds=max(1, max_rounds),
        stop_reasons=stop_reasons,
        repetitions=len(attempts),
        coder_tokens=average(coder_token_values),
        reviewer_tokens=average(reviewer_token_values),
        total_execution_s=average(total_execution_values),
        coder_execution_s=average(coder_execution_values),
        reviewer_execution_s=average(reviewer_execution_values),
        total_load_s=average(total_load_values),
        coder_load_s=average(coder_load_values),
        reviewer_load_s=average(reviewer_load_values),
        failed_calls=average(failed_values),
        timeout_calls=average(timeout_values),
        error_type_count=average(error_type_count_values),
        syntax_ok_rate=average_optional(syntax_values),
        approval_rate=average_optional(approval_values),
        evaluator_pass_rate=None,
    )


def merge_token_cells(
    base_cells: dict[tuple[str, str], OverviewCell],
    token_cells: dict[tuple[str, str], OverviewCell],
) -> dict[tuple[str, str], OverviewCell]:
    """
    Copy token aggregates from agent call cells into summary overview cells.

    Args:
        base_cells, dict[tuple[str, str], OverviewCell]: cells derived from summary.csv.
        token_cells, dict[tuple[str, str], OverviewCell]: cells derived from agent_calls.csv.

    Returns:
        merged_cells, dict[tuple[str, str], OverviewCell]: summary cells enriched with Coder/Reviewer token totals.
    """
    merged: dict[tuple[str, str], OverviewCell] = {}
    for key, cell in base_cells.items():
        token_cell = token_cells.get(key)
        if token_cell is None:
            merged[key] = cell
            continue
        merged[key] = OverviewCell(
            rounds_used=cell.rounds_used,
            max_rounds=cell.max_rounds,
            stop_reasons=cell.stop_reasons,
            repetitions=cell.repetitions,
            coder_tokens=token_cell.coder_tokens,
            reviewer_tokens=token_cell.reviewer_tokens,
            total_execution_s=token_cell.total_execution_s,
            coder_execution_s=token_cell.coder_execution_s,
            reviewer_execution_s=token_cell.reviewer_execution_s,
            total_load_s=token_cell.total_load_s,
            coder_load_s=token_cell.coder_load_s,
            reviewer_load_s=token_cell.reviewer_load_s,
            failed_calls=token_cell.failed_calls,
            timeout_calls=token_cell.timeout_calls,
            error_type_count=token_cell.error_type_count,
            syntax_ok_rate=cell.syntax_ok_rate if cell.syntax_ok_rate is not None else token_cell.syntax_ok_rate,
            approval_rate=cell.approval_rate if cell.approval_rate is not None else token_cell.approval_rate,
            evaluator_pass_rate=cell.evaluator_pass_rate if cell.evaluator_pass_rate is not None else token_cell.evaluator_pass_rate,
        )
    return merged


def aggregate_overview(
    rows: list[dict[str, str]],
    agent_call_rows: list[dict[str, str]] | None = None,
) -> dict[tuple[str, str], OverviewCell]:
    """
    Aggregate CSV rows into task/experiment overview cells.

    Args:
        rows, list[dict[str, str]]: rows from summary.csv or agent_calls.csv.
        agent_call_rows, list[dict[str, str]] | None: optional agent_calls.csv rows for role token totals.

    Returns:
        cells, dict[tuple[str, str], OverviewCell]: mapping from (task_id, experiment_id) to display data.
    """
    buckets: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (row.get("task_id", ""), row.get("experiment_id", ""))
        buckets.setdefault(key, []).append(row)

    cells: dict[tuple[str, str], OverviewCell] = {}
    for key, bucket in buckets.items():
        if any(row_has_value(row, "rounds_used") for row in bucket):
            cells[key] = aggregate_summary_bucket(bucket)
        elif any(row_has_value(row, "round_no") for row in bucket):
            cells[key] = aggregate_agent_call_bucket(bucket)

    if agent_call_rows:
        token_cells = aggregate_overview(agent_call_rows)
        cells = merge_token_cells(cells, token_cells)
    return cells

def interpolate_color(start: tuple[float, float, float], end: tuple[float, float, float], ratio: float) -> tuple[float, float, float]:
    """
    Interpolate between two RGB colors.

    Args:
        start, tuple[float, float, float]: RGB color for ratio 0.0.
        end, tuple[float, float, float]: RGB color for ratio 1.0.
        ratio, float: interpolation ratio, clamped to 0.0..1.0.

    Returns:
        color, tuple[float, float, float]: interpolated RGB color.
    """
    clamped = min(1.0, max(0.0, ratio))
    return tuple(start[i] + (end[i] - start[i]) * clamped for i in range(3))


def cell_color(cell: OverviewCell | None) -> tuple[float, float, float]:
    """
    Choose a cell background color from stop reasons and round usage.

    Args:
        cell, OverviewCell | None: overview cell data, or None when missing.

    Returns:
        color, tuple[float, float, float]: RGB background color in range 0.0..1.0.
    """
    if cell is None:
        return (0.96, 0.96, 0.96)
    if "stagnation_detected" in cell.stop_reasons:
        return GRAY
    if "max_rounds_reached" in cell.stop_reasons:
        return BLUE
    if cell.max_rounds <= 1:
        ratio = 0.0
    else:
        ratio = (cell.rounds_used - 1) / (cell.max_rounds - 1)
    return interpolate_color(GREEN, RED, ratio)




@dataclass(frozen=True)
class TokenRange:
    """
    Min/max bounds for coloring cost cells such as tokens or seconds.

    Zero-value cells are handled separately as timeout/failure indicators and
    therefore are excluded from the positive minimum and maximum. The historic
    class name is kept because public tests import it directly.
    """

    minimum: float
    maximum: float


def build_token_range(values: list[float]) -> TokenRange:
    """
    Build a positive token range for green-to-red interpolation.

    Args:
        values, list[float]: token totals from all visible cells.

    Returns:
        token_range, TokenRange: positive minimum and maximum token totals.
    """
    positive_values = [value for value in values if value > 0]
    if not positive_values:
        return TokenRange(0.0, 0.0)
    return TokenRange(min(positive_values), max(positive_values))


def token_color(tokens: float, token_range: TokenRange) -> tuple[float, float, float]:
    """
    Choose a background color for token-consumption cells.

    Args:
        tokens, float, >= 0.0: token total for one R/TCT/TRT cell.
        token_range, TokenRange: global positive min/max for the token metric.

    Returns:
        color, tuple[float, float, float]: blue for zero tokens, otherwise green-to-red by relative cost.
    """
    if tokens <= 0:
        return BLUE
    if token_range.maximum <= token_range.minimum:
        ratio = 0.0
    else:
        ratio = (tokens - token_range.minimum) / (token_range.maximum - token_range.minimum)
    return interpolate_color(GREEN, RED, ratio)


def metric_color(value: float, metric_range: TokenRange) -> tuple[float, float, float]:
    """
    Choose a green-to-red background color for generic cost metrics.

    Args:
        value, float, >= 0.0: metric value such as seconds or tokens.
        metric_range, TokenRange: global positive min/max for the metric.

    Returns:
        color, tuple[float, float, float]: blue for zero, otherwise green-to-red by relative cost.
    """
    return token_color(value, metric_range)


def lower_is_better_color(value: float, metric_range: TokenRange) -> tuple[float, float, float]:
    """
    Color metrics where lower values are better and zero is a valid optimum.

    Args:
        value, float, >= 0.0: count or cost metric.
        metric_range, TokenRange: positive min/max for the metric.

    Returns:
        color, tuple[float, float, float]: green for zero/low values and red for high values.
    """
    if value <= 0:
        return GREEN
    if metric_range.maximum <= 0:
        return GREEN
    ratio = value / metric_range.maximum if metric_range.maximum else 0.0
    return interpolate_color(GREEN, RED, ratio)


def higher_is_better_color(
    value: float | None,
    metric_range: TokenRange,
    *,
    missing_color: tuple[float, float, float] = BLUE,
    zero_color: tuple[float, float, float] = BLUE,
) -> tuple[float, float, float]:
    """
    Color metrics where higher values are better.

    Args:
        value, float | None: quality or throughput value.
        metric_range, TokenRange: positive min/max for the metric.
        missing_color, tuple[float, float, float]: color used for missing values.
        zero_color, tuple[float, float, float]: color used for known zero values.

    Returns:
        color, tuple[float, float, float]: red-to-green by relative score, or missing_color.
    """
    if value is None:
        return missing_color
    if value <= 0:
        return zero_color
    if metric_range.maximum <= metric_range.minimum:
        ratio = 1.0
    else:
        ratio = (value - metric_range.minimum) / (metric_range.maximum - metric_range.minimum)
    return interpolate_color(RED, GREEN, ratio)


def token_ranges_for_cells(cells: dict[tuple[str, str], OverviewCell]) -> tuple[TokenRange, TokenRange]:
    """
    Build Coder and Reviewer token ranges from all overview cells.

    Args:
        cells, dict[tuple[str, str], OverviewCell]: overview matrix cells.

    Returns:
        ranges, tuple[TokenRange, TokenRange]: Coder-token and Reviewer-token ranges.
    """
    coder_range = build_token_range([cell.coder_tokens for cell in cells.values()])
    reviewer_range = build_token_range([cell.reviewer_tokens for cell in cells.values()])
    return coder_range, reviewer_range


def time_ranges_for_cells(cells: dict[tuple[str, str], OverviewCell]) -> tuple[TokenRange, TokenRange, TokenRange]:
    """
    Build no-load execution time ranges from all overview cells.

    Args:
        cells, dict[tuple[str, str], OverviewCell]: overview matrix cells.

    Returns:
        ranges, tuple[TokenRange, TokenRange, TokenRange]: TTNL, TTC, and TTR ranges.
    """
    total_range = build_token_range([cell.total_execution_s for cell in cells.values()])
    coder_range = build_token_range([cell.coder_execution_s for cell in cells.values()])
    reviewer_range = build_token_range([cell.reviewer_execution_s for cell in cells.values()])
    return total_range, coder_range, reviewer_range


def load_ranges_for_cells(cells: dict[tuple[str, str], OverviewCell]) -> tuple[TokenRange, TokenRange, TokenRange]:
    """
    Build model loading time ranges from all overview cells.

    Args:
        cells, dict[tuple[str, str], OverviewCell]: overview matrix cells.

    Returns:
        ranges, tuple[TokenRange, TokenRange, TokenRange]: TTL, TLC, and TLR ranges.
    """
    total_range = build_token_range([cell.total_load_s for cell in cells.values()])
    coder_range = build_token_range([cell.coder_load_s for cell in cells.values()])
    reviewer_range = build_token_range([cell.reviewer_load_s for cell in cells.values()])
    return total_range, coder_range, reviewer_range


def tps_ranges_for_cells(cells: dict[tuple[str, str], OverviewCell]) -> tuple[TokenRange, TokenRange, TokenRange]:
    """
    Build generated-token throughput ranges from all overview cells.

    Args:
        cells, dict[tuple[str, str], OverviewCell]: overview matrix cells.

    Returns:
        ranges, tuple[TokenRange, TokenRange, TokenRange]: ATPS, CTPS, and RTPS ranges.
    """
    combined_range = build_token_range([cell.combined_tps for cell in cells.values()])
    coder_range = build_token_range([cell.coder_tps for cell in cells.values()])
    reviewer_range = build_token_range([cell.reviewer_tps for cell in cells.values()])
    return combined_range, coder_range, reviewer_range


def reliability_ranges_for_cells(cells: dict[tuple[str, str], OverviewCell]) -> tuple[TokenRange, TokenRange, TokenRange]:
    """
    Build failure-count ranges from all overview cells.

    Args:
        cells, dict[tuple[str, str], OverviewCell]: overview matrix cells.

    Returns:
        ranges, tuple[TokenRange, TokenRange, TokenRange]: failed call, timeout, and error-type ranges.
    """
    failed_range = build_token_range([cell.failed_calls for cell in cells.values()])
    timeout_range = build_token_range([cell.timeout_calls for cell in cells.values()])
    error_range = build_token_range([cell.error_type_count for cell in cells.values()])
    return failed_range, timeout_range, error_range


def quality_ranges_for_cells(cells: dict[tuple[str, str], OverviewCell]) -> tuple[TokenRange, TokenRange, TokenRange]:
    """
    Build quality-indicator ranges from all overview cells.

    Args:
        cells, dict[tuple[str, str], OverviewCell]: overview matrix cells.

    Returns:
        ranges, tuple[TokenRange, TokenRange, TokenRange]: syntax, approval, and evaluator ranges.
    """
    syntax_range = build_token_range([cell.syntax_ok_rate or 0.0 for cell in cells.values()])
    approval_range = build_token_range([cell.approval_rate or 0.0 for cell in cells.values()])
    evaluator_range = build_token_range([cell.evaluator_pass_rate or 0.0 for cell in cells.values()])
    return syntax_range, approval_range, evaluator_range


def efficiency_ranges_for_cells(cells: dict[tuple[str, str], OverviewCell]) -> tuple[TokenRange, TokenRange, TokenRange]:
    """
    Build efficiency ranges from all overview cells.

    Args:
        cells, dict[tuple[str, str], OverviewCell]: overview matrix cells.

    Returns:
        ranges, tuple[TokenRange, TokenRange, TokenRange]: quality, quality/second, and quality/1k-token ranges.
    """
    quality_range = build_token_range([cell.quality_score or 0.0 for cell in cells.values()])
    qps_range = build_token_range([cell.quality_per_second for cell in cells.values()])
    qpk_range = build_token_range([cell.quality_per_1k_tokens for cell in cells.values()])
    return quality_range, qps_range, qpk_range


def all_metric_ranges(cells: dict[tuple[str, str], OverviewCell]) -> dict[str, tuple[TokenRange, ...]]:
    """
    Build all PDF table color ranges in one place.

    Args:
        cells, dict[tuple[str, str], OverviewCell]: overview matrix cells.

    Returns:
        ranges, dict[str, tuple[TokenRange, ...]]: color ranges keyed by table kind.
    """
    return {
        "tokens": token_ranges_for_cells(cells),
        "times": time_ranges_for_cells(cells),
        "loads": load_ranges_for_cells(cells),
        "tps": tps_ranges_for_cells(cells),
        "reliability": reliability_ranges_for_cells(cells),
        "quality": quality_ranges_for_cells(cells),
        "efficiency": efficiency_ranges_for_cells(cells),
    }


def ordered_values(rows: list[dict[str, str]], key: str) -> list[str]:
    """
    Return unique CSV values in first-seen order.

    Args:
        rows, list[dict[str, str]]: CSV rows.
        key, str: field name to read.

    Returns:
        values, list[str]: unique non-empty values preserving input order.
    """
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        value = row.get(key, "")
        if value and value not in seen:
            values.append(value)
            seen.add(value)
    return values


def draw_legend_item(
    commands: list[str],
    x: float,
    y: float,
    color: tuple[float, float, float],
    label: str,
) -> float:
    """
    Draw one colored legend swatch and label.

    Args:
        commands, list[str]: PDF command list to append to.
        x, float: left coordinate in points.
        y, float: bottom coordinate in points.
        color, tuple[float, float, float]: RGB swatch color.
        label, str: legend label next to the swatch.

    Returns:
        next_x, float: recommended x coordinate for the following legend item.
    """
    swatch_size = 7.0
    commands.append(fill_rect_command(x, y, swatch_size, swatch_size, color))
    commands.append(stroke_rect_command(x, y, swatch_size, swatch_size))
    commands.append(text_command(x + swatch_size + 3, y + 1, label, size=6))
    return x + swatch_size + 5 + len(label) * 3.1


def draw_color_legend(
    commands: list[str],
    x: float,
    y: float,
    *,
    green_label: str = "green: 1 round / min tokens",
    red_label: str = "red: max rounds / max tokens",
    gray_label: str | None = "gray: stagnation",
    blue_label: str = "blue: max rounds / 0 tokens",
) -> None:
    """
    Draw the PDF color legend with actual color samples.

    Args:
        commands, list[str]: PDF command list to append to.
        x, float: left coordinate in points.
        y, float: bottom coordinate in points.
        green_label, str: explanation for green cells.
        red_label, str: explanation for red cells.
        gray_label, str | None: optional explanation for gray cells.
        blue_label, str: explanation for blue cells.

    Returns:
        None.
    """
    next_x = draw_legend_item(commands, x, y, GREEN, green_label)
    next_x = draw_legend_item(commands, next_x, y, RED, red_label)
    if gray_label:
        next_x = draw_legend_item(commands, next_x, y, GRAY, gray_label)
    draw_legend_item(commands, next_x, y, BLUE, blue_label)


def draw_subcell(
    commands: list[str],
    x: float,
    y: float,
    width: float,
    label: str,
    color: tuple[float, float, float],
    *,
    size: int = BODY_FONT_SIZE,
) -> None:
    """
    Draw one colored metric subcell with a visible label.

    Args:
        commands, list[str]: PDF command list to append to.
        x, float: left coordinate in points.
        y, float: bottom coordinate in points.
        width, float: subcell width in points.
        label, str: text to draw in the subcell.
        color, tuple[float, float, float]: RGB background color.
        size, int: text size in points.

    Returns:
        None.
    """
    commands.append(fill_rect_command(x, y, width, ROW_HEIGHT, color))
    commands.append(stroke_rect_command(x, y, width, ROW_HEIGHT))
    commands.append(text_command(x + 3, y + 6, label, size=size))


def choose_landscape_page_size(column_count: int) -> tuple[str, float, float]:
    """
    Choose a DIN landscape page size from the number of visible table columns.

    Args:
        column_count, int, >= 0: number of task/experiment groups displayed as PDF columns.

    Returns:
        page_size, tuple[str, float, float]: DIN label plus width and height in PDF points.
    """
    if column_count >= 64:
        label = "A0"
    elif column_count >= 32:
        label = "A1"
    elif column_count >= 16:
        label = "A2"
    elif column_count > 8:
        label = "A3"
    else:
        label = "A4"
    width, height = PAGE_SIZES_LANDSCAPE[label]
    return label, width, height


def draw_table_page(
    *,
    title: str,
    rows: list[str],
    columns: list[str],
    cells: dict[tuple[str, str], OverviewCell],
    token_ranges: tuple[TokenRange, TokenRange],
    time_ranges: tuple[TokenRange, TokenRange, TokenRange] | None = None,
    metric_ranges: dict[str, tuple[TokenRange, ...]] | None = None,
    table_kind: str = "tokens",
    page_number: int,
    total_pages_hint: int,
    transpose: bool = False,
    page_width: float = PAGE_WIDTH,
    page_height: float = PAGE_HEIGHT,
) -> list[str]:
    """
    Draw one paginated overview table page.

    Args:
        title, str: report title.
        rows, list[str]: row labels included on this page.
        columns, list[str]: column labels included on this page.
        cells, dict[tuple[str, str], OverviewCell]: task/experiment matrix values.
        token_ranges, tuple[TokenRange, TokenRange]: Coder and Reviewer token color ranges.
        time_ranges, tuple[TokenRange, TokenRange, TokenRange] | None: backwards-compatible total/Coder/Reviewer time color ranges.
        metric_ranges, dict[str, tuple[TokenRange, ...]] | None: color ranges keyed by PDF table kind.
        table_kind, str: metric table kind to draw.
        page_number, int, >= 1: current page index.
        total_pages_hint, int, >= 1: total generated pages for footer display.
        transpose, bool: when True, experiments are rows and task ids are columns.
        page_width, float: PDF page width in points.
        page_height, float: PDF page height in points.

    Returns:
        commands, list[str]: PDF drawing commands for the page.
    """
    commands: list[str] = []
    metric_ranges = metric_ranges or {
        "tokens": token_ranges,
        "times": time_ranges
        or (
            TokenRange(0.0, 0.0),
            TokenRange(0.0, 0.0),
            TokenRange(0.0, 0.0),
        ),
    }
    current_ranges = metric_ranges.get(table_kind, (TokenRange(0.0, 0.0),) * 3)
    table_specs = {
        "tokens": (
            SUB_COLUMNS,
            "Overview: R=rounds_used/max_rounds, TCT=Coder generated tokens, TRT=Reviewer generated tokens",
            ("green: 1 round / min tokens", "red: max rounds / max tokens", "gray: stagnation", "blue: max rounds / 0 tokens"),
        ),
        "times": (
            TIME_SUB_COLUMNS,
            "Timing: TTNL=Coder+Reviewer execution time without model loading, TTC=Coder execution, TTR=Reviewer execution",
            ("green: min execution time", "red: max execution time", None, "blue: 0 execution time"),
        ),
        "loads": (
            LOAD_SUB_COLUMNS,
            "Loading: TTL=total model load time, TLC=Coder load time, TLR=Reviewer load time",
            ("green: min load time", "red: max load time", None, "blue: 0 load time"),
        ),
        "tps": (
            TPS_SUB_COLUMNS,
            "Throughput: ATPS=all generated tokens/sec, CTPS=Coder tokens/sec, RTPS=Reviewer tokens/sec",
            ("green: max throughput", "red: min throughput", None, "blue: 0 throughput"),
        ),
        "reliability": (
            RELIABILITY_SUB_COLUMNS,
            "Reliability: FC=failed calls, TO=timeout calls, ERR=distinct error types",
            ("green: no failures", "red: most failures", None, "blue: unused"),
        ),
        "quality": (
            QUALITY_SUB_COLUMNS,
            "Quality: SYN=syntax ok rate, APP=reviewer approval rate, EVAL=evaluator pass rate",
            ("green: best quality", "red: worst quality", "gray: unknown", "blue: unused"),
        ),
        "efficiency": (
            EFFICIENCY_SUB_COLUMNS,
            "Efficiency: Q=quality score, QPS=quality/sec, QPK=quality per 1k generated tokens",
            ("green: best efficiency", "red: worst efficiency", "gray: unknown", "blue: zero efficiency"),
        ),
    }
    sub_columns, overview_text, legend_labels = table_specs.get(table_kind, table_specs["tokens"])

    commands.append(text_command(MARGIN, page_height - 24, title, size=TITLE_FONT_SIZE))
    commands.append(text_command(MARGIN, page_height - 40, overview_text, size=8))
    draw_color_legend(
        commands,
        MARGIN,
        page_height - 58,
        green_label=legend_labels[0],
        red_label=legend_labels[1],
        gray_label=legend_labels[2],
        blue_label=legend_labels[3],
    )

    available_width = page_width - 2 * MARGIN - TASK_COL_WIDTH
    group_width = min(
        MAX_EXPERIMENT_GROUP_WIDTH,
        max(MIN_EXPERIMENT_GROUP_WIDTH, available_width / max(1, len(columns))),
    )
    sub_width = group_width / len(sub_columns)
    table_top = page_height - 94
    header_y = table_top - ROW_HEIGHT
    info_y = header_y - ROW_HEIGHT

    commands.append(fill_rect_command(MARGIN, header_y, TASK_COL_WIDTH, ROW_HEIGHT, (0.88, 0.88, 0.88)))
    commands.append(stroke_rect_command(MARGIN, header_y, TASK_COL_WIDTH, ROW_HEIGHT))
    row_header = "experiment_id" if transpose else "task_id"
    commands.append(text_command(MARGIN + 4, header_y + 6, row_header, size=HEADER_FONT_SIZE))
    commands.append(fill_rect_command(MARGIN, info_y, TASK_COL_WIDTH, ROW_HEIGHT, (0.94, 0.94, 0.94)))
    commands.append(stroke_rect_command(MARGIN, info_y, TASK_COL_WIDTH, ROW_HEIGHT))
    commands.append(text_command(MARGIN + 4, info_y + 6, "Info", size=HEADER_FONT_SIZE))

    for col_idx, column_label in enumerate(columns):
        group_x = MARGIN + TASK_COL_WIDTH + col_idx * group_width
        commands.append(fill_rect_command(group_x, header_y, group_width, ROW_HEIGHT, (0.88, 0.88, 0.88)))
        commands.append(stroke_rect_command(group_x, header_y, group_width, ROW_HEIGHT))
        commands.append(text_command(group_x + 3, header_y + 6, truncate_text(column_label, 18), size=HEADER_FONT_SIZE))
        for sub_idx, sub_label in enumerate(sub_columns):
            sub_x = group_x + sub_idx * sub_width
            commands.append(fill_rect_command(sub_x, info_y, sub_width, ROW_HEIGHT, (0.94, 0.94, 0.94)))
            commands.append(stroke_rect_command(sub_x, info_y, sub_width, ROW_HEIGHT))
            commands.append(text_command(sub_x + 3, info_y + 6, sub_label, size=HEADER_FONT_SIZE))

    for row_idx, row_label in enumerate(rows):
        y = info_y - (row_idx + 1) * ROW_HEIGHT
        commands.append(fill_rect_command(MARGIN, y, TASK_COL_WIDTH, ROW_HEIGHT, (0.98, 0.98, 0.98)))
        commands.append(stroke_rect_command(MARGIN, y, TASK_COL_WIDTH, ROW_HEIGHT))
        commands.append(text_command(MARGIN + 4, y + 6, truncate_text(row_label, 28), size=BODY_FONT_SIZE))
        for col_idx, column_label in enumerate(columns):
            group_x = MARGIN + TASK_COL_WIDTH + col_idx * group_width
            cell_key = (column_label, row_label) if transpose else (row_label, column_label)
            cell = cells.get(cell_key)
            if cell and table_kind == "times":
                labels = (cell.total_execution_label(), cell.coder_execution_label(), cell.reviewer_execution_label())
                colors = (
                    metric_color(cell.total_execution_s, current_ranges[0]),
                    metric_color(cell.coder_execution_s, current_ranges[1]),
                    metric_color(cell.reviewer_execution_s, current_ranges[2]),
                )
            elif cell and table_kind == "loads":
                labels = (cell.total_load_label(), cell.coder_load_label(), cell.reviewer_load_label())
                colors = (
                    metric_color(cell.total_load_s, current_ranges[0]),
                    metric_color(cell.coder_load_s, current_ranges[1]),
                    metric_color(cell.reviewer_load_s, current_ranges[2]),
                )
            elif cell and table_kind == "tps":
                labels = (cell.combined_tps_label(), cell.coder_tps_label(), cell.reviewer_tps_label())
                colors = (
                    higher_is_better_color(cell.combined_tps, current_ranges[0]),
                    higher_is_better_color(cell.coder_tps, current_ranges[1]),
                    higher_is_better_color(cell.reviewer_tps, current_ranges[2]),
                )
            elif cell and table_kind == "reliability":
                labels = (cell.failed_calls_label(), cell.timeout_calls_label(), cell.error_type_count_label())
                colors = (
                    lower_is_better_color(cell.failed_calls, current_ranges[0]),
                    lower_is_better_color(cell.timeout_calls, current_ranges[1]),
                    lower_is_better_color(cell.error_type_count, current_ranges[2]),
                )
            elif cell and table_kind == "quality":
                labels = (cell.syntax_rate_label(), cell.approval_rate_label(), cell.evaluator_pass_rate_label())
                colors = (
                    higher_is_better_color(cell.syntax_ok_rate, current_ranges[0], missing_color=GRAY, zero_color=RED),
                    higher_is_better_color(cell.approval_rate, current_ranges[1], missing_color=GRAY, zero_color=RED),
                    higher_is_better_color(cell.evaluator_pass_rate, current_ranges[2], missing_color=GRAY, zero_color=RED),
                )
            elif cell and table_kind == "efficiency":
                labels = (cell.quality_score_label(), cell.quality_per_second_label(), cell.quality_per_1k_tokens_label())
                colors = (
                    higher_is_better_color(cell.quality_score, current_ranges[0], missing_color=GRAY, zero_color=RED),
                    higher_is_better_color(cell.quality_per_second, current_ranges[1]),
                    higher_is_better_color(cell.quality_per_1k_tokens, current_ranges[2]),
                )
            elif cell:
                labels = (cell.rounds_label, cell.coder_tokens_label(), cell.reviewer_tokens_label())
                colors = (
                    cell_color(cell),
                    token_color(cell.coder_tokens, current_ranges[0]),
                    token_color(cell.reviewer_tokens, current_ranges[1]),
                )
            else:
                labels = ("", "", "")
                colors = (cell_color(None), cell_color(None), cell_color(None))
            for sub_idx, (label, color) in enumerate(zip(labels, colors)):
                draw_subcell(commands, group_x + sub_idx * sub_width, y, sub_width, label, color)

    table_bottom = info_y - len(rows) * ROW_HEIGHT
    table_top_line = header_y + ROW_HEIGHT
    for col_idx in range(1, len(columns)):
        separator_x = MARGIN + TASK_COL_WIDTH + col_idx * group_width
        commands.append(line_command(separator_x, table_bottom, separator_x, table_top_line, width=1.0))

    footer = f"Page {page_number}/{total_pages_hint}"
    commands.append(text_command(page_width - MARGIN - 70, 16, footer, size=7))
    return commands

def generate_overview_pdf(
    summary_path: str | Path,
    output_path: str | Path,
    *,
    title: str = "Agentic Benchmark Report",
    agent_calls_path: str | Path | None = None,
    transpose: bool = False,
) -> Path:
    """
    Generate an overview PDF from summary.csv and optional agent_calls.csv.

    Args:
        summary_path, str | Path: path to summary.csv produced by the benchmark runner.
        output_path, str | Path: destination PDF path.
        title, str: document title printed on each page.
        agent_calls_path, str | Path | None: optional per-call CSV used for token, timing, loading, throughput, reliability, and partial quality aggregation.
        transpose, bool: when True, experiments are rows and task ids are columns.

    Returns:
        output_path, Path: written PDF path.
    """
    rows = load_summary_rows(summary_path)
    if not rows:
        raise ValueError(f"No rows found in summary CSV: {summary_path}")

    agent_call_rows = load_summary_rows(agent_calls_path) if agent_calls_path else None
    tasks = ordered_values(rows, "task_id")
    experiments = ordered_values(rows, "experiment_id")
    if not tasks or not experiments:
        raise ValueError("summary.csv must contain non-empty task_id and experiment_id values")
    cells = aggregate_overview(rows, agent_call_rows=agent_call_rows)
    metric_ranges = all_metric_ranges(cells)
    token_ranges = metric_ranges["tokens"]  # Kept for draw_table_page backwards-compatible arguments.
    time_ranges = metric_ranges["times"]
    table_kinds = ("tokens", "times", "loads", "tps", "reliability", "quality", "efficiency")

    row_values = experiments if transpose else tasks
    column_values = tasks if transpose else experiments
    _, page_width, page_height = choose_landscape_page_size(len(column_values))

    available_width = page_width - 2 * MARGIN - TASK_COL_WIDTH
    columns_per_page = max(1, int(available_width // MIN_EXPERIMENT_GROUP_WIDTH))
    rows_per_page = max(1, int((page_height - 134) // ROW_HEIGHT))
    column_chunks = [column_values[i : i + columns_per_page] for i in range(0, len(column_values), columns_per_page)]
    row_chunks = [row_values[i : i + rows_per_page] for i in range(0, len(row_values), rows_per_page)]
    total_pages = max(1, len(column_chunks) * len(row_chunks) * len(table_kinds))

    pdf = SimplePdf(page_width=page_width, page_height=page_height)
    page_number = 1
    for table_kind in table_kinds:
        for column_chunk in column_chunks:
            for row_chunk in row_chunks:
                pdf.add_page(
                    draw_table_page(
                        title=title,
                        rows=row_chunk,
                        columns=column_chunk,
                        cells=cells,
                        token_ranges=token_ranges,
                        time_ranges=time_ranges,
                        metric_ranges=metric_ranges,
                        table_kind=table_kind,
                        page_number=page_number,
                        total_pages_hint=total_pages,
                        transpose=transpose,
                        page_width=page_width,
                        page_height=page_height,
                    )
                )
                page_number += 1

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf.write(output)
    return output
