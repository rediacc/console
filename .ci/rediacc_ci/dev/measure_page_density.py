#!/usr/bin/env python3
"""The one measurement harness for page-density work. Frozen build only, never a dev server.

Ported from `packages/www/scripts/measure-page-density.sh` (PLAN-retire-bash-oracles B5, W10).

    PYTHONPATH=.ci python3 -m rediacc_ci.dev.measure_page_density [out.csv]

WHY NOT THE DEV SERVER. One server, one working tree, HMR. `packages/www/.astro/` is derived from `config.root` with no override, so ANY build rewrites the cache every running dev server in the checkout reads. A stale dev server does not fail: it serves a SMALLER page, and a census against one returns plausible numbers that describe less site. See .claude/agents/browser-probe.md.

THREE THINGS ARE VERIFIED BEFORE ANY NUMBER IS TRUSTED, because each has produced internally consistent fiction in this repo before:

  1. the listening pid is the server THIS run started, not a squatter on the port
  2. the served page links a hashed asset that is present in the dist on disk
  3. every page clears a DOM-node FLOOR; a wiped dist once returned success with 5 nodes

PORT NOTES.

`agent-browser open`'s EXIT STATUS NEVER DECIDES CONTROL FLOW, and the reason is measured: it exits 1 when its stdout is REDIRECTED and 0 on a terminal, for the same URL that loads correctly either way, and the `eval` immediately after returns a real scrollHeight in both cases. Under the bash `set -e` that killed the run at the first page, silently, with an empty log and a CSV holding only its header. A genuinely failed load is still caught, by the DOM-node FLOOR, which is a statement about the page rather than about a wrapper's exit code. `rediacc_ci.quality.agent_browser_exit` guards this for shell and JavaScript; here the status is read and dropped on purpose.

`open --viewport WxH` is SILENTLY IGNORED: it reports 1280x577 whatever is passed, and so does a bare `viewport 1280 900`. The width happens to be the 1280 wanted, so every reflow-dependent number is sound; the HEIGHT never was. Screens are `scrollHeight / innerHeight` with `innerHeight` read back, never a height that was asked for.

The `eval` result is PARSED as JSON, not grepped: a `"?h"?:[0-9]+` grep also matches the `h` inside `vph`.

DELIBERATE DELTAS FROM THE BASH (Rule T), each with a test in `test_dev_measure_page_density.py`:

  * The server's pid is found from `/proc` (the listening socket's inode against each process's open files), not by parsing `ss -lptn`, so the check no longer depends on `ss` being installed and on its column format.
  * The server is polled until it answers (up to ten seconds) instead of sleeping two seconds and hoping. A slow start used to read as "port not served by our pid".
  * A missing `agent-browser` is named. The bash swallowed the 127 with `|| true`, `eval` printed nothing, and the run died on "0 DOM nodes", which reads as a wiped dist.
  * The default CSV path is in the system temp directory rather than a hard-coded `/tmp`.
  * The CSV is rewritten after every page, so a run that dies on page 12 leaves 11 rows rather than the header alone.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import pathlib
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime

from rediacc_ci import paths

FLOOR = 50
MIN_VIEWPORT = 200
PORT_BASE = 20000
PORT_SPAN = 40001
SERVER_WAIT_SECONDS = 10
VIEWPORT = "1280x900"
HOME_PAGES = ("for-devops", "for-ctos", "for-ceos", "for-ai-agents")
HEADER = "slug,height,screens,words,atoms,nodes"
ASSET_RE = re.compile(r"/assets/[A-Za-z0-9_.-]+\.(?:css|js)")
JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
EVAL_JS = (
    "JSON.stringify({vph:innerHeight,vpw:innerWidth,"
    "h:document.documentElement.scrollHeight,"
    "words:(document.body.innerText||'').trim().split(/\\s+/).filter(Boolean).length,"
    "atoms:document.body.querySelectorAll('h1,h2,h3,h4,li,td,th,[class*=card],[class*=chip],"
    "[class*=stat],[class*=step],[class*=item],[class*=row]').length,"
    "nodes:document.body.querySelectorAll('*').length})"
)


class MeasureError(Exception):
    """A verification failed, so no number from this run can be trusted."""


def parse_eval(raw: str) -> dict | None:
    """The metrics object from `agent-browser eval`'s output, or None when there is none.

    The output may quote the JSON string (escaped quotes), so those are unescaped first; the object is then the widest `{...}` in the text.
    """
    text = raw.strip().replace('\\"', '"')
    match = JSON_RE.search(text)
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    needed = ("h", "words", "atoms", "nodes", "vph", "vpw")
    if not isinstance(data, dict) or any(k not in data for k in needed):
        return None
    return data


def listening_pids(port: int, proc: pathlib.Path = pathlib.Path("/proc")) -> set[int]:
    """Pids holding a LISTEN socket on `port`, read from /proc (IPv4 and IPv6)."""
    inodes: set[str] = set()
    for table in ("net/tcp", "net/tcp6"):
        try:
            lines = (proc / table).read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[3] != "0A":
                continue
            if int(fields[1].rsplit(":", 1)[1], 16) == port:
                inodes.add(fields[9])
    if not inodes:
        return set()
    wanted = {"socket:[%s]" % inode for inode in inodes}
    pids: set[int] = set()
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            for fd in (entry / "fd").iterdir():
                if os.readlink(fd) in wanted:
                    pids.add(int(entry.name))
                    break
        except OSError:
            continue
    return pids


def _connectable(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0


def pick_port() -> int:
    """A random port in 20000-60000 that nothing is listening on right now."""
    for _ in range(50):
        port = PORT_BASE + secrets.randbelow(PORT_SPAN)
        if not _connectable(port):
            return port
    raise MeasureError("no free port found in %d-%d" % (PORT_BASE, PORT_BASE + PORT_SPAN - 1))


def fetch(port: int, path: str) -> str:
    conn = http.client.HTTPConnection("localhost", port, timeout=10)
    try:
        conn.request("GET", path)
        return conn.getresponse().read().decode("utf-8", errors="replace")
    finally:
        conn.close()


def wait_for_server(port: int) -> None:
    deadline = time.monotonic() + SERVER_WAIT_SECONDS
    while time.monotonic() < deadline:
        if _connectable(port):
            return
        time.sleep(0.1)
    raise MeasureError(
        "the server did not start listening on %d within %ds" % (port, SERVER_WAIT_SECONDS)
    )


def verify_server(port: int, server_pid: int, dist: pathlib.Path) -> None:
    """Checks 1 and 2: the listener is ours, and the served page links an asset that is in dist.

    An EMPTY needle is a failure, not a pass: that is how check 2 went vacuous the first time it was written.
    """
    if server_pid not in listening_pids(port):
        raise MeasureError(
            "port %d is not served by our pid %d. Another server holds it; every byte would be theirs."
            % (port, server_pid)
        )
    try:
        html = fetch(port, "/en/")
    except OSError:
        html = ""
    found = ASSET_RE.search(html)
    if found is None:
        raise MeasureError("no hashed asset in the served HTML; refusing to call this verified")
    asset = found.group(0)
    if not (dist / asset.lstrip("/")).is_file():
        raise MeasureError("served %s is not in dist/; reading someone else's build" % asset)


def run_browser(*args: str) -> str:
    """One agent-browser call. The exit status is read and dropped: see the module docstring."""
    try:
        proc = subprocess.run(
            ["agent-browser", *args],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise MeasureError("agent-browser is not on PATH") from exc
    return proc.stdout


def measure(port: int, path: str, label: str) -> str:
    """One CSV row for one page. Raises when the page fails the floor or reports no viewport."""
    run_browser("open", "http://localhost:%d%s" % (port, path), "--viewport", VIEWPORT)
    raw = run_browser("eval", EVAL_JS)
    last = raw.strip().splitlines()[-1] if raw.strip() else ""
    data = parse_eval(last)
    if data is None or int(data["nodes"]) < FLOOR:
        raise MeasureError(
            "FLOOR: %s has %s DOM nodes (< %d). That is not a page."
            % (label, data["nodes"] if data else "no", FLOOR)
        )
    vph = int(data["vph"])
    if vph < MIN_VIEWPORT:
        raise MeasureError(
            "VIEWPORT: %s reported innerHeight=%d. Refusing to invent screens." % (label, vph)
        )
    height = int(data["h"])
    return "%s,%d,%s,%d,%d,%d" % (
        label,
        height,
        round(height / vph, 1),
        int(data["words"]),
        int(data["atoms"]),
        int(data["nodes"]),
    )


def page_list(www: pathlib.Path) -> list[tuple[str, str]]:
    """(url path, label) for every solution page, then the home and persona pages."""
    pages = []
    solutions = www / "src" / "pages" / "[lang]" / "solutions"
    for page in sorted(solutions.glob("*.astro")):
        if page.stem == "index":
            continue
        pages.append(("/en/solutions/%s/" % page.stem, page.stem))
    pages.append(("/en/", "home"))
    pages.extend(("/en/%s/" % name, name) for name in HOME_PAGES)
    return pages


def column_table(csv_text: str) -> str:
    """`column -s, -t`: left-aligned cells, two spaces between columns."""
    rows = [line.split(",") for line in csv_text.splitlines() if line]
    widths = [max(len(r[i]) for r in rows if i < len(r)) for i in range(max(len(r) for r in rows))]
    lines = []
    for row in rows:
        cells = [cell.ljust(widths[i]) for i, cell in enumerate(row[:-1])] + [row[-1]]
        lines.append("  ".join(cells))
    return "\n".join(lines)


def main(argv: list[str] | None = None, www: pathlib.Path | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    www = www or paths.repo_root() / "packages" / "www"
    dist = www / "dist"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    default_out = pathlib.Path(tempfile.gettempdir()) / ("page-density-%s.csv" % stamp)
    out = pathlib.Path(argv[0]) if argv else default_out
    if not dist.is_dir():
        print("no dist/. Run: npm run build -w @rediacc/www", file=sys.stderr)
        return 1
    if shutil.which("agent-browser") is None:
        print("agent-browser is not on PATH", file=sys.stderr)
        return 1

    port = pick_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--directory", str(dist)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    try:
        wait_for_server(port)
        verify_server(port, server.pid, dist)
        runtime = os.environ.get("XDG_RUNTIME_DIR") or str(
            pathlib.Path.home() / ".cache" / "xdg-runtime"
        )
        os.environ["XDG_RUNTIME_DIR"] = runtime
        pathlib.Path(runtime).mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("AGENT_BROWSER_SESSION", "page-density")
        rows = [HEADER]
        out.write_text(HEADER + "\n", encoding="utf-8")
        for path, label in page_list(www):
            rows.append(measure(port, path, label))
            out.write_text("\n".join(rows) + "\n", encoding="utf-8")
    except MeasureError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        server.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            server.wait(timeout=5)
        if server.poll() is None:
            server.kill()
    print("wrote %s" % out)
    print(column_table(out.read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
