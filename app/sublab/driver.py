"""How the harness talks to Agent Substrate. AteDriver shells out to
`kubectl ate`; FakeDriver models the semantics so unit tests need no cluster."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse
from dataclasses import dataclass, field


@dataclass
class Response:
    status: int
    body: dict
    ms: float


def find_key(obj, key):
    """Depth-first search for the first value under `key` in nested JSON."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = find_key(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = find_key(v, key)
            if found is not None:
                return found
    return None


class AteDriver:
    def __init__(self, atespace: str = "lab-agents", template: str = "memory-agent",
                 kubectl: str | None = None, base_port: int = 18100):
        self.a = atespace
        self.template = template
        self.kubectl = kubectl or os.environ.get("KUBECTL", "kubectl")
        self.base_port = base_port
        self._proxies: dict[str, tuple[subprocess.Popen, int]] = {}
        self._next = 0

    def _ate(self, *args: str, timeout: int = 300, check: bool = True) -> str:
        p = subprocess.run([self.kubectl, "ate", *args, "-a", self.a], capture_output=True, text=True, timeout=timeout)
        if check and p.returncode != 0:
            raise RuntimeError(f"kubectl ate {' '.join(args)}: {p.stderr.strip() or p.stdout.strip()}")
        return p.stdout

    def create(self, name: str) -> None:
        self._ate("create", "actor", name, "--template", self.template)

    def delete(self, name: str) -> None:
        self._close(name)
        self._ate("delete", "actor", name, check=False)

    def suspend(self, name: str) -> float:
        t0 = time.monotonic()
        self._ate("suspend", "actor", name, "--mode=sync")
        return (time.monotonic() - t0) * 1000

    def state(self, name: str) -> str:
        out = self._ate("get", "actor", name, "-o", "json")
        return str(find_key(json.loads(out), "state") or "UNKNOWN")

    def wait_state(self, name: str, want: str, timeout: float = 120) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.state(name).endswith(want):
                return True
            time.sleep(1)
        return False

    def set_egress(self, name: str, policy_file: str) -> None:
        with open(policy_file) as fh:
            p = subprocess.run([self.kubectl, "ate", "create", "egress-policy", name, "-a", self.a, "-f", "-"],
                               input=fh.read(), capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise RuntimeError(f"create egress-policy {name}: {p.stderr.strip()}")
        time.sleep(3)  # policy refresh reaches the gateway asynchronously

    def workers(self) -> int:
        out = subprocess.run([self.kubectl, "ate", "get", "workers", "-o", "json"], capture_output=True, text=True, timeout=60)
        try:
            data = json.loads(out.stdout)
            items = find_key(data, "workers") or find_key(data, "items") or []
            n = sum(1 for w in items if "memory-agent" in json.dumps(w))
            if n:
                return n
        except (ValueError, TypeError):
            pass
        return int(os.environ.get("SUBLAB_WORKERS", "3"))

    def _port(self, name: str) -> int:
        if name in self._proxies and self._proxies[name][0].poll() is None:
            return self._proxies[name][1]
        port = self.base_port + self._next
        self._next += 1
        proc = subprocess.Popen([self.kubectl, "ate", "proxy", "actor", name, f"{port}:8080", "-a", self.a],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.5)
        self._proxies[name] = (proc, port)
        return port

    def _close(self, name: str) -> None:
        proc, _ = self._proxies.pop(name, (None, 0))
        if proc:
            proc.terminate()

    def request(self, name: str, method: str, path: str, timeout: float = 180) -> Response:
        port = self._port(name)
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method, data=b"" if method == "POST" else None)
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body, status = json.loads(r.read() or b"{}"), r.status
        except urllib.error.HTTPError as e:
            body, status = {"error": e.reason}, e.code
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            body, status = {"error": str(e)}, 0
        return Response(status, body, (time.monotonic() - t0) * 1000)

    def close(self) -> None:
        for n in list(self._proxies):
            self._close(n)


@dataclass
class _Actor:
    memory: int = 0
    file: int = 0
    boot: int = 0
    running: bool = True
    allow: set = field(default_factory=set)


class FakeDriver:
    """Models Substrate semantics. Flags let tests break one guarantee at a time."""

    def __init__(self, workers: int = 3, keep_memory: bool = True, deny_egress: bool = True,
                 leak_secrets: bool = False, plain_kernel: bool = False, resume_ms: float = 120.0):
        self.w = workers
        self.keep_memory, self.deny_egress = keep_memory, deny_egress
        self.leak_secrets, self.plain_kernel, self.resume_ms = leak_secrets, plain_kernel, resume_ms
        self.actors: dict[str, _Actor] = {}
        self.max_running = 0
        self._boots = 0

    def create(self, name):
        self._boots += 1
        self.actors[name] = _Actor(boot=self._boots)
        self._track()

    def delete(self, name):
        self.actors.pop(name, None)

    def suspend(self, name):
        a = self.actors[name]
        a.running = False
        if not self.keep_memory:
            a.memory = 0
            self._boots += 1
            a.boot = self._boots
        return 40.0

    def state(self, name):
        return "ACTOR_STATE_RUNNING" if self.actors[name].running else "ACTOR_STATE_SUSPENDED"

    def wait_state(self, name, want, timeout=120):
        return self.state(name).endswith(want)

    def set_egress(self, name, policy_file):
        self.actors[name].allow.add("pypi.org")

    def workers(self):
        return self.w

    def _track(self):
        running = [n for n, a in self.actors.items() if a.running]
        while len(running) > self.w:  # a full pool evicts (suspends) the oldest idle actor
            self.suspend(running.pop(0))
        self.max_running = max(self.max_running, len(running))

    def request(self, name, method, path, timeout=180):
        a = self.actors[name]
        ms = 5.0
        if not a.running:
            a.running, ms = True, self.resume_ms
            self._track()
        if path.startswith("/remember"):
            a.memory += 1
            a.file += 1
        if path.startswith(("/remember", "/recall")):
            return Response(200, {"memory_count": a.memory, "file_count": a.file, "boot_id": str(a.boot)}, ms)
        if path.startswith("/fetch"):
            host = urlparse(parse_qs(urlparse(path).query)["url"][0]).hostname
            ok = (not self.deny_egress) or host in a.allow
            return Response(200, {"ok": ok}, ms)
        if path.startswith("/selfcheck"):
            return Response(200, {"kernel_release": "6.8.0" if self.plain_kernel else "4.4.0", "uid": 65532,
                                  "sa_token": self.leak_secrets,
                                  "secret_env": ["OPENAI_API_KEY"] if self.leak_secrets else []}, ms)
        return Response(404, {}, ms)

    def close(self):
        pass
