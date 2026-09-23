---
name: workflow-dispatch
description: Supervise one approved Claude relay job and report compact state. Native Codex and local-worker jobs use their own registered tools, never this dispatcher.
---
> Shared workflow root for this installation: `/Users/danielvelikov/Developer/AI-Workflow`. Registry, script, and skill locations named below are relative to it; export it as `WORKFLOW_SHARED_ROOT` when running its scripts.


# Workflow Dispatch

This dispatcher accepts only `claude-cli`. The approved Orchestration Plan or Routing Plan supplies the role, scope, and fallback pool; actual target choice is recorded at dispatch after a fresh health and usage observation. Native Codex work uses native subagents. Local work uses the registered local-worker service. Never call nested `codex exec`, invoke Claude directly, or treat a worker's text as proof of work.

Write the bounded assignment to a prompt file. An artifact task declares exactly one `WORKFLOW_ARTIFACT_PATH=<artifact-repo-relative path>`. An execution unit declares its approved `WORKFLOW_ALLOWED_PATH=<product-repo-relative path or directory/>` markers, optional `WORKFLOW_RESULT_ARTIFACT_PATH`, and exact `WORKFLOW_VALIDATION_COMMAND` markers. Generate all markers from approved scope, not worker suggestions. Set `WORKFLOW_ROLE` and the recorded fallback chain in the environment.

Start a durable job with `python3 $WORKFLOW_SHARED_ROOT/scripts/submit.py claude-cli <label> <artifact|execution> <prompt-file> <artifact-root> <product-root> <job-dir>`. The job directory must be a bounded private path. Poll `python3 $WORKFLOW_SHARED_ROOT/scripts/poll.py <job-dir>` for compact status and flow-control; never stream raw provider JSONL or full changed-file audits into chat. Follow `resume_state.child_job_dir` when a parent has a resumed child. For a short call only, `$WORKFLOW_SHARED_ROOT/scripts/dispatch.sh claude-cli ...` can run directly.

The relay uses `Read,Glob,Grep,Write,Edit`; Bash is added only for an explicitly authorized artifact-stage prompt carrying `WORKFLOW_CLAUDE_ALLOW_BASH=true`. It audits changed paths after the run. No default turn, wall-clock, or inactivity timeout applies. At 15 minutes without activity report `QUIET`; at 30 minutes report `STALLED_SUSPECTED`, keeping the worker alive. The orchestrator posts a status heartbeat every 15 minutes and immediate start/completion, gate, warning, fallback, blocker, and validation events. Ask a human whether to wait 15 minutes and report again, stop with checkpoint, or use an approved fallback only when intervention would help. Never silently kill or reroute.

At usage `WARNING`, report remaining headroom and reset time. At `SUSPENDED`, preserve the checkpoint and stop scheduling new work. Resume exactly once through `python3 $WORKFLOW_SHARED_ROOT/scripts/resume.py <parent-job-dir>` only after the verified reset boundary. A `BLOCKED` state, missing reset time, unsafe checkpoint, or unavailable target without approved fallback requires human direction. On completion, inspect the actual diff and scope audit and run independent validation before accepting the result. Record actual target, elapsed time, known usage/reset, outcome, fallback, and evidence in the controller records.
