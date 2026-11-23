from sublab.cli import main
from sublab.policy_diff import diff

BASE = {"rules": [{"https": {"hostnames": ["pypi.org"]}}]}


def test_no_change():
    assert diff(BASE, BASE) == []


def test_widening_and_narrowing():
    new = {"rules": [{"https": {"hostnames": ["pypi.org", "*.github.com"]}}, {"http": {"hostnames": ["example.com"], "ports": {"all": {}}}}]}
    tags = [t for t, _ in diff(BASE, new)]
    assert tags.count("WIDEN") == 2 and any("wildcard" in d for _, d in diff(BASE, new))
    assert [t for t, _ in diff(new, BASE)] == ["narrow", "narrow"]


def test_cli_gate(tmp_path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    a.write_text("rules:\n- https: {hostnames: [pypi.org]}\n")
    b.write_text("rules:\n- https: {hostnames: [pypi.org, api.openai.com]}\n")
    assert main(["policy-diff", str(a), str(b)]) == 1
    assert main(["policy-diff", str(a), str(b), "--approved-by", "owner"]) == 0
