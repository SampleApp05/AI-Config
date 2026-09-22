"""Plain stdio MCP boundary for registry-driven bounded local-worker edits."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from worker import run_local_worker as _run_local_worker
from worker import status as _status


mcp = FastMCP(
    "local_worker",
    instructions=(
        "Run bounded registered Ollama targets through Mac-side Aider. "
        "Targets, models, endpoints, and hard limits are loaded from the shared workflow registry."
    ),
)


@mcp.tool()
def local_worker_status() -> dict:
    """Report local target availability; the result is not a capacity lock."""
    return _status()


@mcp.tool()
def run_local_worker(
    label: str,
    repository: str,
    allowed_files: list[str],
    prompt: str,
    timeout_seconds: int = 900,
    target: str = "mac-ollama",
) -> dict:
    """Run one bounded target using an approved repository-relative file allowlist."""
    return _run_local_worker(label, repository, allowed_files, prompt, timeout_seconds, target)


if __name__ == "__main__":
    mcp.run(transport="stdio")
