#!/usr/bin/env python3
"""Tests for the deterministic Claude JSONL relay.

These tests never invoke Claude.  They feed synthetic JSONL events into the
parser and use a harmless Python child only to cover the public process wrapper.
"""

from __future__ import annotations

import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest

# Permit both ``python scripts/test_claude_relay.py`` and the unittest loader's
# file-path form from the workflow root.
SCRIPT_DIRECTORY = str(Path(__file__).resolve().parent)
if SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, SCRIPT_DIRECTORY)

from claude_relay import (
    ClaudeRelay,
    MAX_CALLER_SUMMARY_CHARS,
    MAX_TEXT_SUMMARY_CHARS,
    classify_flow_control,
    extract_rate_limit_windows,
    run,
    wall_timeout_deadline,
    wall_timeout_expired,
)


class ClaudeRelayTests(unittest.TestCase):
    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_stream_containment_and_atomic_compact_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_directory = Path(temporary_directory)
            relay = ClaudeRelay(run_directory, changed_file_sample_limit=3)
            changed_files = [f"generated/file-{number}.ts" for number in range(10_000)]
            self.assertTrue(
                relay.consume_line(
                    json.dumps(
                        {
                            "type": "assistant",
                            "session_id": "session-123",
                            "changed_files": changed_files,
                        }
                    )
                )
            )
            self.assertTrue(
                relay.consume_line(
                    json.dumps(
                        {
                            "type": "result",
                            "terminal_reason": "completed",
                            "subtype": "success",
                            "is_error": False,
                            "result": "x" * (MAX_TEXT_SUMMARY_CHARS * 4),
                        }
                    )
                )
            )
            self.assertEqual(relay.finalize(returncode=0, timed_out=False), "success")

            stream_event = json.loads(relay.stream_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(len(stream_event["changed_files"]), 10_000)
            self.assertEqual(stat.S_IMODE(relay.stream_path.stat().st_mode), 0o600)

            status = self.read_json(relay.status_path)
            self.assertEqual(status["session_id"], "session-123")
            self.assertEqual(status["changed_files"]["count"], 10_000)
            self.assertEqual(status["changed_files"]["sample"], changed_files[:3])
            self.assertTrue(status["changed_files"]["truncated"])
            self.assertLessEqual(len(status["terminal"]["summary"]), MAX_TEXT_SUMMARY_CHARS)
            self.assertEqual(status["semantic_outcome"], "success")
            self.assertFalse(list(run_directory.glob(".worker-status.json.*.tmp")))
            self.assertFalse(list(run_directory.glob(".flow-control.json.*.tmp")))

            caller_summary = relay.caller_summary()
            self.assertLessEqual(len(caller_summary), MAX_CALLER_SUMMARY_CHARS)
            self.assertNotIn("generated/file-9999.ts", caller_summary)
            self.assertEqual(json.loads(caller_summary)["changed_file_count"], 10_000)

    def test_usage_warning_then_sticky_suspend(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            relay = ClaudeRelay(temporary_directory, warning_percent=15, suspend_percent=10)
            relay.consume_line(
                json.dumps(
                    {
                        "type": "rate_limit_event",
                        "rate_limit_info": {
                            "five_hour": {
                                "utilization": 0.86,
                                "resets_at": "2030-01-01T00:00:00Z",
                            }
                        },
                    }
                )
            )
            warning = self.read_json(relay.flow_control_path)
            self.assertEqual(warning["state"], "WARNING")
            self.assertEqual(warning["action"], "warn")
            self.assertEqual(warning["remaining_percent"], 14.0)

            relay.consume_line(
                json.dumps(
                    {
                        "type": "rate_limit_event",
                        "rate_limit_info": {
                            "five_hour": {
                                "utilization": 0.92,
                                "resets_at": "2030-01-01T00:00:00Z",
                            }
                        },
                    }
                )
            )
            suspend = self.read_json(relay.flow_control_path)
            self.assertEqual(suspend["state"], "SUSPENDED")
            self.assertEqual(suspend["action"], "suspend")
            self.assertEqual(suspend["remaining_percent"], 8.0)

            # A later status event cannot silently restart scheduling.  A
            # supervisor must checkpoint, verify reset, and begin/resume work.
            relay.consume_line(
                json.dumps(
                    {
                        "type": "rate_limit_event",
                        "rate_limit_info": {"five_hour": {"utilization": 0.10}},
                    }
                )
            )
            self.assertEqual(self.read_json(relay.flow_control_path)["state"], "SUSPENDED")
            relay.close()

    def test_malformed_events_are_retained_but_do_not_crash_the_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            relay = ClaudeRelay(temporary_directory)
            self.assertFalse(relay.consume_line("{ not valid json"))
            self.assertFalse(relay.consume_line(json.dumps(["not", "an", "event"])))
            status = self.read_json(relay.status_path)
            self.assertEqual(status["event_counts"], {"malformed_events": 2, "parsed_events": 0, "raw_lines": 2})
            self.assertEqual(status["state"], "running")
            self.assertEqual(len(relay.stream_path.read_text(encoding="utf-8").splitlines()), 2)
            relay.close()

    def test_timeout_helpers_and_terminal_classification(self) -> None:
        self.assertEqual(wall_timeout_deadline(20.0, 5.0), 25.0)
        self.assertFalse(wall_timeout_expired(20.0, 5.0, now_monotonic=24.999))
        self.assertTrue(wall_timeout_expired(20.0, 5.0, now_monotonic=25.0))
        self.assertFalse(wall_timeout_expired(20.0, None, now_monotonic=1_000.0))
        with self.assertRaises(ValueError):
            wall_timeout_deadline(0.0, 0.0)

        with tempfile.TemporaryDirectory() as temporary_directory:
            relay = ClaudeRelay(temporary_directory)
            self.assertEqual(relay.finalize(returncode=124, timed_out=True), "timeout")
            status = self.read_json(relay.status_path)
            self.assertEqual(status["state"], "timed_out")
            self.assertEqual(status["terminal"]["reason"], "wall_timeout")

    def test_flow_classifier_handles_named_windows(self) -> None:
        flow = classify_flow_control(
            [
                {"window": "weekly", "remaining_percent": 60, "resets_at": "later"},
                {"window": "five_hour", "remaining_percent": 9, "resets_at": "soon"},
            ]
        )
        self.assertEqual(flow["state"], "SUSPENDED")
        self.assertEqual(flow["window"], "five_hour")
        self.assertEqual(flow["resets_at"], "soon")

    def test_percent_field_names_do_not_treat_one_percent_as_full_usage(self) -> None:
        percent_windows = extract_rate_limit_windows(
            {"rate_limit_info": {"five_hour": {"usedPercent": 1, "resetsAt": "soon"}}}
        )
        remaining_windows = extract_rate_limit_windows(
            {"rate_limit_info": {"weekly": {"remainingPercent": 1, "resetsAt": "later"}}}
        )
        ratio_windows = extract_rate_limit_windows(
            {"rate_limit_info": {"five_hour": {"utilization": 1, "resetsAt": "soon"}}}
        )

        self.assertEqual(percent_windows[0]["remaining_percent"], 99.0)
        self.assertEqual(remaining_windows[0]["remaining_percent"], 1.0)
        self.assertEqual(classify_flow_control(percent_windows)["state"], "OK")
        self.assertEqual(classify_flow_control(ratio_windows)["state"], "SUSPENDED")

    def test_public_run_uses_a_fake_jsonl_worker_and_returns_bounded_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fake_worker = (
                "import json; "
                "print(json.dumps({'type':'system','session_id':'fake-session'})); "
                "print(json.dumps({'type':'result','terminal_reason':'completed','is_error':False,'result':'done'}))"
            )
            result = run(
                [sys.executable, "-u", "-c", fake_worker],
                cwd=temporary_directory,
                run_dir=temporary_directory,
                timeout_seconds=5,
            )
            self.assertEqual(result.returncode, 0)
            self.assertFalse(result.timed_out)
            self.assertEqual(result.semantic_outcome, "success")
            self.assertLessEqual(len(result.stdout_summary), MAX_CALLER_SUMMARY_CHARS)
            self.assertEqual(self.read_json(Path(result.status_path))["session_id"], "fake-session")

    def test_public_run_classifies_a_wall_timeout_without_claude(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = run(
                [sys.executable, "-u", "-c", "import time; time.sleep(2)"],
                cwd=temporary_directory,
                run_dir=temporary_directory,
                timeout_seconds=0.05,
            )
            self.assertTrue(result.timed_out)
            self.assertEqual(result.semantic_outcome, "timeout")
            status = self.read_json(Path(result.status_path))
            self.assertEqual(status["state"], "timed_out")
            self.assertEqual(status["terminal"]["reason"], "wall_timeout")

    def test_public_run_classifies_an_inactive_worker_without_claude(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = run(
                [sys.executable, "-u", "-c", "import time; time.sleep(2)"],
                cwd=temporary_directory,
                run_dir=temporary_directory,
                timeout_seconds=5,
                stall_timeout_seconds=0.05,
            )
            self.assertFalse(result.timed_out)
            self.assertTrue(result.stalled)
            self.assertEqual(result.semantic_outcome, "stalled")
            status = self.read_json(Path(result.status_path))
            self.assertEqual(status["state"], "stalled")
            self.assertEqual(status["terminal"]["reason"], "inactivity_timeout")


if __name__ == "__main__":
    unittest.main()
