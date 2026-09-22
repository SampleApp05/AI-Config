#!/usr/bin/env python3
"""Dry-run tests for the dispatcher against mocked targets in scratch repositories."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import dispatch  # noqa: E402


class Fixture(unittest.TestCase):
    """Scratch repositories and a CLI runner; holds no tests of its own."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.artifact = base / "artifacts"
        self.product = base / "product"
        for root in (self.artifact, self.product):
            root.mkdir()
        (self.product / "src").mkdir()
        (self.product / "src" / "a.ts").write_text("a\n")
        (self.product / "node_modules").mkdir()
        self.prompt = base / "prompt.md"
        self.state_dir = base / "state"

    def tearDown(self):
        self.tmp.cleanup()

    def run_dispatch(self, target, label, mode, scope_lines, mock, env=None, timeout="30"):
        self.prompt.write_text("Task body.\n" + "\n".join(scope_lines) + "\n")
        environment = dict(os.environ, WORKFLOW_DISPATCH_ALLOW_MOCK="1", WORKFLOW_DISPATCH_MOCK_COMMAND=mock,
                           WORKFLOW_DISPATCH_TIMEOUT_SECONDS=timeout, WORKFLOW_STATE_DIR=str(self.state_dir))
        environment.update(env or {})
        completed = subprocess.run(
            [str(SCRIPTS / "dispatch.sh"), target, label, mode, str(self.prompt), str(self.artifact), str(self.product)],
            capture_output=True, text=True, env=environment, check=False)
        stream = completed.stdout if completed.stdout.strip() else completed.stderr
        return completed.returncode, json.loads(stream)


class DispatchTest(Fixture):
    def test_artifact_success_writes_only_assigned_path(self):
        code, result = self.run_dispatch(
            "claude-cli", "[CLAUDE][STAGE] ARC", "architecture",
            ["WORKFLOW_ARTIFACT_PATH=solution_architect/architecture-v1.md"],
            "mkdir -p solution_architect && echo ok > solution_architect/architecture-v1.md")
        self.assertEqual((code, result["outcome"]), (0, "success"))
        self.assertEqual(result["changed_files"], ["artifacts:solution_architect/architecture-v1.md"])

    def test_artifact_scope_violation_fails(self):
        code, result = self.run_dispatch(
            "claude-cli", "[CLAUDE][STAGE] ARC", "artifact",
            ["WORKFLOW_ARTIFACT_PATH=solution_architect/architecture-v1.md"],
            "mkdir -p solution_architect && echo ok > solution_architect/architecture-v1.md && echo x > manifest.yaml")
        self.assertEqual((code, result["outcome"]), (6, "scope-violation"))
        self.assertEqual(result["scope_violation"], ["artifacts:manifest.yaml"])

    def test_artifact_mode_treats_product_repo_as_read_only(self):
        code, result = self.run_dispatch(
            "claude-cli", "[CLAUDE][STAGE] ARC", "artifact",
            ["WORKFLOW_ARTIFACT_PATH=a.md"], "echo ok > a.md && echo x > %s/src/a.ts" % self.product)
        self.assertEqual((code, result["outcome"]), (6, "scope-violation"))
        self.assertEqual(result["scope_violation"], ["product:src/a.ts"])

    def test_execution_allows_directory_prefix_and_result_artifact(self):
        code, result = self.run_dispatch(
            "claude-cli", "[CLAUDE][EXEC] EU-01", "execution",
            ["WORKFLOW_ALLOWED_PATH=src/", "WORKFLOW_RESULT_ARTIFACT_PATH=implementation_worker/result-v1.md"],
            "echo b > src/b.ts && mkdir -p %s/implementation_worker && echo ok > %s/implementation_worker/result-v1.md"
            % (self.artifact, self.artifact))
        self.assertEqual((code, result["outcome"]), (0, "success"))

    def test_execution_ignores_dependency_directories(self):
        code, result = self.run_dispatch(
            "claude-cli", "[CLAUDE][EXEC] EU-01", "execution", ["WORKFLOW_ALLOWED_PATH=src/a.ts"],
            "echo changed > src/a.ts && echo junk > node_modules/x.js")
        self.assertEqual((code, result["outcome"]), (0, "success"))
        self.assertEqual(result["changed_files"], ["product:src/a.ts"])

    def test_execution_out_of_scope_edit_fails(self):
        code, result = self.run_dispatch(
            "claude-cli", "[CLAUDE][EXEC] EU-01", "execution", ["WORKFLOW_ALLOWED_PATH=src/a.ts"],
            "echo changed > src/a.ts && echo x > src/other.ts")
        self.assertEqual((code, result["outcome"]), (6, "scope-violation"))

    def test_timeout_kills_target(self):
        code, result = self.run_dispatch(
            "claude-cli", "[CLAUDE][EXEC] EU-01", "execution", ["WORKFLOW_ALLOWED_PATH=src/a.ts"],
            "sleep 30", timeout="1")
        self.assertEqual((code, result["outcome"]), (124, "timeout"))

    def test_timeout_follows_only_recorded_fallback(self):
        mock = 'if [ "$WORKFLOW_TARGET_ID" = claude-cli ]; then sleep 30; else echo "$WORKFLOW_TARGET_ID" > src/a.ts; fi'
        code, result = self.run_dispatch(
            "claude-cli", "[CLAUDE][EXEC] EU-01", "execution", ["WORKFLOW_ALLOWED_PATH=src/a.ts"], mock,
            env={"WORKFLOW_FALLBACK_CHAIN": "mac-ollama", "WORKFLOW_ROLE": "implementation_worker"}, timeout="1")
        self.assertEqual((code, result["outcome"], result["target"]), (0, "success", "mac-ollama"))
        self.assertEqual(result["label"], "[LOCAL][EXEC] EU-01")
        self.assertEqual([a["outcome"] for a in result["attempts"]], ["timeout", "success"])

    def test_no_fallback_without_recorded_chain(self):
        mock = 'if [ "$WORKFLOW_TARGET_ID" = claude-cli ]; then sleep 30; fi'
        code, result = self.run_dispatch(
            "claude-cli", "[CLAUDE][EXEC] EU-01", "execution", ["WORKFLOW_ALLOWED_PATH=src/a.ts"], mock, timeout="1")
        self.assertEqual((code, len(result["attempts"])), (124, 1))

    def test_failed_run_never_falls_back(self):
        code, result = self.run_dispatch(
            "claude-cli", "[CLAUDE][EXEC] EU-01", "execution", ["WORKFLOW_ALLOWED_PATH=src/a.ts"], "exit 7",
            env={"WORKFLOW_FALLBACK_CHAIN": "codex"})
        self.assertEqual((code, result["outcome"], len(result["attempts"])), (7, "failed", 1))

    def test_fallback_skips_targets_not_eligible_for_role(self):
        mock = 'if [ "$WORKFLOW_TARGET_ID" = claude-cli ]; then sleep 30; fi'
        code, result = self.run_dispatch(
            "claude-cli", "[CLAUDE][STAGE] ARC", "artifact", ["WORKFLOW_ARTIFACT_PATH=a.md"], mock,
            env={"WORKFLOW_FALLBACK_CHAIN": "mac-ollama", "WORKFLOW_ROLE": "solution_architect"}, timeout="1")
        self.assertEqual([a["outcome"] for a in result["attempts"]], ["timeout", "unsuitable"])
        self.assertEqual(code, 124)

    def test_hard_limits_make_local_target_unsuitable_without_running(self):
        files = ["WORKFLOW_ALLOWED_PATH=src/f%d.ts" % index for index in range(7)]
        code, result = self.run_dispatch("mac-ollama", "[LOCAL][EXEC] EU-01", "execution", files, "echo ran > src/f0.ts")
        self.assertEqual((code, result["outcome"], result["changed_files"]), (3, "unsuitable", []))
        self.assertIn("max_files", result["attempts"][0]["reason"])

    def test_mock_requires_explicit_opt_in(self):
        self.prompt.write_text("WORKFLOW_ARTIFACT_PATH=a.md\n")
        environment = {key: value for key, value in os.environ.items() if not key.startswith("WORKFLOW_DISPATCH_")}
        environment["WORKFLOW_DISPATCH_MOCK_COMMAND"] = "true"
        environment["WORKFLOW_STATE_DIR"] = str(self.state_dir)
        completed = subprocess.run(
            [str(SCRIPTS / "dispatch.sh"), "claude-cli", "[CLAUDE] x", "artifact", str(self.prompt), str(self.artifact), str(self.product)],
            capture_output=True, text=True, env=environment, check=False)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("ALLOW_MOCK", completed.stderr)

    def test_label_must_carry_target_prefix(self):
        code, result = self.run_dispatch("claude-cli", "[LOCAL] wrong", "artifact", ["WORKFLOW_ARTIFACT_PATH=a.md"], "true")
        self.assertEqual((code, result["outcome"]), (2, "invalid-dispatch"))

    def test_scope_markers_reject_escapes(self):
        code, result = self.run_dispatch("claude-cli", "[CLAUDE] x", "execution", ["WORKFLOW_ALLOWED_PATH=../outside"], "true")
        self.assertEqual((code, result["outcome"]), (2, "invalid-dispatch"))

    def test_scoped_profile_limits_edits_and_bash_to_the_scope(self):
        scope = dispatch.Scope("WORKFLOW_ALLOWED_PATH=src/a.ts\nWORKFLOW_ALLOWED_PATH=lib/\nWORKFLOW_VALIDATION_COMMAND=pnpm test\n",
                               "execution", self.artifact, self.product)
        target = dict(dispatch.resolve_target("claude-cli"), permissions={"profile": "scoped"})
        allow = json.loads(dispatch.claude_settings(scope, target))["permissions"]["allow"]
        self.assertIn("Edit(//%s/src/a.ts)" % str(self.product).lstrip("/"), allow)
        self.assertIn("Write(//%s/lib/**)" % str(self.product).lstrip("/"), allow)
        self.assertIn("Bash(pnpm test)", allow)
        self.assertNotIn("Bash", allow)

    def test_developer_profile_allows_tools_and_edits_under_the_developer_folder(self):
        scope = dispatch.Scope("WORKFLOW_ALLOWED_PATH=src/a.ts\n", "execution", self.artifact, self.product)
        target = dispatch.resolve_target("claude-cli")
        allow = json.loads(dispatch.claude_settings(scope, target))["permissions"]["allow"]
        for tool in ("Bash", "Read", "WebFetch"):
            self.assertIn(tool, allow)
        self.assertIn("Edit(//Users/danielvelikov/Developer/**)", allow)
        self.assertIn("Edit(//%s/**)" % str(self.product).lstrip("/"), allow)
        directories = dispatch.writable_directories(target, scope, self.product, self.artifact, self.product)
        self.assertIn("/Users/danielvelikov/Developer", directories)
        self.assertIn(str(self.artifact), directories)
        self.assertNotIn(str(self.product), directories)

    def test_health_reports_unavailable_ollama(self):
        target = dict(dispatch.resolve_target("mac-ollama"), ollama_base_url="http://127.0.0.1:9")
        environment = {key: value for key, value in os.environ.items() if key != "WORKFLOW_DISPATCH_MOCK_COMMAND"}
        saved = dict(os.environ)
        os.environ.clear()
        os.environ.update(environment)
        try:
            healthy, detail = dispatch.health(target)
        finally:
            os.environ.clear()
            os.environ.update(saved)
        self.assertFalse(healthy)
        self.assertIn("unreachable", detail)


def event(kind, **fields):
    return "echo '%s'" % json.dumps(dict(type=kind, **fields))


def limit_event(five_hour_used, resets_in, seven_day_used=0.1):
    windows = {"five_hour": {"utilization": five_hour_used, "resetsAt": int(time.time()) + resets_in},
               "seven_day": {"utilization": seven_day_used, "resetsAt": 9999999999}}
    return "echo '%s'" % json.dumps({"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": windows}})


class JobTest(Fixture):
    """Detached jobs, stall detection, usage suspension, and resume."""

    def cli(self, *args, env=None, mock=None):
        environment = dict(os.environ, WORKFLOW_DISPATCH_ALLOW_MOCK="1", WORKFLOW_STATE_DIR=str(self.state_dir),
                           WORKFLOW_RESUME_BUFFER_SECONDS="0")
        if mock is not None:
            environment["WORKFLOW_DISPATCH_MOCK_COMMAND"] = mock
        environment.update(env or {})
        completed = subprocess.run([str(SCRIPTS / "dispatch.sh")] + list(args), capture_output=True, text=True, env=environment, check=False)
        return completed.returncode, json.loads(completed.stdout) if completed.stdout.strip().startswith(("{", "[")) else completed.stdout

    def start(self, mock, scope=("WORKFLOW_ALLOWED_PATH=src/a.ts",), target="claude-cli", label="[CLAUDE][EXEC] EU-01", env=None):
        self.prompt.write_text("Task.\n" + "\n".join(scope) + "\n")
        return self.cli("start", target, label, "execution", str(self.prompt), str(self.artifact), str(self.product), env=env, mock=mock)

    def test_start_returns_immediately_and_status_reports_progress(self):
        tool = json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "x.ts"}}]}})
        mock = "for i in 1 2 3; do echo '%s'; sleep 1; done; echo done > src/a.ts" % tool
        started = time.time()
        code, job = self.start(mock)
        self.assertEqual((code, job["state"]), (0, "queued"))
        self.assertLess(time.time() - started, 3)
        time.sleep(2.5)
        code, status = self.cli("status", job["job_id"])
        self.assertEqual(code, 10)
        self.assertEqual(status["state"], "running")
        self.assertGreaterEqual(status["turns"], 1)
        self.assertEqual(status["last_activity"], "Read x.ts")
        code, final = self.cli("wait", job["job_id"], "--seconds", "20")
        self.assertEqual((code, final["state"], final["turns"], final["tool_calls"]), (0, "success", 3, 3))
        self.assertEqual((self.product / "src" / "a.ts").read_text(), "done\n")
        self.assertEqual(self.cli("list")[1][0]["state"], "success")

    def test_wait_returns_running_after_its_window(self):
        code, job = self.start("sleep 30")
        code, status = self.cli("wait", job["job_id"], "--seconds", "3")
        self.assertEqual((code, status["state"]), (10, "running"))
        self.cli("cancel", job["job_id"])

    def test_cancel_stops_the_target(self):
        code, job = self.start("sleep 60")
        time.sleep(1.5)
        code, status = self.cli("cancel", job["job_id"])
        self.assertEqual((status["state"], status["outcome"]), ("cancelled", "cancelled"))

    def test_idle_timeout_stops_a_stalled_target_but_output_keeps_it_alive(self):
        code, job = self.start("echo started; sleep 30", env={"WORKFLOW_IDLE_TIMEOUT_SECONDS": "2", "WORKFLOW_DISPATCH_TIMEOUT_SECONDS": "0"})
        code, final = self.cli("wait", job["job_id"], "--seconds", "20")
        self.assertEqual((code, final["state"]), (124, "timeout"))
        self.assertEqual(json.loads((Path(job["job_dir"]) / "result.json").read_text())["timeout_reason"], "no output")
        code, job = self.start("for i in 1 2 3 4; do echo tick; sleep 1; done", env={"WORKFLOW_IDLE_TIMEOUT_SECONDS": "3", "WORKFLOW_DISPATCH_TIMEOUT_SECONDS": "0"})
        code, final = self.cli("wait", job["job_id"], "--seconds", "20")
        self.assertEqual((code, final["state"]), (0, "success"))

    def test_no_turn_limit_and_stream_output_for_claude(self):
        scope = dispatch.Scope("WORKFLOW_ALLOWED_PATH=src/a.ts\n", "execution", self.artifact, self.product)
        target = dispatch.resolve_target("claude-cli")
        saved = dict(os.environ)
        os.environ.pop("WORKFLOW_DISPATCH_MOCK_COMMAND", None)
        os.environ.pop("CLAUDE_WORKER_MAX_TURNS", None)
        try:
            command, stdin = dispatch.target_command(target, "l", self.prompt, "task", scope, 60, self.artifact, self.product, self.product, None, False)
            self.assertNotIn("--max-turns", command)
            self.assertIn("stream-json", command)
            self.assertEqual(stdin, "task")
            resumed, note = dispatch.target_command(target, "l", self.prompt, "task", scope, 60, self.artifact, self.product, self.product, "sess-9", True)
            self.assertEqual(resumed[resumed.index("--resume") + 1], "sess-9")
            self.assertEqual(note, dispatch.RESUME_NOTE)
            os.environ["CLAUDE_WORKER_MAX_TURNS"] = "5"
            self.assertIn("--max-turns", dispatch.target_command(target, "l", self.prompt, "task", scope, 60, self.artifact, self.product, self.product, None, False)[0])
            codex = dispatch.target_command(dispatch.resolve_target("codex"), "l", self.prompt, "task", scope, 60, self.artifact, self.product, self.product, "thr-1", True)[0]
            self.assertEqual(codex[1:3], ["exec", "resume"])
            self.assertIn('sandbox_mode="workspace-write"', codex)
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def test_usage_threshold_suspends_mid_run_and_resumes_the_same_session(self):
        mock = ('if [ "$WORKFLOW_RESUME_COUNT" = "0" ]; then %s; %s; sleep 60; '
                'else echo "$WORKFLOW_RESUME_SESSION" > src/a.ts; %s; fi') % (
            event("system", subtype="init", session_id="sess-1"), limit_event(0.95, 7),
            event("result", subtype="success", is_error=False, result="done"))
        code, job = self.start(mock)
        time.sleep(2.5)
        code, status = self.cli("status", job["job_id"])
        self.assertEqual((code, status["state"]), (11, "suspended"))
        self.assertIn("resume_at_iso", status)
        code, final = self.cli("wait", job["job_id"], "--seconds", "30")
        self.assertEqual((code, final["state"]), (0, "success"))
        result = json.loads((Path(job["job_dir"]) / "result.json").read_text())
        self.assertEqual((result["resumes"], result["session_id"], len(result["suspensions"])), (1, "sess-1", 1))
        self.assertEqual((self.product / "src" / "a.ts").read_text(), "sess-1\n")

    def test_blocking_window_stops_the_job_for_a_human(self):
        mock = "%s; %s; sleep 60" % (event("system", subtype="init", session_id="s"), limit_event(0.2, 100, seven_day_used=0.95))
        code, job = self.start(mock)
        code, final = self.cli("wait", job["job_id"], "--seconds", "20")
        self.assertEqual((code, final["state"]), (4, "blocked"))

    def test_preflight_uses_recorded_fallback_when_primary_is_usage_limited(self):
        usage_file = self.state_dir.parent / "usage.json"
        usage_file.write_text(json.dumps({
            "claude-code": {"five_hour": {"used": 0.95, "resets_at": time.time() + 300}, "seven_day": {"used": 0.1, "resets_at": 9999999999}},
            "codex-cli": {"five_hour": {"used": 0.1, "resets_at": time.time() + 300}, "seven_day": {"used": 0.1, "resets_at": 9999999999}}}))
        code, job = self.start('echo "$WORKFLOW_TARGET_ID" > src/a.ts', env={"WORKFLOW_FALLBACK_CHAIN": "codex", "WORKFLOW_USAGE_MOCK_FILE": str(usage_file)})
        code, final = self.cli("wait", job["job_id"], "--seconds", "20")
        result = json.loads((Path(job["job_dir"]) / "result.json").read_text())
        self.assertEqual((code, result["target"]), (0, "codex"))
        self.assertEqual([a["outcome"] for a in result["attempts"]], ["usage-limited", "success"])

    def test_preflight_waits_for_reset_when_no_fallback_is_available(self):
        usage_file = self.state_dir.parent / "usage.json"
        usage_file.write_text(json.dumps({"claude-code": {"five_hour": {"used": 0.97, "resets_at": time.time() + 6}, "seven_day": {"used": 0.1, "resets_at": 9999999999}}}))
        code, job = self.start("echo ran > src/a.ts", env={"WORKFLOW_USAGE_MOCK_FILE": str(usage_file)})
        time.sleep(1.5)
        self.assertEqual(self.cli("status", job["job_id"])[1]["state"], "suspended")
        code, final = self.cli("wait", job["job_id"], "--seconds", "30")
        result = json.loads((Path(job["job_dir"]) / "result.json").read_text())
        self.assertEqual((code, result["suspensions"][0]["reason"]), (0, "preflight"))
        self.assertEqual((self.product / "src" / "a.ts").read_text(), "ran\n")

    def test_codex_usage_limit_message_suspends_then_resumes_thread(self):
        usage_file = self.state_dir.parent / "usage.json"
        usage_file.write_text(json.dumps({"codex-cli": {"five_hour": {"used": 0.1, "resets_at": time.time() + 3}, "seven_day": {"used": 0.1, "resets_at": 9999999999}}}))
        message = "You have hit your usage limit. Try again at 11:25 PM."
        mock = ('if [ "$WORKFLOW_RESUME_COUNT" = "0" ]; then %s; %s; exit 1; else echo "$WORKFLOW_RESUME_SESSION" > src/a.ts; fi') % (
            event("thread.started", thread_id="thr-7"), event("turn.failed", error={"message": message}))
        code, job = self.start(mock, target="codex", label="[CODEX][EXEC] EU-01", env={"WORKFLOW_USAGE_MOCK_FILE": str(usage_file)})
        code, final = self.cli("wait", job["job_id"], "--seconds", "30")
        self.assertEqual((code, final["state"]), (0, "success"))
        self.assertEqual((self.product / "src" / "a.ts").read_text(), "thr-7\n")

    def test_repeated_permission_denials_stop_the_job_instead_of_burning_usage(self):
        denied = json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True, "content": "This command requires approval"}]}})
        code, job = self.start("for i in 1 2 3 4 5 6; do echo '%s'; sleep 1; done; echo late > src/a.ts" % denied)
        code, final = self.cli("wait", job["job_id"], "--seconds", "30")
        self.assertEqual((code, final["state"]), (7, "permission-denied"))
        self.assertEqual(final["permission_denial_count"], 3)
        self.assertEqual((self.product / "src" / "a.ts").read_text(), "a\n")

    def test_a_single_denial_is_reported_but_does_not_stop_the_job(self):
        denied = json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True, "content": "ls was blocked. For security, Claude Code may only list files in the allowed working directories"}]}})
        code, job = self.start("echo '%s'; sleep 2; echo ok > src/a.ts" % denied)
        time.sleep(1.5)
        status = self.cli("status", job["job_id"])[1]
        self.assertIn("1 permission denial", status["warning"])
        code, final = self.cli("wait", job["job_id"], "--seconds", "20")
        self.assertEqual((code, final["state"]), (0, "success"))

    def test_codex_command_adds_the_other_roots_as_writable(self):
        scope = dispatch.Scope("WORKFLOW_ALLOWED_PATH=src/a.ts\n", "execution", self.artifact, self.product)
        saved = dict(os.environ)
        os.environ.pop("WORKFLOW_DISPATCH_MOCK_COMMAND", None)
        try:
            command = dispatch.target_command(dispatch.resolve_target("codex"), "l", self.prompt, "t", scope, 60, self.artifact, self.product, self.product, None, False)[0]
        finally:
            os.environ.clear()
            os.environ.update(saved)
        added = [command[i + 1] for i, part in enumerate(command) if part == "--add-dir"]
        self.assertEqual(sorted(added), sorted(["/Users/danielvelikov/Developer", str(self.artifact)]))


class UsageTest(unittest.TestCase):
    def test_decide_suspends_on_five_hour_and_blocks_on_weekly(self):
        import usage
        future = time.time() + 600
        self.assertEqual(usage.decide({"five_hour": {"used": 0.5, "resets_at": future}})["action"], "ok")
        self.assertEqual(usage.decide({"five_hour": {"used": 0.91, "resets_at": future}})["action"], "suspend")
        self.assertEqual(usage.decide({"five_hour": {"used": 0.1, "resets_at": future}, "seven_day": {"used": 0.95, "resets_at": future}})["action"], "blocked")
        self.assertEqual(usage.decide({"five_hour": {"used": 1.0, "resets_at": time.time() - 5}})["action"], "ok")
        self.assertEqual(usage.decide(None)["action"], "ok")

    def test_claude_rate_limit_event_is_normalised(self):
        import usage
        windows = usage.windows_from_claude_event({"rate_limit_info": {"unifiedWindows": {
            "five_hour": {"utilization": 0.33, "resetsAt": 1789943400}, "seven_day": {"utilization": 0.13, "resetsAt": 1790265600}}}})
        self.assertEqual(windows["five_hour"], {"used": 0.33, "resets_at": 1789943400})

    def test_policy_reads_float_headroom(self):
        import usage
        self.assertAlmostEqual(usage.policy()["suspend_when_headroom_below"], 0.10)


if __name__ == "__main__":
    unittest.main()
