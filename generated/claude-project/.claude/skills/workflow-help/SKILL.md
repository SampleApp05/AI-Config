---
name: workflow-help
description: Show configured governed workflow agents and preferred stage owners when the user asks for workflow-help or available workflow agents.
---
> Shared workflow root for this installation: `/Users/danielvelikov/Developer/AI-Workflow`. Registry, script, and skill locations named below are relative to it; export it as `WORKFLOW_SHARED_ROOT` when running its scripts.


# Workflow Help

Run `workflow-help` to list active backends, specialist roles, stage preferences, and modes. Run `workflow-help <agent-id>` for one backend's capabilities and invocation, or `workflow-help <role-id>` for its preferred and eligible backends. Report reachability only after a fresh health check; listing an agent does not mean it is online. A user's request for a specific agent overrides preferences when the agent fits the task, is healthy, and preserves required review independence. If it cannot safely handle the work, explain the exact constraint and offer a capable option.
