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
MIN_EXPERIMENT_COL_WIDTH = 70.0
MAX_EXPERIMENT_COL_WIDTH = 118.0


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

    @property
    def label(self) -> str:
        """
        Render the visible cell label.

        Returns:
            label, str: rounds_used/max_rounds, including n when repetitions > 1.
        """
        rounds = int(self.rounds_used) if self.rounds_used.is_integer() else round(self.rounds_used, 1)
        suffix = f" n={self.repetitions}" if self.repetitions > 1 else ""
        return f"{rounds}/{self.max_rounds}{suffix}"


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


def aggregate_summary_bucket(bucket: list[dict[str, str]]) -> OverviewCell:
    """
    Aggregate normal summary.csv rows for one task/experiment pair.

    Args:
        bucket, list[dict[str, str]]: rows sharing task_id and experiment_id.

    Returns:
        cell, OverviewCell: averaged rounds/max-rounds display data.
    """
    rounds_values = [parse_int(row.get("rounds_used"), 0) for row in bucket]
    max_values = [parse_int(row.get("max_rounds"), 1) for row in bucket]
    rounds_avg = sum(rounds_values) / max(1, len(rounds_values))
    max_rounds = max(max_values) if max_values else 1
    stop_reasons = tuple(row.get("stop_reason", "") for row in bucket)
    return OverviewCell(
        rounds_used=rounds_avg,
        max_rounds=max_rounds,
        stop_reasons=stop_reasons,
        repetitions=len(bucket),
    )


def aggregate_agent_call_bucket(bucket: list[dict[str, str]]) -> OverviewCell:
    """
    Aggregate agent_calls.csv-style rows for one task/experiment pair.

    Args:
        bucket, list[dict[str, str]]: per-agent-call rows sharing task_id and experiment_id.

    Returns:
        cell, OverviewCell: display data derived from the maximum round_no per logical attempt.
    """
    attempts: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in bucket:
        attempts.setdefault(row_identity(row), []).append(row)

    # agent_calls.csv contains one row per concrete Coder/Reviewer call. For
    # the overview matrix, those rows must collapse back into one benchmark
    # attempt; otherwise Coder+Reviewer calls from the same round look like
    # separate repetitions and distort the label.
    rounds_values = [max(parse_int(row.get("round_no"), 0) for row in rows) for rows in attempts.values()]
    fallback_max_rounds = max(rounds_values) if rounds_values else 1
    max_values = [parse_int(row.get("max_rounds"), 0) for row in bucket if row_has_value(row, "max_rounds")]
    max_rounds = max(max_values) if max_values else fallback_max_rounds
    stop_reasons = tuple(row.get("stop_reason", "") for row in bucket if row_has_value(row, "stop_reason"))
    rounds_avg = sum(rounds_values) / max(1, len(rounds_values))
    return OverviewCell(
        rounds_used=rounds_avg,
        max_rounds=max(1, max_rounds),
        stop_reasons=stop_reasons,
        repetitions=len(attempts),
    )


def aggregate_overview(rows: list[dict[str, str]]) -> dict[tuple[str, str], OverviewCell]:
    """
    Aggregate CSV rows into task/experiment overview cells.

    Args:
        rows, list[dict[str, str]]: rows from summary.csv or agent_calls.csv.

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


def draw_table_page(
    *,
    title: str,
    tasks: list[str],
    experiments: list[str],
    cells: dict[tuple[str, str], OverviewCell],
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
        page_number, int, >= 1: current page index.
        total_pages_hint, int, >= 1: total generated pages for footer display.

    Returns:
        commands, list[str]: PDF drawing commands for the page.
    """
    commands: list[str] = []
    commands.append(text_command(MARGIN, PAGE_HEIGHT - 24, title, size=TITLE_FONT_SIZE))
    commands.append(text_command(MARGIN, PAGE_HEIGHT - 40, "Overview: rounds_used / max_rounds", size=9))
    commands.append(
        text_command(
            MARGIN,
            PAGE_HEIGHT - 53,
            "Color: green=1 round, red=max rounds, gray=stagnation_detected, blue=max_rounds_reached",
            size=7,
        )
    )

    available_width = PAGE_WIDTH - 2 * MARGIN - TASK_COL_WIDTH
    experiment_width = min(MAX_EXPERIMENT_COL_WIDTH, max(MIN_EXPERIMENT_COL_WIDTH, available_width / max(1, len(experiments))))
    table_top = PAGE_HEIGHT - 76
    header_y = table_top - ROW_HEIGHT

    commands.append(fill_rect_command(MARGIN, header_y, TASK_COL_WIDTH, ROW_HEIGHT, (0.88, 0.88, 0.88)))
    commands.append(stroke_rect_command(MARGIN, header_y, TASK_COL_WIDTH, ROW_HEIGHT))
    commands.append(text_command(MARGIN + 4, header_y + 6, "task_id", size=HEADER_FONT_SIZE))

    for col_idx, experiment in enumerate(experiments):
        x = MARGIN + TASK_COL_WIDTH + col_idx * experiment_width
        commands.append(fill_rect_command(x, header_y, experiment_width, ROW_HEIGHT, (0.88, 0.88, 0.88)))
        commands.append(stroke_rect_command(x, header_y, experiment_width, ROW_HEIGHT))
        commands.append(text_command(x + 3, header_y + 6, truncate_text(experiment, 16), size=HEADER_FONT_SIZE))

    for row_idx, task_id in enumerate(tasks):
        y = header_y - (row_idx + 1) * ROW_HEIGHT
        commands.append(fill_rect_command(MARGIN, y, TASK_COL_WIDTH, ROW_HEIGHT, (0.98, 0.98, 0.98)))
        commands.append(stroke_rect_command(MARGIN, y, TASK_COL_WIDTH, ROW_HEIGHT))
        commands.append(text_command(MARGIN + 4, y + 6, truncate_text(task_id, 28), size=BODY_FONT_SIZE))
        for col_idx, experiment in enumerate(experiments):
            x = MARGIN + TASK_COL_WIDTH + col_idx * experiment_width
            cell = cells.get((task_id, experiment))
            commands.append(fill_rect_command(x, y, experiment_width, ROW_HEIGHT, cell_color(cell)))
            commands.append(stroke_rect_command(x, y, experiment_width, ROW_HEIGHT))
            commands.append(text_command(x + 4, y + 6, cell.label if cell else "", size=BODY_FONT_SIZE))

    footer = f"Page {page_number}/{total_pages_hint}"
    commands.append(text_command(PAGE_WIDTH - MARGIN - 70, 16, footer, size=7))
    return commands


def generate_overview_pdf(summary_path: str | Path, output_path: str | Path, *, title: str = "Agentic Benchmark Report") -> Path:
    """
    Generate an overview PDF from summary.csv.

    Args:
        summary_path, str | Path: path to summary.csv produced by the benchmark runner.
        output_path, str | Path: destination PDF path.
        title, str: document title printed on each page.

    Returns:
        output_path, Path: written PDF path.
    """
    rows = load_summary_rows(summary_path)
    if not rows:
        raise ValueError(f"No rows found in summary CSV: {summary_path}")

    tasks = ordered_values(rows, "task_id")
    experiments = ordered_values(rows, "experiment_id")
    if not tasks or not experiments:
        raise ValueError("summary.csv must contain non-empty task_id and experiment_id values")
    cells = aggregate_overview(rows)

    available_width = PAGE_WIDTH - 2 * MARGIN - TASK_COL_WIDTH
    experiments_per_page = max(1, int(available_width // MIN_EXPERIMENT_COL_WIDTH))
    rows_per_page = max(1, int((PAGE_HEIGHT - 116) // ROW_HEIGHT))
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
                    page_number=page_number,
                    total_pages_hint=total_pages,
                )
            )
            page_number += 1

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf.write(output)
    return output
