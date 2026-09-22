# Local worker MCP

This host-agnostic stdio MCP service delegates bounded coding work to Mac-side
Aider. Target facts—including Ollama model, endpoint, workspace host, and hard
limits—come exclusively from the shared target registry. The worker never owns
workflow state, validation, manifests, or human gates.

Its dedicated environment pins the Python MCP SDK to the compatible 1.x API via
`requirements.txt`.

It exposes two tools:

- `run_local_worker` receives an explicit Git root, file allowlist, prompt, and
  canonical target id (or documented legacy alias). It checks model availability
  and every registered hard limit before Aider edits workspace files.
- `local_worker_status` reports target availability for manual monitoring. It
  does not reserve capacity or prevent concurrent calls.

The cloud parent remains responsible for reviewing the diff, running tests and
other validation, committing, pushing, and requesting review. If a target is
offline, unsuitable, or fails validation, use only its preauthorized fallback.
