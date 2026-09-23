"""Offline checks for the registry-driven local-worker boundary."""

from __future__ import annotations

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import worker
from registry import resolve_target


class WorkerTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)
        (self.repository / "small.txt").write_text("small\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_registry_resolves_canonical_and_legacy_ids(self) -> None:
        self.assertEqual(resolve_target("mac-ollama")["id"], "mac-ollama")
        self.assertEqual(resolve_target("mac")["id"], "mac-ollama")
        self.assertEqual(resolve_target("windows")["id"], "windows-4070")

    def test_windows_limits_are_registry_values(self) -> None:
        target = worker.target_config("windows-4070")
        self.assertEqual(target["hard_limits"], {"max_files": 3, "max_context_bytes": 32000, "max_prompt_chars": 8000})

    def test_oversized_windows_unit_is_rejected_before_health_check(self) -> None:
        with patch.object(worker, "ollama_model_available") as health:
            result = worker.run_local_worker(
                "[WINDOWS][EXEC] EU-01",
                str(self.repository),
                ["small.txt"],
                "x" * 8001,
                target="windows-4070",
            )
        self.assertEqual(result["status"], "unsuitable")
        health.assert_not_called()

    def test_target_label_must_match_registry_prefix(self) -> None:
        with self.assertRaisesRegex(ValueError, "\\[WINDOWS\\]"):
            worker.run_local_worker("[LOCAL][EXEC] EU-01", str(self.repository), ["small.txt"], "change", target="windows-4070")

    def test_unavailable_target_returns_without_editing(self) -> None:
        with patch.object(worker, "ollama_model_available", return_value=(False, "offline")):
            result = worker.run_local_worker("[WINDOWS][EXEC] EU-01", str(self.repository), ["small.txt"], "change", target="windows-4070")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual((self.repository / "small.txt").read_text(encoding="utf-8"), "small\n")

    def test_local_worker_has_no_default_task_timeout(self) -> None:
        with patch.object(worker, "ollama_model_available", return_value=(True, "ready")):
            with patch.object(worker.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "done", "")) as run:
                result = worker.run_local_worker(
                    "[LOCAL][EXEC] EU-01", str(self.repository), ["small.txt"], "add a focused test",
                )
        self.assertEqual(result["status"], "success")
        self.assertIsNone(run.call_args.kwargs["timeout"])


if __name__ == "__main__":
    unittest.main()
