import csv
import tempfile
import unittest
from pathlib import Path

from agentic_benchmark.reporting.pdf import aggregate_overview, generate_overview_pdf, text_command


class PdfReportTests(unittest.TestCase):
    """Tests for the dependency-free benchmark overview PDF renderer."""

    def test_text_command_resets_text_color_to_black(self):
        """Verify text remains visible after colored table backgrounds are drawn."""
        command = text_command(1, 2, "visible")
        self.assertTrue(command.startswith("0 0 0 rg BT"))
        self.assertIn("visible", command)

    def test_agent_call_rows_are_aggregated_into_visible_cells(self):
        """Verify agent_calls.csv-style rows produce task/experiment labels and round values."""
        rows = [
            {
                "run_id": "20260607_103907_538776",
                "experiment_id": "qwen_self_review",
                "task_id": "HumanEval/0",
                "repetition": "1",
                "round_no": "1",
                "agent_role": "Coder",
            },
            {
                "run_id": "20260607_103907_538776",
                "experiment_id": "qwen_self_review",
                "task_id": "HumanEval/0",
                "repetition": "1",
                "round_no": "1",
                "agent_role": "Reviewer",
            },
            {
                "run_id": "20260607_103945_261855",
                "experiment_id": "qwen_no_review",
                "task_id": "HumanEval/0",
                "repetition": "1",
                "round_no": "1",
                "agent_role": "Coder",
            },
        ]
        cells = aggregate_overview(rows)
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].label, "1/1")
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].repetitions, 1)
        self.assertEqual(cells[("HumanEval/0", "qwen_no_review")].label, "1/1")

    def test_generated_pdf_contains_headers_and_cell_labels_for_agent_calls(self):
        """Verify a PDF generated from agent call rows contains visible table text commands."""
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "agent_calls.csv"
            output_path = Path(tmp) / "overview.pdf"
            fieldnames = ["run_id", "experiment_id", "task_id", "repetition", "round_no", "agent_role"]
            rows = [
                ["20260607_103907_538776", "qwen_self_review", "HumanEval/0", "1", "1", "Coder"],
                ["20260607_103907_538776", "qwen_self_review", "HumanEval/0", "1", "1", "Reviewer"],
                ["20260607_103945_261855", "qwen_no_review", "HumanEval/0", "1", "1", "Coder"],
            ]
            with summary_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(fieldnames)
                writer.writerows(rows)

            generate_overview_pdf(summary_path, output_path)
            pdf_text = output_path.read_text(encoding="latin-1")

        self.assertIn("(task_id)", pdf_text)
        self.assertIn("(HumanEval/0)", pdf_text)
        self.assertIn("(qwen_self_review)", pdf_text)
        self.assertIn("(qwen_no_review)", pdf_text)
        self.assertIn("(1/1)", pdf_text)


if __name__ == "__main__":
    unittest.main()
