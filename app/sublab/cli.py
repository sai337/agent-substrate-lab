"""sublab: run the Agent Substrate checks and write a report.

    sublab run --actors 12 --out evals/results/2026-11-19-kind
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .checks import run_all
from .driver import AteDriver


def to_markdown(s: dict, title: str) -> str:
    when = datetime.fromtimestamp(s["finished_at"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    c = s["counts"]
    lines = [f"# {title}", "", f"Run: {when} · target: `{s.get('meta', {}).get('target', '?')}`", "",
             f"**Gate: {s['gate'].upper()}** · pass {c['pass']} · fail {c['fail']} · error {c['error']}", "",
             "| Check | Result | Severity | What it checks | Key numbers |", "|---|---|---|---|---|"]
    for r in s["results"]:
        m = r["metrics"]
        keys = {k: m[k] for k in ("p50_ms", "p95_ms", "actors_per_worker", "create_to_first_response_ms", "suspend_ms", "actor_kernel") if k in m}
        lines.append(f"| {r['id']} | {r['status'].upper()} | {r['severity']} | {r['title']} | {json.dumps(keys) if keys else ''} |")
    bad = [r for r in s["results"] if r["status"] != "pass"]
    if bad:
        lines += ["", "## Failures", ""] + [f"- **{r['id']}**: {r['note']}" for r in bad]
    lines += ["", "Resume times are measured on this cluster through `kubectl ate proxy`. The vendor figure (<500 ms) is GKE-reported and not comparable to kind."]
    return "\n".join(lines) + "\n"


def _ate_json(*args: str):
    import subprocess
    p = subprocess.run(["kubectl", "ate", *args, "-o", "json"], capture_output=True, text=True, timeout=60)
    return json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else None


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def golden_status(doc) -> str:
    """ready | error | building, from an ActorTemplate JSON document."""
    for path, v in _walk(doc or {}):
        low = path.lower()
        if "error" in low and v:
            return "error"
        if "golden" in low and "tag" in low and isinstance(v, str) and v and v != "DISABLED":
            return "ready"
    return "building"


def cmd_wait(a) -> int:
    import time
    end = time.monotonic() + a.timeout
    while time.monotonic() < end:
        if a.what == "template":
            st = golden_status(_ate_json("get", "actor-template", a.name, "-a", a.atespace))
            print("golden snapshot:", st, flush=True)
            if st != "building":
                return 0 if st == "ready" else 1
        else:
            doc = _ate_json("get", "workers") or {}
            n = sum(1 for _, v in _walk(doc) if v == a.name)
            print(f"workers in pool {a.name}: {n}/{a.count}", flush=True)
            if n >= a.count:
                return 0
        time.sleep(5)
    return 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="sublab")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--actors", type=int, default=12)
    r.add_argument("--atespace", default="lab-agents")
    r.add_argument("--egress-policy", default="k8s/egress-allow-pypi.yaml")
    r.add_argument("--target", default="kind")
    r.add_argument("--out", required=True)
    r.add_argument("--title", default="Agent Substrate lab checks")
    w = sub.add_parser("wait", help="wait for a template's golden snapshot or a worker pool")
    w.add_argument("what", choices=["template", "workers"])
    w.add_argument("--name", default="memory-agent")
    w.add_argument("--atespace", default="lab-agents")
    w.add_argument("--count", type=int, default=3)
    w.add_argument("--timeout", type=int, default=600)
    a = p.parse_args(argv)
    if a.cmd == "wait":
        return cmd_wait(a)
    summary = run_all(AteDriver(atespace=a.atespace), a.actors, a.egress_policy)
    summary["meta"] = {"target": a.target, "actors": a.actors}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(summary, indent=2))
    md = to_markdown(summary, a.title)
    (out / "summary.md").write_text(md)
    print(md)
    return 0 if summary["gate"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
