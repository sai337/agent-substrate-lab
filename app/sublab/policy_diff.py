"""G2 promotion gate for Substrate EgressPolicy files: block unapproved widening
(new hostnames, new rule types, wildcards, all-ports)."""
from __future__ import annotations

from pathlib import Path

import yaml


def _grants(doc: dict) -> set[tuple[str, str, str]]:
    out = set()
    for rule in (doc or {}).get("rules") or []:
        for kind, body in (rule or {}).items():
            body = body or {}
            ports = "all" if "all" in (body.get("ports") or {}) else "default"
            for host in body.get("hostnames") or []:
                out.add((kind, str(host), ports))
    return out


def diff(old: dict, new: dict) -> list[tuple[str, str]]:
    """Returns (WIDEN|narrow, detail) pairs."""
    o, n = _grants(old), _grants(new)
    changes = [("WIDEN", f"+ {k} {h} ports={p}" + (" (wildcard)" if "*" in h else "")) for k, h, p in sorted(n - o)]
    changes += [("narrow", f"- {k} {h} ports={p}") for k, h, p in sorted(o - n)]
    return changes


def diff_files(old: str | Path, new: str | Path):
    load = lambda p: yaml.safe_load(Path(p).read_text()) or {}  # noqa: E731
    return diff(load(old), load(new))
