from types import SimpleNamespace
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentic_benchmark import cli


class InteractiveModeTests(unittest.TestCase):
    """Tests that interactive mode uses the user's task text as its task source."""

    def test_prompt_argument_becomes_interactive_task_prompt(self):
        """Verify --prompt is passed to run_agentic_loop instead of loading a benchmark task."""
        captured = {}
        fake_result = SimpleNamespace(final_code_file="code.py", history_file="history.json")

        def fake_run_agentic_loop(task, experiment, *, verbose=False):
            """Capture the task passed to the loop without invoking Ollama."""
            captured["task_id"] = task.task_id
            captured["source"] = task.source
            captured["prompt"] = task.prompt
            captured["experiment_provider"] = experiment.task_provider
            captured["verbose"] = verbose
            return fake_result

        args = SimpleNamespace(output_dir="/tmp/interactive-test", verbose=True, prompt="solve my custom task", prompt_file=None)
        with patch.object(cli, "run_agentic_loop", side_effect=fake_run_agentic_loop), \
             patch.object(cli, "ResultsWriter") as writer_cls, \
             patch.object(cli, "print_interactive_summary"):
            exit_code = cli.interactive(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["task_id"], "interactive")
        self.assertEqual(captured["source"], "interactive")
        self.assertEqual(captured["prompt"], "solve my custom task")
        self.assertEqual(captured["experiment_provider"], "interactive")
        self.assertTrue(captured["verbose"])
        writer_cls.return_value.write_result.assert_called_once_with(fake_result)

    def test_prompt_file_is_read_as_interactive_task_text(self):
        """Verify --prompt-file supports multi-line task descriptions."""
        with tempfile.TemporaryDirectory() as tmp:
            prompt_path = Path(tmp) / "task.txt"
            prompt_path.write_text("line one\nline two\n", encoding="utf-8")
            args = SimpleNamespace(prompt=None, prompt_file=str(prompt_path))
            self.assertEqual(cli.read_interactive_task_text(args), "line one\nline two")

    def test_piped_stdin_reads_complete_multiline_task(self):
        """Verify non-TTY stdin is consumed completely instead of only reading one line."""
        args = SimpleNamespace(prompt=None, prompt_file=None)
        with patch.object(cli.sys, "stdin", io.StringIO("first line\nsecond line\n")):
            self.assertEqual(cli.read_interactive_task_text(args), "first line\nsecond line")

    def test_empty_interactive_task_returns_error_before_model_call(self):
        """Verify empty interactive input fails clearly before invoking any model."""
        args = SimpleNamespace(output_dir="/tmp/interactive-test", verbose=False, prompt="   ", prompt_file=None)
        with patch.object(cli, "run_agentic_loop") as run_loop:
            exit_code = cli.interactive(args)
        self.assertEqual(exit_code, 1)
        run_loop.assert_not_called()

    def test_main_accepts_prompt_without_explicit_interactive_subcommand(self):
        """Verify legacy entrypoint arguments default to the interactive subcommand."""
        with patch.object(cli, "interactive", return_value=0) as interactive_func:
            exit_code = cli.main(["--prompt", "legacy prompt"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(interactive_func.call_args.args[0].prompt, "legacy prompt")

    def test_main_preserves_explicit_run_subcommand(self):
        """Verify explicit subcommands are not rewritten to interactive mode."""
        with patch.object(cli, "run_benchmark", return_value=0) as run_func:
            exit_code = cli.main(["run", "--tasks", "tasks.jsonl"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(run_func.call_args.args[0].command, "run")


if __name__ == "__main__":
    unittest.main()
