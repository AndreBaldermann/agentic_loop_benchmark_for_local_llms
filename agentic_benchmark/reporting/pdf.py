from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PAGE_WIDTH = 842.0
PAGE_HEIGHT = 595.0
MARGIN = 28.0
TITLE_FONT_SIZE = 16
BODY_FONT_SIZE = 7
HEADER_FONT_SIZE = 7
ROW_HEIGHT = 18.0
TASK_COL_WIDTH = 150.0
MIN_EXPERIMENT_GROUP_WIDTH = 78.0
MAX_EXPERIMENT_GROUP_WIDTH = 132.0
SUB_COLUMNS = ("R", "TCT", "TRT")


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

    def __init__(self) -> None:
        """
        Initialize an empty PDF document.

        Args:
            None.
        """
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
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_WIDTH:.0f} {PAGE_HEIGHT:.0f}] "
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
        return (0.66, 0.66, 0.66)
    if "max_rounds_reached" in cell.stop_reasons:
        return (0.35, 0.60, 0.95)
    if cell.max_rounds <= 1:
        ratio = 0.0
    else:
        ratio = (cell.rounds_used - 1) / (cell.max_rounds - 1)
    return interpolate_color((0.35, 0.82, 0.35), (0.90, 0.25, 0.25), ratio)




@dataclass(frozen=True)
class TokenRange:
    """
    Min/max bounds for coloring token-consumption cells.

    Zero-token cells are handled separately as timeout/failure indicators and
    therefore are excluded from the positive minimum and maximum.
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
        return (0.35, 0.60, 0.95)
    if token_range.maximum <= token_range.minimum:
        ratio = 0.0
    else:
        ratio = (tokens - token_range.minimum) / (token_range.maximum - token_range.minimum)
    return interpolate_color((0.35, 0.82, 0.35), (0.90, 0.25, 0.25), ratio)


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


def draw_table_page(
    *,
    title: str,
    tasks: list[str],
    experiments: list[str],
    cells: dict[tuple[str, str], OverviewCell],
    token_ranges: tuple[TokenRange, TokenRange],
    page_number: int,
    total_pages_hint: int,
) -> list[str]:
    """
    Draw one paginated overview table page.

    Args:
        title, str: report title.
        tasks, list[str]: task ids included on this page.
        experiments, list[str]: experiment ids included on this page.
        cells, dict[tuple[str, str], OverviewCell]: task/experiment matrix values.
        token_ranges, tuple[TokenRange, TokenRange]: Coder and Reviewer token color ranges.
        page_number, int, >= 1: current page index.
        total_pages_hint, int, >= 1: total generated pages for footer display.

    Returns:
        commands, list[str]: PDF drawing commands for the page.
    """
    commands: list[str] = []
    coder_token_range, reviewer_token_range = token_ranges
    commands.append(text_command(MARGIN, PAGE_HEIGHT - 24, title, size=TITLE_FONT_SIZE))
    commands.append(text_command(MARGIN, PAGE_HEIGHT - 40, "Overview: R=rounds_used/max_rounds, TCT=Coder generated tokens, TRT=Reviewer generated tokens", size=8))
    commands.append(
        text_command(
            MARGIN,
            PAGE_HEIGHT - 53,
            "Color: R green=1 round, red=max rounds, gray=stagnation, blue=max rounds/zero tokens; TCT/TRT green=min tokens, red=max tokens",
            size=7,
        )
    )

    available_width = PAGE_WIDTH - 2 * MARGIN - TASK_COL_WIDTH
    group_width = min(
        MAX_EXPERIMENT_GROUP_WIDTH,
        max(MIN_EXPERIMENT_GROUP_WIDTH, available_width / max(1, len(experiments))),
    )
    sub_width = group_width / len(SUB_COLUMNS)
    table_top = PAGE_HEIGHT - 76
    header_y = table_top - ROW_HEIGHT
    info_y = header_y - ROW_HEIGHT

    commands.append(fill_rect_command(MARGIN, header_y, TASK_COL_WIDTH, ROW_HEIGHT, (0.88, 0.88, 0.88)))
    commands.append(stroke_rect_command(MARGIN, header_y, TASK_COL_WIDTH, ROW_HEIGHT))
    commands.append(text_command(MARGIN + 4, header_y + 6, "task_id", size=HEADER_FONT_SIZE))
    commands.append(fill_rect_command(MARGIN, info_y, TASK_COL_WIDTH, ROW_HEIGHT, (0.94, 0.94, 0.94)))
    commands.append(stroke_rect_command(MARGIN, info_y, TASK_COL_WIDTH, ROW_HEIGHT))
    commands.append(text_command(MARGIN + 4, info_y + 6, "Info", size=HEADER_FONT_SIZE))

    for col_idx, experiment in enumerate(experiments):
        group_x = MARGIN + TASK_COL_WIDTH + col_idx * group_width
        commands.append(fill_rect_command(group_x, header_y, group_width, ROW_HEIGHT, (0.88, 0.88, 0.88)))
        commands.append(stroke_rect_command(group_x, header_y, group_width, ROW_HEIGHT))
        commands.append(text_command(group_x + 3, header_y + 6, truncate_text(experiment, 18), size=HEADER_FONT_SIZE))
        for sub_idx, sub_label in enumerate(SUB_COLUMNS):
            sub_x = group_x + sub_idx * sub_width
            commands.append(fill_rect_command(sub_x, info_y, sub_width, ROW_HEIGHT, (0.94, 0.94, 0.94)))
            commands.append(stroke_rect_command(sub_x, info_y, sub_width, ROW_HEIGHT))
            commands.append(text_command(sub_x + 3, info_y + 6, sub_label, size=HEADER_FONT_SIZE))

    for row_idx, task_id in enumerate(tasks):
        y = info_y - (row_idx + 1) * ROW_HEIGHT
        commands.append(fill_rect_command(MARGIN, y, TASK_COL_WIDTH, ROW_HEIGHT, (0.98, 0.98, 0.98)))
        commands.append(stroke_rect_command(MARGIN, y, TASK_COL_WIDTH, ROW_HEIGHT))
        commands.append(text_command(MARGIN + 4, y + 6, truncate_text(task_id, 28), size=BODY_FONT_SIZE))
        for col_idx, experiment in enumerate(experiments):
            group_x = MARGIN + TASK_COL_WIDTH + col_idx * group_width
            cell = cells.get((task_id, experiment))
            labels = (cell.rounds_label, cell.coder_tokens_label(), cell.reviewer_tokens_label()) if cell else ("", "", "")
            colors = (
                cell_color(cell),
                token_color(cell.coder_tokens, coder_token_range) if cell else cell_color(None),
                token_color(cell.reviewer_tokens, reviewer_token_range) if cell else cell_color(None),
            )
            for sub_idx, (label, color) in enumerate(zip(labels, colors)):
                draw_subcell(commands, group_x + sub_idx * sub_width, y, sub_width, label, color)

    footer = f"Page {page_number}/{total_pages_hint}"
    commands.append(text_command(PAGE_WIDTH - MARGIN - 70, 16, footer, size=7))
    return commands

def generate_overview_pdf(
    summary_path: str | Path,
    output_path: str | Path,
    *,
    title: str = "Agentic Benchmark Report",
    agent_calls_path: str | Path | None = None,
) -> Path:
    """
    Generate an overview PDF from summary.csv and optional agent_calls.csv.

    Args:
        summary_path, str | Path: path to summary.csv produced by the benchmark runner.
        output_path, str | Path: destination PDF path.
        title, str: document title printed on each page.
        agent_calls_path, str | Path | None: optional per-call CSV used for R/TCT/TRT token aggregation.

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
    token_ranges = token_ranges_for_cells(cells)

    available_width = PAGE_WIDTH - 2 * MARGIN - TASK_COL_WIDTH
    experiments_per_page = max(1, int(available_width // MIN_EXPERIMENT_GROUP_WIDTH))
    rows_per_page = max(1, int((PAGE_HEIGHT - 134) // ROW_HEIGHT))
    experiment_chunks = [experiments[i : i + experiments_per_page] for i in range(0, len(experiments), experiments_per_page)]
    task_chunks = [tasks[i : i + rows_per_page] for i in range(0, len(tasks), rows_per_page)]
    total_pages = max(1, len(experiment_chunks) * len(task_chunks))

    pdf = SimplePdf()
    page_number = 1
    for experiment_chunk in experiment_chunks:
        for task_chunk in task_chunks:
            pdf.add_page(
                draw_table_page(
                    title=title,
                    tasks=task_chunk,
                    experiments=experiment_chunk,
                    cells=cells,
                    token_ranges=token_ranges,
                    page_number=page_number,
                    total_pages_hint=total_pages,
                )
            )
            page_number += 1

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf.write(output)
    return output
