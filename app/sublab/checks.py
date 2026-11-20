"""The Agent Substrate checks: does it keep its promises for stateful,
untrusted, mostly-idle agents?"""
from __future__ import annotations

import os
import platform
import statistics
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import quote

VENDOR_RESUME_CLAIM_MS = 500  # README v1.0.0: "fast resume operations in less than 500ms" (GKE, vendor-reported)


@dataclass
class Check:
    id: str
    title: str
    severity: str
    status: str = "pass"  # pass | fail | error
    metrics: dict = field(default_factory=dict)
    note: str = ""


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, round(p / 100 * (len(s) - 1))))
    return round(s[k], 1)


def _fetch(d, actor, url):
    return d.request(actor, "GET", "/fetch?url=" + quote(url, safe=""))


def run_all(d, actors: int, egress_policy: str, resume_budget_ms: float | None = None,
            host_kernel: str | None = None) -> dict:
    budget = resume_budget_ms or float(os.environ.get("SUBLAB_RESUME_P95_MS", "5000"))
    host_kernel = host_kernel or platform.release()
    names = [f"agent-{i:03d}" for i in range(actors)]
    out: list[Check] = []
    created: list[str] = []
    started = time.time()
    try:
        # SUB-08 cold start from the template's golden snapshot
        c = Check("SUB-08", "New actor starts from the golden snapshot and answers", "medium")
        t0 = time.monotonic()
        d.create(names[0])
        created.append(names[0])
        r = d.request(names[0], "GET", "/recall")
        c.metrics = {"create_to_first_response_ms": round((time.monotonic() - t0) * 1000, 1)}
        if r.status != 200:
            c.status, c.note = "fail", f"first request status {r.status}: {r.body}"
        out.append(c)

        # SUB-01 full state round trip on one actor
        c = Check("SUB-01", "RAM and disk state survive suspend and resume (same process, not a reboot)", "critical")
        a = names[0]
        for i in range(3):
            d.request(a, "POST", f"/remember?note=n{i}")
        before = d.request(a, "GET", "/recall").body
        c.metrics["suspend_ms"] = round(d.suspend(a), 1)
        suspended = d.wait_state(a, "SUSPENDED", 120)
        after = d.request(a, "GET", "/recall").body
        c.metrics.update({"before": before, "after": after, "observed_suspended": suspended})
        if not suspended:
            c.status, c.note = "fail", "actor never reached SUSPENDED"
        elif (after.get("memory_count"), after.get("file_count")) != (3, 3) or after.get("boot_id") != before.get("boot_id"):
            c.status, c.note = "fail", "state lost or process rebooted across the snapshot"
        out.append(c)

        # SUB-03 multiplexing many actors onto few workers
        c = Check("SUB-03", f"{actors} stateful actors share a small worker pool without losing state", "critical")
        # Like real agents: work, then go idle (suspend) so the worker is free for the next one.
        for n in names[1:]:
            d.create(n)
            created.append(n)
            d.request(n, "POST", "/remember?note=hello")
            d.suspend(n)
        bad = []
        for n in names[1:]:
            if d.request(n, "GET", "/recall").body.get("memory_count") != 1:
                bad.append(n)
            d.suspend(n)
        workers = d.workers()
        ratio = round(actors / max(workers, 1), 2)
        c.metrics = {"actors": actors, "workers": workers, "actors_per_worker": ratio, "lost_state": bad}
        if bad:
            c.status, c.note = "fail", f"{len(bad)} actors lost state"
        elif ratio < 3:
            c.status, c.note = "fail", "fewer than 3 actors per worker: not a multiplexing test"
        out.append(c)

        # SUB-02 resume latency across all actors (request-driven resume through the router)
        c = Check("SUB-02", "Suspended actors resume on demand within budget", "high")
        lat = []
        d.suspend(names[0])  # SUB-01 left it running
        for n in names:  # every actor is suspended here; time the request-driven resume
            r = d.request(n, "GET", "/recall")
            if r.status == 200:
                lat.append(r.ms)
            d.suspend(n)
        c.metrics = {"samples": len(lat), "p50_ms": _pct(lat, 50), "p95_ms": _pct(lat, 95),
                     "max_ms": _pct(lat, 100), "budget_p95_ms": budget,
                     "vendor_claim_ms": VENDOR_RESUME_CLAIM_MS,
                     "mean_ms": round(statistics.fmean(lat), 1) if lat else 0}
        if len(lat) < len(names):
            c.status, c.note = "fail", f"{len(names) - len(lat)} resumes failed"
        elif c.metrics["p95_ms"] > budget:
            c.status, c.note = "fail", f"p95 {c.metrics['p95_ms']}ms over budget {budget}ms"
        c.note = c.note or "Measured end to end through `kubectl ate proxy` (includes the local proxy hop)."
        out.append(c)

        # SUB-04 / SUB-05 egress
        probe = names[-1]
        c = Check("SUB-04", "Egress is denied by default (no policy = no tunnel)", "critical")
        r = _fetch(d, probe, "https://pypi.org/simple/")
        c.metrics = {"pypi_without_policy": r.body}
        if r.body.get("ok"):
            c.status, c.note = "fail", "actor reached the internet with no egress policy"
        out.append(c)

        c = Check("SUB-05", "EgressPolicy allows only the listed host", "critical")
        try:
            d.set_egress(probe, egress_policy)
            # Upstream: a new policy reaches the actor's DNS relay "within about 5 seconds".
            t0 = time.monotonic()
            allowed = _fetch(d, probe, "https://pypi.org/simple/").body
            while not allowed.get("ok") and time.monotonic() - t0 < float(os.environ.get("SUBLAB_POLICY_WAIT_S", "30")):
                time.sleep(2)
                allowed = _fetch(d, probe, "https://pypi.org/simple/").body
            c.metrics["policy_effective_after_s"] = round(time.monotonic() - t0, 1)
            other = _fetch(d, probe, "https://example.com/").body
            c.metrics.update({"pypi_with_policy": allowed, "example_com": other})
            if not allowed.get("ok"):
                c.status, c.note = "fail", "allowed host was blocked"
            elif other.get("ok"):
                c.status, c.note = "fail", "unlisted host got through"
        except Exception as e:  # policy API failure is an error, not a pass
            c.status, c.note = "error", str(e)[-400:]
        out.append(c)

        # SUB-06 / SUB-07 what a hostile agent can see
        sc = d.request(probe, "GET", "/selfcheck")
        info = sc.body
        c = Check("SUB-06", "No service-account token or secrets inside the actor", "critical", metrics=info)
        if sc.status != 200 or "sa_token" not in info:
            c.status, c.note = "error", f"self-check did not answer (status {sc.status}): {info}"
        elif info.get("sa_token") or info.get("secret_env"):
            c.status, c.note = "fail", "credentials reachable from untrusted code"
        out.append(c)
        c = Check("SUB-07", "Actor runs on a sandbox kernel (gVisor), not the host kernel", "high",
                  metrics={"actor_kernel": info.get("kernel_release"), "host_kernel": host_kernel})
        if not info.get("kernel_release") or info.get("kernel_release") == host_kernel:
            c.status, c.note = "fail", "actor sees the host kernel: not sandboxed"
        out.append(c)
    except Exception as e:
        out.append(Check("SUB-00", "Harness completed", "critical", "error", note=str(e)[-600:]))
    finally:
        for n in created:
            try:
                d.delete(n)
            except Exception:
                pass
        d.close()

    order = ["SUB-01", "SUB-02", "SUB-03", "SUB-04", "SUB-05", "SUB-06", "SUB-07", "SUB-08", "SUB-00"]
    out.sort(key=lambda c: order.index(c.id))
    counts = {s: sum(c.status == s for c in out) for s in ("pass", "fail", "error")}
    blocking = [c.id for c in out if c.status != "pass" and c.severity in ("critical", "high")]
    return {"started_at": started, "finished_at": time.time(), "counts": counts,
            "gate": "pass" if not blocking else "fail", "blocking_failures": blocking,
            "results": [asdict(c) for c in out]}
