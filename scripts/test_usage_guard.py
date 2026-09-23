#!/usr/bin/env python3
"""Deterministic tests for the standard-library usage guard."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import usage_guard


NOW = 1_700_000_000


def legacy_payload(*, primary_used: int = 50, primary_reset: int | None = NOW + 300) -> dict:
    return {
        "ordinaryUsageAllowed": True,
        "rateLimits": {
            "limitId": "codex",
            "primary": {
                "usedPercent": primary_used,
                "resetsAt": primary_reset,
                "windowDurationMins": 300,
            },
            "secondary": {
                "usedPercent": 20,
                "resetsAt": NOW + 86_400,
                "windowDurationMins": 10_080,
            },
        },
    }


def write_fake_codex_app_server(directory: Path, payload: dict, mode: str = "success") -> Path:
    """Write a deterministic JSONL app-server executable for opt-in CLI tests."""

    executable = directory / "fake-codex-app-server.py"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
import time

PAYLOAD = %r
MODE = %r
messages = []

def trace():
    path = os.environ.get("USAGE_GUARD_FAKE_TRACE")
    if path:
        Path(path).write_text(json.dumps(messages), encoding="utf-8")

for raw in sys.stdin:
    message = json.loads(raw)
    messages.append(message)
    method = message.get("method")
    if method == "initialize":
        print(json.dumps({"id": message.get("id"), "result": {"serverInfo": {"name": "fake"}}}), flush=True)
    elif method == "initialized":
        continue
    elif method == "account/rateLimits/read":
        trace()
        if MODE == "stall":
            time.sleep(60)
        elif MODE == "error":
            print(json.dumps({"id": message.get("id"), "error": {"code": -32000, "message": "fixture error"}}), flush=True)
        else:
            print(json.dumps({"id": message.get("id"), "result": PAYLOAD}), flush=True)
        break
""" % (payload, mode),
        encoding="utf-8",
    )
    executable.chmod(0o700)
    return executable


class NormalizeTests(unittest.TestCase):
    def test_normalizes_legacy_primary_and_secondary_windows(self) -> None:
        normalized = usage_guard.normalize_codex_rate_limits(legacy_payload(primary_used=84))

        self.assertEqual(normalized["source"], "legacy")
        self.assertEqual(
            normalized["windows"],
            [
                {
                    "id": "codex:primary",
                    "limit_id": "codex",
                    "window": "primary",
                    "used_percent": 84.0,
                    "remaining_percent": 16.0,
                    "resets_at_epoch": NOW + 300,
                    "window_duration_minutes": 300,
                },
                {
                    "id": "codex:secondary",
                    "limit_id": "codex",
                    "window": "secondary",
                    "used_percent": 20.0,
                    "remaining_percent": 80.0,
                    "resets_at_epoch": NOW + 86_400,
                    "window_duration_minutes": 10_080,
                },
            ],
        )

    def test_multi_bucket_payload_is_authoritative_and_preserves_all_windows(self) -> None:
        payload = {
            "rateLimits": legacy_payload()["rateLimits"],
            "rateLimitsByLimitId": {
                "codex": {
                    "limitId": "codex",
                    "primary": {"usedPercent": 90, "resetsAt": NOW + 100},
                    "secondary": {"usedPercent": 30, "resetsAt": NOW + 5_000},
                },
                "gpt-5": {
                    "primary": {"usedPercent": 95, "resetsAt": NOW + 200},
                },
            },
        }

        normalized = usage_guard.normalize_codex_rate_limits(payload)

        self.assertEqual(normalized["source"], "multi_bucket")
        self.assertEqual([window["id"] for window in normalized["windows"]], [
            "codex:primary", "codex:secondary", "gpt-5:primary",
        ])
        self.assertNotIn("legacy:primary", [window["id"] for window in normalized["windows"]])

    def test_nested_json_rpc_result_is_accepted(self) -> None:
        normalized = usage_guard.normalize_codex_rate_limits({"result": legacy_payload()})
        self.assertEqual(normalized["windows"][0]["id"], "codex:primary")

    def test_malformed_multi_bucket_data_is_not_silently_ignored(self) -> None:
        payload = legacy_payload()
        payload["rateLimitsByLimitId"] = []

        with self.assertRaisesRegex(ValueError, "must be an object or null"):
            usage_guard.normalize_codex_rate_limits(payload)

    def test_empty_present_multi_bucket_map_does_not_fall_back_to_legacy(self) -> None:
        payload = legacy_payload()
        payload["rateLimitsByLimitId"] = {}

        with self.assertRaisesRegex(ValueError, "must not be empty when present"):
            usage_guard.normalize_codex_rate_limits(payload)

    def test_explicitly_unavailable_optional_window_is_recorded_not_treated_as_zero(self) -> None:
        payload = legacy_payload()
        payload["rateLimits"]["secondary"] = None

        normalized = usage_guard.normalize_codex_rate_limits(payload)
        record = usage_guard.evaluate_codex_usage(normalized, now_epoch=NOW)

        self.assertEqual([window["id"] for window in normalized["windows"]], ["codex:primary"])
        self.assertEqual(normalized["unavailable_window_ids"], ["codex:secondary"])
        self.assertEqual(record["unavailable_window_ids"], ["codex:secondary"])


class EvaluationTests(unittest.TestCase):
    def test_warning_at_fifteen_percent_headroom(self) -> None:
        normalized = usage_guard.normalize_codex_rate_limits(legacy_payload(primary_used=85))
        record = usage_guard.evaluate_codex_usage(normalized, now_epoch=NOW)

        self.assertEqual((record["state"], record["reason"]), (
            "WARNING", "headroom_at_or_below_warning_threshold",
        ))
        self.assertEqual(record["limiting_window_ids"], ["codex:primary"])
        self.assertIsNone(record["resume_at_epoch"])

    def test_hard_suspend_waits_for_every_limiting_bucket_reset(self) -> None:
        payload = {
            "rateLimits": {"primary": {"usedPercent": 1}},
            "rateLimitsByLimitId": {
                "codex": {"primary": {"usedPercent": 90, "resetsAt": NOW + 100}},
                "gpt-5": {"primary": {"usedPercent": 95, "resetsAt": NOW + 200}},
            },
        }
        normalized = usage_guard.normalize_codex_rate_limits(payload)
        record = usage_guard.evaluate_codex_usage(normalized, now_epoch=NOW)

        self.assertEqual(record["state"], "SUSPENDED")
        self.assertEqual(record["limiting_window_ids"], ["codex:primary", "gpt-5:primary"])
        self.assertEqual(record["resume_at_epoch"], NOW + 200)
        self.assertEqual(record["resume_at_iso"], "2023-11-14T22:16:40Z")
        self.assertTrue(record["requires_fresh_check"])

    def test_custom_thresholds_are_validated_and_applied(self) -> None:
        normalized = usage_guard.normalize_codex_rate_limits(legacy_payload(primary_used=82))
        record = usage_guard.evaluate_codex_usage(
            normalized,
            warning_headroom_percent=20,
            suspend_headroom_percent=18,
            now_epoch=NOW,
        )

        self.assertEqual(record["state"], "SUSPENDED")
        with self.assertRaisesRegex(ValueError, "must not exceed"):
            usage_guard.evaluate_codex_usage(
                normalized, warning_headroom_percent=5, suspend_headroom_percent=10, now_epoch=NOW
            )

    def test_missing_reset_time_blocks_an_automatic_suspend_resume(self) -> None:
        normalized = usage_guard.normalize_codex_rate_limits(legacy_payload(primary_used=95, primary_reset=None))
        record = usage_guard.evaluate_codex_usage(normalized, now_epoch=NOW)

        self.assertEqual((record["state"], record["reason"]), ("BLOCKED", "suspend_without_reset_time"))
        self.assertIsNone(record["resume_at_epoch"])


class CliAndStorageTests(unittest.TestCase):
    def test_cli_writes_a_compact_atomic_record_from_a_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture = directory / "usage.json"
            output = directory / "flow-control.json"
            fixture.write_text(json.dumps(legacy_payload(primary_used=95)), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("usage_guard.py")),
                    "--input", str(fixture),
                    "--flow-control", str(output),
                    "--now-epoch", str(NOW),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            printed = json.loads(completed.stdout)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(printed, saved)
            self.assertEqual(saved["state"], "SUSPENDED")
            self.assertNotIn("used_percent", saved["windows"][0])
            self.assertEqual(list(directory.glob(".flow-control.json.*.tmp")), [])

    def test_invalid_fixture_replaces_stale_ok_record_with_blocked_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture = directory / "usage.json"
            output = directory / "flow-control.json"
            fixture.write_text("{not json", encoding="utf-8")
            output.write_text('{"state":"OK"}\n', encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("usage_guard.py")),
                    "--input", str(fixture),
                    "--flow-control", str(output),
                    "--now-epoch", str(NOW),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(saved["state"], "BLOCKED")
            self.assertTrue(saved["reason"].startswith("invalid_usage_input:"))

    def test_invalid_clock_still_replaces_stale_ok_record_with_blocked_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture = directory / "usage.json"
            output = directory / "flow-control.json"
            fixture.write_text(json.dumps(legacy_payload()), encoding="utf-8")
            output.write_text('{"state":"OK"}\n', encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("usage_guard.py")),
                    "--input", str(fixture),
                    "--flow-control", str(output),
                    "--now-epoch", "nan",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(saved["state"], "BLOCKED")
            self.assertTrue(saved["reason"].startswith("invalid_usage_input:"))


class AppServerCliTests(unittest.TestCase):
    def test_opt_in_reader_performs_handshake_and_uses_fake_response(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            output = directory / "flow-control.json"
            trace = directory / "messages.json"
            snapshot = legacy_payload(primary_used=95)
            snapshot["rateLimits"]["secondary"] = None
            snapshot["rateLimitsByLimitId"] = {"codex": snapshot["rateLimits"]}
            fake = write_fake_codex_app_server(directory, snapshot)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("usage_guard.py")),
                    "--read-codex-app-server",
                    "--codex-binary", str(fake),
                    "--app-server-timeout-seconds", "1",
                    "--flow-control", str(output),
                    "--now-epoch", str(NOW),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=dict(os.environ, USAGE_GUARD_FAKE_TRACE=str(trace)),
                timeout=5,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            record = json.loads(output.read_text(encoding="utf-8"))
            messages = json.loads(trace.read_text(encoding="utf-8"))
            self.assertEqual([message["method"] for message in messages], [
                "initialize", "initialized", "account/rateLimits/read",
            ])
            self.assertEqual(messages[0]["params"]["clientInfo"]["name"], "ai-workflow-usage-guard")
            self.assertEqual(record["state"], "SUSPENDED")
            self.assertEqual(record["unavailable_window_ids"], ["codex:secondary"])

    def test_opt_in_reader_timeout_fails_closed_and_replaces_stale_ok_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            output = directory / "flow-control.json"
            fake = write_fake_codex_app_server(directory, legacy_payload(), mode="stall")
            output.write_text('{"state":"OK"}\n', encoding="utf-8")

            started = time.monotonic()
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("usage_guard.py")),
                    "--read-codex-app-server",
                    "--codex-binary", str(fake),
                    "--app-server-timeout-seconds", "0.5",
                    "--flow-control", str(output),
                    "--now-epoch", str(NOW),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )

            record = json.loads(output.read_text(encoding="utf-8"))
            self.assertLess(time.monotonic() - started, 3)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(record["state"], "BLOCKED")
            self.assertIn("timed out", record["reason"])


if __name__ == "__main__":
    unittest.main()
