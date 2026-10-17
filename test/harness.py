"""Helpers for running the original and the rebuilt image side by side.

Only the Python standard library and the docker CLI are used.
"""
import os
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

ORIG_IMAGE = os.environ.get("ORIG_IMAGE", "nginx:1.25-bookworm")
NEW_IMAGE = os.environ.get("NEW_IMAGE", "echo/nginx:1.25-bookworm")
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIGS = os.path.join(HERE, "configs")

# Headers that legitimately differ between two runs of the same image.
VOLATILE_HEADERS = {"date"}
# Headers derived from file mtimes. Packaged files (e.g. /usr/share/nginx/html)
# were built at different times, so these are only compared for mounted content.
MTIME_HEADERS = {"etag", "last-modified"}


def docker(*args: str, check: bool = True) -> str:
    res = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} failed:\n{res.stderr}")
    return res.stdout + (res.stderr if not check else "")


@dataclass
class Container:
    image: str
    name: str
    network: str
    mounts: List[Tuple[str, str]] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    ports: Dict[int, int] = field(default_factory=dict)

    def start(self) -> "Container":
        args = ["run", "-d", "--name", self.name, "--network", self.network,
                "-p", "127.0.0.1::80", "-p", "127.0.0.1::443"]
        for src, dst in self.mounts:
            args += ["-v", f"{src}:{dst}:ro"]
        for k, v in self.env.items():
            args += ["-e", f"{k}={v}"]
        docker(*args, self.image)
        for cport in (80, 443):
            self.ports[cport] = self._published_port(cport)
        self._wait_ready()
        return self

    def _published_port(self, cport: int, timeout: float = 10) -> int:
        """Look up the host port for `cport`, tolerating the create->publish race.

        Right after `docker run -d`, the port mapping can briefly be
        unqueryable (Docker Desktop under load), or the container may have
        exited on startup. Retry for a short window; if the container is no
        longer running, surface its logs rather than the cryptic
        "No public port" error from `docker port`.
        """
        deadline = time.time() + timeout
        while True:
            res = subprocess.run(["docker", "port", self.name, f"{cport}/tcp"],
                                 capture_output=True, text=True)
            lines = res.stdout.strip().splitlines()
            if res.returncode == 0 and lines:
                return int(lines[0].rsplit(":", 1)[1])
            if not self.running():
                raise RuntimeError(f"{self.name} exited before publishing "
                                   f"{cport}/tcp:\n{self.logs()}")
            if time.time() >= deadline:
                raise RuntimeError(f"docker port {self.name} {cport}/tcp failed:\n"
                                   f"{res.stderr}")
            time.sleep(0.3)

    def _wait_ready(self, timeout: float = 30) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.running():
                raise RuntimeError(f"{self.name} exited:\n{self.logs()}")
            try:
                with socket.create_connection(("127.0.0.1", self.ports[80]), 1) as s:
                    s.sendall(b"HEAD / HTTP/1.0\r\n\r\n")
                    if s.recv(16).startswith(b"HTTP/"):
                        return
            except OSError:
                pass
            time.sleep(0.3)
        raise RuntimeError(f"{self.name} not ready:\n{self.logs()}")

    def running(self) -> bool:
        return docker("inspect", "-f", "{{.State.Running}}", self.name).strip() == "true"

    def logs(self) -> str:
        return docker("logs", self.name, check=False)

    def exec(self, *cmd: str) -> str:
        return docker("exec", self.name, *cmd, check=False)

    def stop(self) -> None:
        docker("rm", "-f", self.name, check=False)


class Pair:
    """The same configuration started from the original and from the new image."""

    def __init__(self, network: str, label: str, mounts=None, env=None):
        tag = uuid.uuid4().hex[:6]
        self.orig = Container(ORIG_IMAGE, f"compat-{label}-orig-{tag}", network,
                              list(mounts or []), dict(env or {}))
        self.new = Container(NEW_IMAGE, f"compat-{label}-new-{tag}", network,
                             list(mounts or []), dict(env or {}))

    def __enter__(self) -> "Pair":
        try:
            self.orig.start()
            self.new.start()
        except Exception:
            self.__exit__()
            raise
        return self

    def __exit__(self, *exc) -> None:
        self.orig.stop()
        self.new.stop()


@dataclass
class Response:
    status: int
    reason: str
    headers: List[Tuple[str, str]]
    body: bytes

    def header(self, name: str) -> Optional[str]:
        for k, v in self.headers:
            if k.lower() == name.lower():
                return v
        return None

    def normalized(self, ignore=frozenset()) -> tuple:
        skip = VOLATILE_HEADERS | {h.lower() for h in ignore}
        hdrs = tuple((k.lower(), v) for k, v in self.headers if k.lower() not in skip)
        return (self.status, self.reason, hdrs, self.body)


def raw_exchange(port: int, data: bytes, timeout: float = 10) -> bytes:
    """Send raw bytes, read until the server closes the connection."""
    with socket.create_connection(("127.0.0.1", port), timeout) as s:
        try:
            s.sendall(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # e.g. 413: the server answers before reading the whole body
        chunks = []
        while True:
            try:
                b = s.recv(65536)
            except (socket.timeout, ConnectionResetError):
                break
            if not b:
                break
            chunks.append(b)
    return b"".join(chunks)


def parse_responses(raw: bytes, head: bool = False) -> List[Response]:
    """Parse one or more HTTP/1.x responses (Content-Length or chunked bodies)."""
    out = []
    while raw:
        head_end = raw.find(b"\r\n\r\n")
        if head_end < 0:
            raise ValueError(f"incomplete response: {raw[:200]!r}")
        lines = raw[:head_end].decode("latin-1").split("\r\n")
        _, status, reason = (lines[0].split(" ", 2) + [""])[:3]
        headers = [tuple(x.strip() for x in l.split(":", 1)) for l in lines[1:]]
        rest = raw[head_end + 4:]
        resp = Response(int(status), reason, headers, b"")
        te = (resp.header("transfer-encoding") or "").lower()
        cl = resp.header("content-length")
        if head or resp.status in (204, 304) or 100 <= resp.status < 200:
            body, rest = b"", rest
        elif te == "chunked":
            body = b""
            while True:
                size_end = rest.find(b"\r\n")
                size = int(rest[:size_end].split(b";")[0], 16)
                rest = rest[size_end + 2:]
                if size == 0:
                    rest = rest[rest.find(b"\r\n") + 2:]
                    break
                body += rest[:size]
                rest = rest[size + 2:]
        elif cl is not None:
            body, rest = rest[:int(cl)], rest[int(cl):]
        else:
            body, rest = rest, b""
        resp.body = body
        out.append(resp)
        raw = rest
    return out


def request(port: int, method: str = "GET", path: str = "/", headers=None,
            body: bytes = b"", version: str = "HTTP/1.1") -> Response:
    hdrs = {"Host": "localhost", "Connection": "close"}
    hdrs.update(headers or {})
    if body:
        hdrs["Content-Length"] = str(len(body))
    head = f"{method} {path} {version}\r\n" + "".join(
        f"{k}: {v}\r\n" for k, v in hdrs.items() if v is not None) + "\r\n"
    raw = raw_exchange(port, head.encode("latin-1") + body)
    return parse_responses(raw, head=(method == "HEAD"))[0]
