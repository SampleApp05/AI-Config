"""Small TOML reader for this repository's scalar, array, and table records."""

from __future__ import annotations

import ast
from pathlib import Path


def _value(raw: str):
    raw = raw.strip()
    if raw.startswith('"') or raw.startswith("["):
        return ast.literal_eval(raw)
    if raw == "true":
        return True
    if raw == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def load(path: Path) -> dict:
    result: dict = {}
    table = result
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            table = result
            for name in line[1:-1].split("."):
                table = table.setdefault(name, {})
            continue
        key, raw_value = line.split("=", 1)
        table[key.strip()] = _value(raw_value.split("#", 1)[0])
    return result
