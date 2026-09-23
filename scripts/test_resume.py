#!/usr/bin/env python3
"""Deterministic tests for the Claude-only safe resume helper."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("resume.py")
POLL = Path(__file__).with_name("poll.py")
NOW = 1_700_000_000


FAKE_SUBMIT = """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

job_dir = Path(sys.argv[-1])
job_dir.mkdir(parents=True)
record = {
    "argv": sys.argv[1:],
    "session": os.environ.get("WORKFLOW_CLAUDE_RESUME_SESSION"),
    "parent": os.environ.get("WORKFLOW_RESUME_PARENT_JOB_DIR"),
    "parent_envelope": os.environ.get("WORKFLOW_RESUME_PARENT_ENVELOPE_PATH"),
    "provenance": os.environ.get("WORKFLOW_RESUME_PROVENANCE_PATH"),
    "attempt": os.environ.get("WORKFLOW_RESUME_ATTEMPT"),
}
(Path(record["parent"]) / "resume-state.json").exists() and record.update({
    "parent_state_when_called": json.loads((Path(record["parent"]) / "resume-state.json").read_text()).get("state")
})
(job_dir / "fake-submit.json").write_text(json.dumps(record), encoding="utf-8")
reply_job_dir = "/wrong-child" if os.environ.get("FAKE_SUBMIT_REPLY_MISMATCH") == "1" else str(job_dir)
print(json.dumps({"status": "submitted", "job_dir": reply_job_dir, "pid": 123}))
"""


class ResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.parent = self.root / "parent"
        self.parent.mkdir()
        self.prompt = self.root / "prompt.md"
        self.prompt.write_text("Task\n", encoding="utf-8")
        self.artifact_root = self.root / "artifact"
        self.product_root = self.root / "product"
        self.artifact_root.mkdir()
        self.product_root.mkdir()
        self.fake_submit = self.root / "fake-submit.py"
        self.fake_submit.write_text(FAKE_SUBMIT, encoding="utf-8")
        self.fake_submit.chmod(0o700)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_parent(
        self,
        *,
        target: str = "claude-cli",
        outcome: str = "suspended",
        session_id: object = "claude-session-1",
        flow_state: str = "SUSPENDED",
        resets_at: object = NOW,
    ) -> None:
        envelope = self.parent / "result-envelope.json"
        envelope.write_text(
            json.dumps(
                {
                    "outcome": outcome,
                    "worker": {
                        "kind": "external-claude-worker",
                        "summary": {"session_id": session_id},
                        "flow_control": {"state": flow_state, "resets_at": resets_at},
                    },
                }
            ),
            encoding="utf-8",
        )
        (self.parent / "job.json").write_text(
            json.dumps(
                {
                    "target": target,
                    "label": "[CLAUDE] resumable stage",
                    "mode": "artifact",
                    "prompt_file": str(self.prompt),
                    "artifact_root": str(self.artifact_root),
                    "product_root": str(self.product_root),
                    "envelope_path": str(envelope),
                }
            ),
            encoding="utf-8",
        )

    def invoke(self, *extra: str, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.parent),
                "--submit-script",
                str(self.fake_submit),
                "--now-epoch",
                str(NOW),
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
            env=dict(os.environ, **(environment or {})),
        )

    def test_due_checkpoint_submits_one_resumed_child_with_provenance(self) -> None:
        self.write_parent()
        completed = self.invoke()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "resumed")
        child = Path(result["child_job_dir"])
        self.assertEqual(child, (self.parent / "resumes" / "resume-001").resolve())
        fake = json.loads((child / "fake-submit.json").read_text(encoding="utf-8"))
        self.assertEqual(fake["session"], "claude-session-1")
        self.assertEqual(fake["parent"], str(self.parent.resolve()))
        self.assertEqual(fake["attempt"], "1")
        self.assertEqual(fake["parent_state_when_called"], "submitting")
        provenance = json.loads((child / "resume-provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(provenance["session_id"], "claude-session-1")
        self.assertEqual(provenance["reset_due_epoch"], NOW)
        state = json.loads((self.parent / "resume-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["child_job_dir"], str(child))
        polled = subprocess.run(
            [sys.executable, str(POLL), str(self.parent)], check=False, capture_output=True, text=True
        )
        self.assertEqual(polled.returncode, 0, polled.stderr)
        self.assertEqual(json.loads(polled.stdout)["resume_state"]["child_job_dir"], str(child))
        self.assertFalse((self.parent / ".resume.lock").exists())

    def test_not_due_never_invokes_submission(self) -> None:
        self.write_parent(resets_at=NOW + 1)
        completed = self.invoke()

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stderr)["status"], "not-resumed")
        self.assertFalse((self.parent / "resumes").exists())

    def test_invalid_or_non_claude_checkpoints_are_rejected_before_submission(self) -> None:
        cases = [
            {"target": "codex-app"},
            {"outcome": "failed"},
            {"session_id": ""},
            {"flow_state": "OK"},
            {"resets_at": None},
            {"resets_at": "not-a-time"},
        ]
        for case in cases:
            with self.subTest(case=case):
                self.write_parent(**case)
                completed = self.invoke()
                self.assertEqual(completed.returncode, 2)
                self.assertFalse((self.parent / "resumes").exists())
                for path in self.parent.glob("resume-state.json"):
                    path.unlink()

    def test_repeat_invocation_does_not_launch_a_second_resume(self) -> None:
        self.write_parent(resets_at="2023-11-14T22:13:20Z")
        first = self.invoke()
        second = self.invoke()

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 2)
        self.assertEqual(sorted(path.name for path in (self.parent / "resumes").iterdir()), ["resume-001"])

    def test_ambiguous_submission_is_recorded_and_never_retried_automatically(self) -> None:
        self.write_parent()
        first = self.invoke(environment={"FAKE_SUBMIT_REPLY_MISMATCH": "1"})
        second = self.invoke()

        self.assertEqual(first.returncode, 2)
        self.assertEqual(second.returncode, 2)
        state = json.loads((self.parent / "resume-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["state"], "submitting")
        self.assertEqual(sorted(path.name for path in (self.parent / "resumes").iterdir()), ["resume-001"])


if __name__ == "__main__":
    unittest.main()
