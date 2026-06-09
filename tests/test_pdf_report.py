import csv
import tempfile
import unittest
from pathlib import Path

from agentic_benchmark.reporting.pdf import (
    TokenRange,
    aggregate_overview,
    choose_landscape_page_size,
    generate_overview_pdf,
    text_command,
    token_color,
)


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
                "output_tokens": "337",
                "prompt_eval_duration_s": "1.25",
                "eval_duration_s": "0.75",
                "load_duration_s": "0.50",
                "syntax_ok_after_coder": "True",
                "call_failed": "False",
            },
            {
                "run_id": "20260607_103907_538776",
                "experiment_id": "qwen_self_review",
                "task_id": "HumanEval/0",
                "repetition": "1",
                "round_no": "1",
                "agent_role": "Reviewer",
                "output_tokens": "83",
                "prompt_eval_duration_s": "0.40",
                "eval_duration_s": "0.10",
                "load_duration_s": "0.25",
                "reviewer_approved": "True",
                "call_failed": "False",
            },
            {
                "run_id": "20260607_103945_261855",
                "experiment_id": "qwen_no_review",
                "task_id": "HumanEval/0",
                "repetition": "1",
                "round_no": "1",
                "agent_role": "Coder",
                "output_tokens": "311",
                "prompt_eval_duration_s": "1.00",
                "eval_duration_s": "0.25",
                "load_duration_s": "0.20",
                "syntax_ok_after_coder": "False",
                "call_failed": "True",
                "error_type": "TimeoutError",
            },
        ]
        cells = aggregate_overview(rows)
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].label, "1/1")
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].coder_tokens_label(), "337")
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].reviewer_tokens_label(), "83")
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].total_execution_label(), "2.5")
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].coder_execution_label(), "2")
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].reviewer_execution_label(), "0.5")
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].total_load_label(), "0.75")
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].combined_tps_label(), "168")
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].failed_calls_label(), "0")
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].syntax_rate_label(), "100")
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].quality_score_label(), "100")
        self.assertEqual(cells[("HumanEval/0", "qwen_self_review")].repetitions, 1)
        self.assertEqual(cells[("HumanEval/0", "qwen_no_review")].label, "1/1")

    def test_generated_pdf_contains_headers_and_cell_labels_for_agent_calls(self):
        """Verify a PDF generated from agent call rows contains visible table text commands."""
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "agent_calls.csv"
            output_path = Path(tmp) / "overview.pdf"
            fieldnames = [
                "run_id",
                "experiment_id",
                "task_id",
                "repetition",
                "round_no",
                "agent_role",
                "output_tokens",
                "prompt_eval_duration_s",
                "eval_duration_s",
                "load_duration_s",
                "syntax_ok_after_coder",
                "reviewer_approved",
                "call_failed",
                "error_type",
            ]
            rows = [
                ["20260607_103907_538776", "qwen_self_review", "HumanEval/0", "1", "1", "Coder", "337", "1.25", "0.75", "0.50", "True", "", "False", ""],
                ["20260607_103907_538776", "qwen_self_review", "HumanEval/0", "1", "1", "Reviewer", "83", "0.40", "0.10", "0.25", "", "True", "False", ""],
                ["20260607_103945_261855", "qwen_no_review", "HumanEval/0", "1", "1", "Coder", "311", "1.00", "0.25", "0.20", "False", "", "True", "TimeoutError"],
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
        self.assertIn("(R)", pdf_text)
        self.assertIn("(TCT)", pdf_text)
        self.assertIn("(TRT)", pdf_text)
        self.assertIn("(TTNL)", pdf_text)
        self.assertIn("(TTC)", pdf_text)
        self.assertIn("(TTR)", pdf_text)
        for header in ["TTL", "TLC", "TLR", "ATPS", "CTPS", "RTPS", "FC", "TO", "ERR", "SYN", "APP", "EVAL", "Q", "QPS", "QPK"]:
            self.assertIn(f"({header})", pdf_text)
        self.assertIn("(1/1)", pdf_text)
        self.assertIn("(337)", pdf_text)
        self.assertIn("(83)", pdf_text)
        self.assertIn("(2.5)", pdf_text)
        self.assertIn("(0.75)", pdf_text)
        self.assertIn("(168)", pdf_text)
        self.assertIn("(100)", pdf_text)
        self.assertIn("(green: 1 round / min tokens)", pdf_text)
        self.assertIn("(green: min execution time)", pdf_text)
        self.assertIn("(green: min load time)", pdf_text)
        self.assertIn("(green: max throughput)", pdf_text)
        self.assertIn("(green: no failures)", pdf_text)
        self.assertIn("(green: best quality)", pdf_text)
        self.assertIn("(green: best efficiency)", pdf_text)
        self.assertIn("0.350 0.820 0.350 rg", pdf_text)
        self.assertIn("0.900 0.250 0.250 rg", pdf_text)
        self.assertIn("1.00 w 0.000 0.000 0.000 RG", pdf_text)


    def test_page_size_grows_with_column_count(self):
        """Verify wide reports choose larger DIN landscape pages."""
        self.assertEqual(choose_landscape_page_size(8)[0], "A4")
        self.assertEqual(choose_landscape_page_size(9)[0], "A3")
        self.assertEqual(choose_landscape_page_size(16)[0], "A2")
        self.assertEqual(choose_landscape_page_size(32)[0], "A1")
        self.assertEqual(choose_landscape_page_size(64)[0], "A0")

    def test_transposed_pdf_uses_tasks_as_columns_and_a3_for_nine_columns(self):
        """Verify transposed reports swap axes and grow page size for many task columns."""
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "summary.csv"
            output_path = Path(tmp) / "overview.pdf"
            fieldnames = ["run_id", "experiment_id", "task_id", "repetition", "max_rounds", "rounds_used", "stop_reason"]
            with summary_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(fieldnames)
                for idx in range(9):
                    writer.writerow([f"run{idx}", "wide_experiment", f"HumanEval/{idx}", "1", "5", "1", "done"])

            generate_overview_pdf(summary_path, output_path, transpose=True)
            pdf_text = output_path.read_text(encoding="latin-1")

        self.assertIn("/MediaBox [0 0 1191 842]", pdf_text)
        self.assertIn("(experiment_id)", pdf_text)
        self.assertIn("(wide_experiment)", pdf_text)
        self.assertIn("(HumanEval/8)", pdf_text)

    def test_metric_pages_stay_grouped_when_rows_overflow(self):
        """Verify all row pages for one metric are emitted before the next metric table."""
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "summary.csv"
            output_path = Path(tmp) / "overview.pdf"
            fieldnames = ["run_id", "experiment_id", "task_id", "repetition", "max_rounds", "rounds_used", "stop_reason"]
            with summary_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(fieldnames)
                for idx in range(30):
                    writer.writerow([f"run{idx}", "exp", f"HumanEval/{idx}", "1", "5", "1", "done"])

            generate_overview_pdf(summary_path, output_path)
            pdf_text = output_path.read_text(encoding="latin-1")

        first_tokens = pdf_text.find("Overview: R=rounds_used/max_rounds")
        second_tokens = pdf_text.find("Overview: R=rounds_used/max_rounds", first_tokens + 1)
        first_timing = pdf_text.find("Timing: TTNL=Coder+Reviewer execution time")
        self.assertGreaterEqual(first_tokens, 0)
        self.assertGreaterEqual(second_tokens, 0)
        self.assertGreaterEqual(first_timing, 0)
        self.assertLess(second_tokens, first_timing)

    def test_zero_tokens_are_blue_and_positive_tokens_interpolate(self):
        """Verify token color rules use blue for zero and redder colors for higher usage."""
        low = token_color(10, TokenRange(10, 100))
        high = token_color(100, TokenRange(10, 100))
        zero = token_color(0, TokenRange(10, 100))
        self.assertEqual(zero, (0.35, 0.60, 0.95))
        self.assertLess(low[0], high[0])
        self.assertGreater(low[1], high[1])


if __name__ == "__main__":
    unittest.main()
