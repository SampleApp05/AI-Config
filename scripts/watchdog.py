#!/usr/bin/env python3
"""Run one command with a bounded lifetime, including all of its children."""

from __future__ import annotations

import os
import signal
import subprocess
import sys


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: watchdog.py <timeout-seconds> <command> [args...]", file=sys.stderr)
        return 2
    try:
        timeout = int(argv[1])
    except ValueError:
        print("timeout must be a positive integer", file=sys.stderr)
        return 2
    if timeout < 1:
        print("timeout must be a positive integer", file=sys.stderr)
        return 2

    process = subprocess.Popen(argv[2:], start_new_session=True)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        return 124


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
