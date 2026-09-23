#!/usr/bin/env python3
"""End-to-end tests for the bounded Claude dispatch and durable polling path.

The fake worker deliberately behaves like Claude's JSONL stream.  It never
contacts a provider, so these tests prove controller output bounds without
spending subscription usage.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import stat
import sys
import tempfile
import time
import threading
import unittest

from dispatch import MAX_CHANGED_FILE_PATH_CHARS, bounded_file_list, write_json_sidecar
from poll import liveness

SCRIPTS = Path(__file__).resolve().parent
DISPATCH = SCRIPTS / "dispatch.py"
SUBMIT = SCRIPTS / "submit.py"
POLL = SCRIPTS / "poll.py"


FAKE_CLAUDE = """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
import time

root = Path(os.environ["FAKE_PRODUCT_ROOT"])
arguments_path = os.environ.get("FAKE_ARGS_PATH")
if arguments_path:
    Path(arguments_path).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
for index in range(int(os.environ.get("FAKE_CHANGE_COUNT", "0"))):
    path = root / "generated" / f"file-{index:05d}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{index}\\n", encoding="utf-8")

print(json.dumps({"type": "system", "subtype": "init", "session_id": "claude-session-1"}), flush=True)
if os.environ.get("FAKE_USAGE"):
    print(json.dumps({
        "type": "rate_limit_event",
        "rate_limit_info": {"unifiedWindows": {
            "five_hour": {"utilization": float(os.environ["FAKE_USAGE"]), "resetsAt": 1999999999}
        }},
    }), flush=True)
if os.environ.get("FAKE_DELAY"):
    time.sleep(float(os.environ["FAKE_DELAY"]))
is_error = os.environ.get("FAKE_RESULT_ERROR") == "1"
print(json.dumps({
    "type": "result", "subtype": "error" if is_error else "success",
    "is_error": is_error, "result": "blocked by test" if is_error else "done",
}), flush=True)
"""


class DispatchRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "artifacts"
        self.product = self.root / "product"
        self.artifacts.mkdir()
        self.product.mkdir()
        self.prompt = self.root / "prompt.md"
        self.fake_claude = self.root / "fake-claude.py"
        self.fake_claude.write_text(FAKE_CLAUDE, encoding="utf-8")
        self.fake_claude.chmod(0o755)
        self.run_root = self.root / "runtime"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def environment(self, **extra: str) -> dict[str, str]:
        environment = dict(os.environ)
        environment.update(
            {
                "WORKFLOW_CLAUDE_BINARY": str(self.fake_claude),
                "WORKFLOW_SHARED_CONTEXT_ROOT": str(self.root),
                "WORKFLOW_DISPATCH_RUN_ROOT": str(self.run_root),
                "WORKFLOW_CHANGED_FILE_SAMPLE_LIMIT": "5",
                "FAKE_PRODUCT_ROOT": str(self.product),
            }
        )
        environment.update(extra)
        return environment

    def dispatch(self, environment: dict[str, str]) -> tuple[subprocess.CompletedProcess[str], dict]:
        self.prompt.write_text("Task.\nWORKFLOW_ALLOWED_DIRECTORY=generated\n", encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(DISPATCH),
                "claude-cli",
                "[CLAUDE][EXEC] relay-test",
                "execution",
                str(self.prompt),
                str(self.artifacts),
                str(self.product),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        return completed, json.loads(completed.stdout)

    def test_large_change_audit_is_sidecar_not_controller_payload(self) -> None:
        # This is deliberately large enough to reproduce the former controller
        # flood without ever passing the 10,000 paths through stdout.
        completed, envelope = self.dispatch(self.environment(FAKE_CHANGE_COUNT="10000", FAKE_USAGE="0.85"))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(envelope["outcome"], "success")
        self.assertEqual(envelope["product_changed_file_count"], 10_000)
        self.assertEqual(len(envelope["product_changed_files"]), 5)
        self.assertTrue(envelope["product_changed_files_truncated"])
        self.assertLess(len(completed.stdout), 8_000)
        self.assertEqual(envelope["worker"]["kind"], "external-claude-worker")
        self.assertEqual(envelope["worker"]["summary"]["session_id"], "claude-session-1")
        self.assertEqual(envelope["worker"]["summary"]["flow_control"], "WARNING")

        audit = json.loads(Path(envelope["changed_file_audit_path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(audit["product_changed_files"]), 10_000)
        worker = envelope["worker"]
        status = json.loads(Path(worker["status_path"]).read_text(encoding="utf-8"))
        self.assertEqual(status["changed_files"]["count"], 0)
        self.assertEqual(status["session_id"], "claude-session-1")
        stream = Path(worker["stream_path"]).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(stream), 3)
        self.assertEqual(stat.S_IMODE(Path(worker["stream_path"]).stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(Path(envelope["changed_file_audit_path"]).stat().st_mode), 0o600)

    def test_semantic_error_is_not_reported_as_success_when_process_exits_zero(self) -> None:
        completed, envelope = self.dispatch(self.environment(FAKE_RESULT_ERROR="1"))

        self.assertEqual(completed.returncode, 6)
        self.assertEqual(envelope["outcome"], "failed")
        self.assertEqual(envelope["worker"]["semantic_outcome"], "failed")

    def test_native_and_removed_legacy_codex_targets_cannot_run_through_dispatcher(self) -> None:
        self.prompt.write_text("Task.\nWORKFLOW_ALLOWED_DIRECTORY=generated\n", encoding="utf-8")
        for target_id in ("codex-native", "codex-app"):
            with self.subTest(target_id=target_id):
                completed = subprocess.run(
                    [
                        sys.executable, str(DISPATCH), target_id, "[CODEX][EXEC] disabled-target-test",
                        "execution", str(self.prompt), str(self.artifacts), str(self.product),
                    ],
                    check=False, capture_output=True, text=True, env=self.environment(),
                )
                self.assertEqual(completed.returncode, 2)
                self.assertTrue(
                    "not a Claude relay target" in completed.stderr or "unknown target" in completed.stderr,
                    completed.stderr,
                )

    def test_claude_dispatch_has_no_automatic_turn_or_wall_clock_limit(self) -> None:
        arguments_path = self.root / "claude-args.json"
        completed, envelope = self.dispatch(self.environment(
            FAKE_ARGS_PATH=str(arguments_path), FAKE_DELAY="1.2",
            WORKFLOW_DISPATCH_TIMEOUT_SECONDS="1", CLAUDE_WORKER_MAX_TURNS="1",
        ))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(envelope["outcome"], "success")
        self.assertNotIn("--max-turns", json.loads(arguments_path.read_text(encoding="utf-8")))

    def test_liveness_is_observational_at_fifteen_and_thirty_minutes(self) -> None:
        self.assertEqual(liveness(None, 1000, now_epoch=1899)["state"], "ACTIVE")
        self.assertEqual(liveness(None, 1000, now_epoch=1900)["state"], "QUIET")
        self.assertEqual(liveness(None, 1000, now_epoch=2800)["state"], "STALLED_SUSPECTED")

    def test_changed_file_sample_limit_cannot_be_configured_back_to_raw_output_size(self) -> None:
        self.prompt.write_text("Task.\nWORKFLOW_ALLOWED_DIRECTORY=generated\n", encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(DISPATCH),
                "claude-cli",
                "[CLAUDE][EXEC] invalid-sample-limit",
                "execution",
                str(self.prompt),
                str(self.artifacts),
                str(self.product),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=self.environment(WORKFLOW_CHANGED_FILE_SAMPLE_LIMIT="10000"),
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("between 1 and 100", completed.stderr)

    def test_controller_file_samples_have_a_hard_path_length_bound(self) -> None:
        sample, truncated = bounded_file_list({"a" * (MAX_CHANGED_FILE_PATH_CHARS + 20)}, limit=1)

        self.assertFalse(truncated)
        self.assertEqual(len(sample[0]), MAX_CHANGED_FILE_PATH_CHARS)
        self.assertTrue(sample[0].endswith("…"))

    def test_poll_distinguishes_all_terminal_outcomes(self) -> None:
        job_dir = self.root / "terminal-status-job"
        job_dir.mkdir()
        envelope_path = job_dir / "result-envelope.json"
        (job_dir / "job.json").write_text(
            json.dumps({"pid": os.getpid(), "envelope_path": str(envelope_path)}),
            encoding="utf-8",
        )
        expected = {
            "success": "completed",
            "suspended": "suspended",
            "timeout": "timeout",
            "stalled": "stalled",
            "scope-violation": "scope-violation",
            "failed": "failed",
            "unexpected": "failed",
        }
        for outcome, status in expected.items():
            with self.subTest(outcome=outcome):
                envelope_path.write_text(json.dumps({"outcome": outcome}), encoding="utf-8")
                completed = subprocess.run(
                    [sys.executable, str(POLL), str(job_dir)], check=False, capture_output=True, text=True
                )
                self.assertEqual(completed.returncode, 0)
                self.assertEqual(json.loads(completed.stdout)["status"], status)

    def test_poll_never_reads_a_partial_envelope_during_atomic_replacement(self) -> None:
        job_dir = self.root / "atomic-envelope-job"
        job_dir.mkdir()
        envelope_path = job_dir / "result-envelope.json"
        (job_dir / "job.json").write_text(
            json.dumps({"pid": os.getpid(), "envelope_path": str(envelope_path)}),
            encoding="utf-8",
        )
        outcomes = ["success", "failed"]
        write_json_sidecar(envelope_path, {"outcome": "success"})

        def replace_envelope() -> None:
            for index in range(50):
                write_json_sidecar(envelope_path, {"outcome": outcomes[index % len(outcomes)]})
                time.sleep(0.01)

        writer = threading.Thread(target=replace_envelope)
        writer.start()
        observed: list[str] = []
        while writer.is_alive():
            completed = subprocess.run(
                [sys.executable, str(POLL), str(job_dir)], check=False, capture_output=True, text=True
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            observed.append(json.loads(completed.stdout)["status"])
        writer.join()
        self.assertTrue(observed)
        self.assertTrue(set(observed).issubset({"completed", "failed"}))

    def test_hard_usage_threshold_suspends_further_work_at_the_boundary(self) -> None:
        completed, envelope = self.dispatch(self.environment(FAKE_USAGE="0.95"))

        self.assertEqual(completed.returncode, 6)
        self.assertEqual(envelope["outcome"], "suspended")
        flow = json.loads(Path(envelope["worker"]["flow_control_path"]).read_text(encoding="utf-8"))
        self.assertEqual((flow["state"], flow["action"]), ("SUSPENDED", "suspend"))

    def test_observed_usage_suspension_survives_a_generic_provider_error(self) -> None:
        completed, envelope = self.dispatch(self.environment(FAKE_USAGE="0.95", FAKE_RESULT_ERROR="1"))

        self.assertEqual(completed.returncode, 6)
        self.assertEqual(envelope["worker"]["semantic_outcome"], "failed")
        self.assertEqual(envelope["outcome"], "suspended")
        self.assertTrue(Path(envelope["checkpoint_path"]).is_file())

    def test_legacy_stall_timeout_setting_does_not_kill_worker(self) -> None:
        completed, envelope = self.dispatch(
            self.environment(FAKE_DELAY="1", WORKFLOW_CLAUDE_STALL_TIMEOUT_SECONDS="0.05")
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(envelope["outcome"], "success")

    def test_dispatch_forwards_a_verified_resume_session_to_the_external_worker(self) -> None:
        arguments_path = self.root / "fake-claude-args.json"
        completed, envelope = self.dispatch(
            self.environment(
                WORKFLOW_CLAUDE_RESUME_SESSION="parent-session-1",
                FAKE_ARGS_PATH=str(arguments_path),
            )
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(envelope["outcome"], "success")
        arguments = json.loads(arguments_path.read_text(encoding="utf-8"))
        self.assertIn("--resume", arguments)
        self.assertEqual(arguments[arguments.index("--resume") + 1], "parent-session-1")

    def test_submit_and_poll_expose_compact_live_external_worker_state(self) -> None:
        self.prompt.write_text("Task.\nWORKFLOW_ALLOWED_DIRECTORY=generated\n", encoding="utf-8")
        job_dir = self.root / "job"
        submitted = subprocess.run(
            [
                sys.executable,
                str(SUBMIT),
                "claude-cli",
                "[CLAUDE][EXEC] relay-test",
                "execution",
                str(self.prompt),
                str(self.artifacts),
                str(self.product),
                str(job_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=self.environment(
                FAKE_DELAY="1.0",
                WORKFLOW_CLAUDE_RESUME_SESSION="parent-session-1",
                WORKFLOW_RESUME_PARENT_JOB_DIR="/tmp/parent-job",
                WORKFLOW_RESUME_PARENT_ENVELOPE_PATH="/tmp/parent-job/result-envelope.json",
                WORKFLOW_RESUME_PROVENANCE_PATH="/tmp/parent-job/resumes/resume-001/resume-provenance.json",
                WORKFLOW_RESUME_ATTEMPT="1",
            ),
        )
        self.assertEqual(submitted.returncode, 0, submitted.stderr)
        self.assertEqual(stat.S_IMODE(job_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((job_dir / "job.json").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((job_dir / "runner.stdout.log").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((job_dir / "runner.stderr.log").stat().st_mode), 0o600)
        deadline = time.monotonic() + 5
        worker_status = job_dir / "worker-status.json"
        status_record = None
        while time.monotonic() < deadline:
            if worker_status.exists():
                status_record = json.loads(worker_status.read_text(encoding="utf-8"))
                if status_record.get("session_id") == "claude-session-1":
                    break
            time.sleep(0.05)
        self.assertIsNotNone(status_record)
        self.assertEqual(status_record.get("session_id"), "claude-session-1")

        running = subprocess.run(
            [sys.executable, str(POLL), str(job_dir)], check=False, capture_output=True, text=True
        )
        running_status = json.loads(running.stdout)
        self.assertEqual(running_status["status"], "running")
        self.assertEqual(running_status["worker"]["session_id"], "claude-session-1")
        self.assertEqual(running_status["resume"]["attempt"], "1")

        envelope = job_dir / "result-envelope.json"
        while not envelope.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(envelope.exists())
        self.assertEqual(stat.S_IMODE(envelope.stat().st_mode), 0o600)
        finished = subprocess.run(
            [sys.executable, str(POLL), str(job_dir)], check=False, capture_output=True, text=True
        )
        self.assertEqual(json.loads(finished.stdout)["status"], "completed")


if __name__ == "__main__":
    unittest.main()
