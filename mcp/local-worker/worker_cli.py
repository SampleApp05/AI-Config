#!/usr/bin/env python3
"""CLI entry point used by the engine-neutral dispatcher for Ollama targets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worker import run_local_worker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("label")
    parser.add_argument("repository")
    parser.add_argument("prompt_file", type=Path)
    parser.add_argument("--allowed-file", action="append", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=None)
    args = parser.parse_args()
    result = run_local_worker(
        args.label,
        args.repository,
        args.allowed_file,
        args.prompt_file.read_text(encoding="utf-8"),
        timeout_seconds=args.timeout_seconds,
        target=args.target,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
