from types import SimpleNamespace
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentic_benchmark import cli


class InteractiveModeTests(unittest.TestCase):
    """Tests that interactive mode uses the user's task text as its task source."""

    def write_config(self, path: Path) -> None:
        """Write a small two-row experiment CSV for interactive tests."""
        path.write_text(
            "experiment_id,task_provider,coder_model,reviewer_model,coder_ctx,reviewer_ctx,"
            "coder_num_predict,reviewer_num_predict,coder_timeout_seconds,reviewer_timeout_seconds,"
            "coder_temperature,reviewer_temperature,max_rounds,max_same_code_rounds,feedback_mode,"
            "stop_policy,coder_prompt_template,reviewer_prompt_template,keep_alive,load_mode,repetitions,evaluator\n"
            "first,csv,coder-a,reviewer-a,100,50,10,5,30,30,0.2,0.0,2,1,compact_json,"
            "reviewer_approved_and_syntax_ok,coder_default,reviewer_default,10m,as_is,1,syntax\n"
            "second,csv,coder-b,reviewer-b,200,80,20,8,40,40,0.3,0.1,4,2,full_json,"
            "fixed_rounds,coder_minimal,reviewer_minimal,10m,as_is,1,none\n",
            encoding="utf-8",
        )

    def test_prompt_argument_runs_all_interactive_config_rows(self):
        """Verify --prompt is run once for each selected config row."""
        captured = []
        fake_result = SimpleNamespace(final_code_file="code.py", history_file="history.json")

        def fake_run_agentic_loop(task, experiment, *, repetition=1, verbose=False):
            """Capture each config-backed loop invocation without invoking Ollama."""
            captured.append(
                {
                    "task_id": task.task_id,
                    "source": task.source,
                    "prompt": task.prompt,
                    "experiment_provider": experiment.task_provider,
                    "experiment_id": experiment.experiment_id,
                    "coder_model": experiment.coder.model,
                    "reviewer_model": experiment.reviewer.model if experiment.reviewer else "",
                    "max_rounds": experiment.max_rounds,
                    "repetition": repetition,
                    "verbose": verbose,
                }
            )
            return fake_result

        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "configs.csv"
            self.write_config(config_path)
            args = SimpleNamespace(
                output_dir="/tmp/interactive-test",
                verbose=True,
                prompt="solve my custom task",
                prompt_file=None,
                config=str(config_path),
                experiment_id=None,
            )
            with patch.object(cli, "run_agentic_loop", side_effect=fake_run_agentic_loop), \
                 patch.object(cli, "ResultsWriter") as writer_cls, \
                 patch.object(cli, "prepare_load_mode") as prepare_load, \
                 patch.object(cli, "print_interactive_summary"):
                exit_code = cli.interactive(args)

        self.assertEqual(exit_code, 0)
        self.assertEqual([item["experiment_id"] for item in captured], ["first", "second"])
        self.assertEqual([item["coder_model"] for item in captured], ["coder-a", "coder-b"])
        self.assertTrue(all(item["task_id"] == "interactive" for item in captured))
        self.assertTrue(all(item["source"] == "interactive" for item in captured))
        self.assertTrue(all(item["prompt"] == "solve my custom task" for item in captured))
        self.assertTrue(all(item["experiment_provider"] == "interactive" for item in captured))
        self.assertTrue(all(item["verbose"] for item in captured))
        self.assertEqual(writer_cls.return_value.write_result.call_count, 2)
        self.assertEqual(prepare_load.call_count, 2)

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
        args = SimpleNamespace(
            output_dir="/tmp/interactive-test",
            verbose=False,
            prompt="   ",
            prompt_file=None,
            config="missing.csv",
            experiment_id=None,
        )
        with patch.object(cli, "run_agentic_loop") as run_loop:
            exit_code = cli.interactive(args)
        self.assertEqual(exit_code, 1)
        run_loop.assert_not_called()

    def test_load_interactive_experiments_defaults_to_all_config_rows(self):
        """Verify interactive config loading defaults to all CSV rows."""
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "configs.csv"
            self.write_config(config_path)
            args = SimpleNamespace(config=str(config_path), experiment_id=None)
            experiments = cli.load_interactive_experiments(args)
        self.assertEqual([experiment.experiment_id for experiment in experiments], ["first", "second"])
        self.assertTrue(all(experiment.task_provider == "interactive" for experiment in experiments))
        self.assertEqual(experiments[0].coder.model, "coder-a")

    def test_load_interactive_experiments_can_filter_one_experiment_id(self):
        """Verify --experiment-id narrows interactive mode to one config row."""
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "configs.csv"
            self.write_config(config_path)
            args = SimpleNamespace(config=str(config_path), experiment_id="second")
            experiments = cli.load_interactive_experiments(args)
        self.assertEqual(len(experiments), 1)
        self.assertEqual(experiments[0].experiment_id, "second")
        self.assertEqual(experiments[0].coder.model, "coder-b")

    def test_load_interactive_experiments_rejects_unknown_id(self):
        """Verify an unknown interactive experiment id fails before model execution."""
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "configs.csv"
            self.write_config(config_path)
            args = SimpleNamespace(config=str(config_path), experiment_id="missing")
            with self.assertRaises(ValueError):
                cli.load_interactive_experiments(args)

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
