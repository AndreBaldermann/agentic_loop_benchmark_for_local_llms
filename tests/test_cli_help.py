import contextlib
import io
import unittest

from agentic_benchmark.cli import build_parser


class CliHelpTests(unittest.TestCase):
    """Smoke tests that keep CLI documentation aligned with argparse."""
    def test_top_level_help_lists_commands(self):
        """Verify top-level help lists every public subcommand."""
        help_text = build_parser().format_help()
        for command in [
            "interactive",
            "run",
            "validate-config",
            "list-tasks",
            "write-sample-config",
        ]:
            self.assertIn(command, help_text)

    def test_run_help_lists_core_options(self):
        """Verify run --help exposes the primary benchmark options."""
        parser = build_parser()
        with contextlib.redirect_stdout(io.StringIO()) as stdout, self.assertRaises(SystemExit) as cm:
            parser.parse_args(["run", "--help"])
        help_text = stdout.getvalue()
        for option in ["--config", "--tasks", "--output-dir", "--limit", "--task-id"]:
            self.assertIn(option, help_text)
        self.assertEqual(cm.exception.code, 0)

    def test_known_commands_have_handlers(self):
        """Verify known subcommands are wired to callable handlers."""
        parser = build_parser()
        cases = [
            ["interactive"],
            ["validate-config"],
            ["list-tasks", "--tasks", "tasks.jsonl"],
            ["write-sample-config"],
        ]
        for args in cases:
            with self.subTest(args=args):
                namespace = parser.parse_args(args)
                self.assertTrue(callable(namespace.func))


if __name__ == "__main__":
    unittest.main()
