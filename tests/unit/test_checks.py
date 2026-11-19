import json

import pytest

from sublab.checks import _pct, run_all
from sublab.cli import to_markdown
from sublab.driver import FakeDriver, find_key

POLICY = "k8s/egress-allow-pypi.yaml"


def by_id(summary):
    return {r["id"]: r for r in summary["results"]}


def test_healthy_substrate_passes_every_check():
    s = run_all(FakeDriver(workers=3), actors=12, egress_policy=POLICY, host_kernel="6.8.0")
    assert s["gate"] == "pass", [r for r in s["results"] if r["status"] != "pass"]
    r = by_id(s)
    assert set(r) == {f"SUB-0{i}" for i in range(1, 9)}
    assert r["SUB-03"]["metrics"]["actors_per_worker"] == 4.0
    assert r["SUB-02"]["metrics"]["samples"] == 12


@pytest.mark.parametrize(
    "flags,blocker",
    [
        ({"keep_memory": False}, "SUB-01"),
        ({"deny_egress": False}, "SUB-04"),
        ({"leak_secrets": True}, "SUB-06"),
        ({"plain_kernel": True}, "SUB-07"),
        ({"resume_ms": 9000}, "SUB-02"),
    ],
)
def test_each_broken_guarantee_is_caught(flags, blocker):
    s = run_all(FakeDriver(**flags), actors=12, egress_policy=POLICY, host_kernel="6.8.0")
    assert s["gate"] == "fail"
    assert blocker in s["blocking_failures"]


def test_too_few_actors_is_not_a_multiplexing_test():
    s = run_all(FakeDriver(workers=3), actors=6, egress_policy=POLICY, host_kernel="6.8.0")
    assert by_id(s)["SUB-03"]["status"] == "fail"


def test_all_actors_deleted_even_on_error():
    class Exploding(FakeDriver):
        def workers(self):
            raise RuntimeError("api down")

    d = Exploding()
    s = run_all(d, actors=12, egress_policy=POLICY, host_kernel="6.8.0")
    assert "SUB-00" in s["blocking_failures"]
    assert d.actors == {}


def test_percentiles_and_find_key():
    assert _pct([], 95) == 0.0
    assert _pct([1, 2, 3, 4, 100], 50) == 3
    assert _pct([1, 2, 3, 4, 100], 100) == 100
    doc = {"actor": {"metadata": {"name": "a"}, "status": {"state": "ACTOR_STATE_SUSPENDED"}}}
    assert find_key(doc, "state") == "ACTOR_STATE_SUSPENDED"
    assert find_key([{"x": 1}, {"state": "S"}], "state") == "S"


def test_markdown_report():
    s = run_all(FakeDriver(deny_egress=False), actors=12, egress_policy=POLICY, host_kernel="6.8.0")
    s["meta"] = {"target": "kind"}
    md = to_markdown(s, "t")
    assert "Gate: FAIL" in md and "SUB-04" in md and "## Failures" in md
    json.dumps(s)  # serialisable


def test_golden_status():
    from sublab.cli import golden_status

    assert golden_status({"metadata": {"name": "t"}}) == "building"
    assert golden_status({"status": {"goldenTag": "golden-abc"}}) == "ready"
    assert golden_status({"status": {"goldenTag": "DISABLED"}}) == "building"
    assert golden_status({"status": {"goldenError": "image pull failed"}}) == "error"
    assert golden_status(None) == "building"
