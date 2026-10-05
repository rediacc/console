#!/usr/bin/env python3
"""GitHub's own service status, read once per 15 minutes per MACHINE and shown to every agent session without being asked for.

WHY. This repo's whole delivery loop runs on GitHub: Actions runs every gate, the PR is the unit of work, `gh` and the REST/GraphQL API are how every CI read happens, git pushes are the backups, and ghcr.io carries the CI images. When GitHub itself is degraded, a session reading "no runs yet" or "still queued" has no way to tell a slow runner pool from a broken workflow, and on 2026-10-05 (indicator minor, "Incident with Actions": runner assignment delays) that is exactly the question sessions were burning turns on. Operator request 2026-10-05: check GitHub's status automatically, cache it for 15 minutes, and survive the status API failing too.

THE SOURCE. githubstatus.com is an Atlassian Statuspage; `/api/v2/summary.json` is unauthenticated and carries, in one ~7 KB response, the page indicator, every component's status, and the unresolved incidents with their latest update. One call, everything.

WHICH COMPONENTS COUNT (`RELEVANT_COMPONENTS`), each with the evidence that this repo depends on it:

- Actions: every CI and CD workflow under .github/workflows (28 files).
- API Requests: `gh`, ci-trace.py, the Stop hook's wl_ci reads and every `gh api` call go through it.
- Git Operations: pushes are the backup and the CI trigger; submodule fetches ride on it too.
- Pull Requests: one PR per branch is the unit of work; the rollup ci-trace reads is a PR's.
- Webhooks: every workflow trigger (push, pull_request, `workflow_run` in ci-verdict.yml) is a webhook delivery.
- Issues: PR comments are issue comments (wl_prreview.py answers the review summary through them), and nightly-status.yml opens the rolling nightly-red issue.
- Packages: ghcr.io carries the CI images in ten workflows (ci.yml, cd-v2.yml, ci-vm-bake.yml, ...).

LEFT OUT on purpose: Pages (the "pages" in cd-deploy-worker.yml are the www site's, deployed to Cloudflare, not GitHub Pages), Codespaces (only a `customizations.codespaces` block in .devcontainer/devcontainer.json; sessions run in the devbox), Copilot and its model providers (nothing here calls them). A degraded component outside the list reads `ok`: the page's own indicator goes minor for a Copilot incident, and that is not a reason to doubt a CI verdict.

THE CACHE is one JSON file per machine, `core_lease.lease_dir() / "github-status.json"`, shared by every checkout, session and devbox: the lease directory is bound into the devbox, so host and container read the same answer, and fifteen sessions polling every stop cost one request per 15 minutes in total. A fresh entry (younger than `max_age_s`) is served with no network. Writes are tmp + os.replace, so a reader never sees half a file; a file that does not parse is ignored as if absent.

FAILURE. Any fetch failure (network, HTTP, a body that is not the expected shape) serves the last good answer marked `stale` with its age and the error, or `unknown` with the error when there was never one. A failure is remembered for `NEGATIVE_TTL_S` (60 s), so a status page that is down is not asked again by every hook call in that minute. Neither read raises: every caller is a hook or a verdict printer, and a status note must never be the thing that breaks them.

NO HOOK WAITS ON THE NETWORK (operator ruling 2026-10-05: "it should not block us much"). Two reads, split by who may wait. `read` fetches in the foreground with a 5 s timeout and is for the CLI and the refresher. `read_cached` is for every automatic surface (SessionStart, the post-bash note, the Stop advisory, ci-trace): it reads the file only, and when the file is old or missing it starts ONE detached refresher (`--refresh-bg`, its own session, no pipes, never waited on, single-flighted by a flock on `github-status.lock` beside the cache) and answers with what the file holds now. The suite pins it: each surface returns in under 200 ms with a fetch that sleeps 30 s.

RECOVERY IS ANNOUNCED TOO (operator, 2026-10-05: "when github solves the issues, the system will catch and notify"). The cache keeps a transition record (`advance_history`): the current state, when it began, a generation counter, and on a degraded -> ok flip what recovered. Every surface goes through `surface`, which prints the degraded line while GitHub is degraded and, after a flip, one `GITHUB RECOVERED: ...` note per session per recovery (a marker file per session under `github-status-seen/`), then nothing. A session that wants to be WOKEN rather than told at its next tool call runs `--wait-recovery` in the background: a background task re-invokes the session only by exiting, and the waiter exits exactly on recovery. Every degraded line ends with that command.

CLI: `PYTHONPATH=.ci python3 -m rediacc_ci.ci.github_status [--json] [--refresh] [--line] [--wait-recovery [--timeout MIN]]`.
  (no flag)        one human line, `GITHUB: operational ...` when all is well.
  --line           the one line the surfaces print, or NOTHING when GitHub is ok.
  --json           the whole Status as JSON.
  --refresh        ignore the cache (positive and negative) and fetch now.
  --wait-recovery  block until every relevant component is operational, then print one
                   `GITHUB RECOVERED` line and exit 0; exit 2 after --timeout minutes
                   (default 240). Polls the shared cache every 30 s and refetches only
                   when it is older than 150 s.
Exit 0 ok, 1 degraded, 3 unknown.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import fcntl
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

SUMMARY_URL = "https://www.githubstatus.com/api/v2/summary.json"
CACHE_NAME = "github-status.json"
MAX_AGE_S = 900
NEGATIVE_TTL_S = 60
FETCH_TIMEOUT_S = 5
LOCK_NAME = "github-status.lock"
SEEN_DIR = "github-status-seen"
RECOVERY_NOTE_MAX_AGE_S = 3 * 3600
WAIT_POLL_S = 30
WAIT_REFRESH_S = 150
WAIT_DEFAULT_MIN = 240
WAIT_CMD = "PYTHONPATH=.ci python3 -m rediacc_ci.ci.github_status --wait-recovery"

RELEVANT_COMPONENTS = (
    "Actions",
    "API Requests",
    "Git Operations",
    "Pull Requests",
    "Webhooks",
    "Issues",
    "Packages",
)

EXIT_OK = 0
EXIT_DEGRADED = 1
EXIT_WAIT_TIMEOUT = 2
EXIT_UNKNOWN = 3

_SENTENCE_END = re.compile(r"(?<=[.!?])\s")
_UPDATE_MAX = 200


@dataclasses.dataclass
class Status:
    state: str  # "ok" | "degraded" | "unknown"
    indicator: str | None = None
    description: str | None = None
    components: list[dict] = dataclasses.field(default_factory=list)
    incidents: list[dict] = dataclasses.field(default_factory=list)
    fetched_at: float | None = None
    age_s: float | None = None
    stale: bool = False
    error: str | None = None
    since: float | None = None
    gen: int = 0
    recovered: dict | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _core_lease():
    """`rediacc_ci.core_lease`, or the sibling file loaded by path: the Stop hook and ci-trace load THIS module by file, where the package is not importable by name."""
    try:
        from rediacc_ci import core_lease  # noqa: PLC0415 -- the fallback below needs the failure

        return core_lease
    except ImportError:
        path = pathlib.Path(__file__).resolve().parents[1] / "core_lease.py"
        spec = importlib.util.spec_from_file_location("rediacc_core_lease_for_github_status", path)
        if spec is None or spec.loader is None:
            raise
        mod = importlib.util.module_from_spec(spec)
        # Registered BEFORE it runs: a dataclass resolves its module through sys.modules while the class is built.
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod


def cache_path() -> pathlib.Path:
    """The machine-wide cache file, beside the core lease (module docstring, THE CACHE)."""
    return _core_lease().lease_dir() / CACHE_NAME


def fetch_summary() -> bytes:
    """One GET of summary.json, bounded by `FETCH_TIMEOUT_S`. Raises on any failure; `read` turns that into a stale or unknown answer."""
    # Imported here, not at the top: urllib.request costs ~50 ms to import, and every hook-side caller loads this module without ever fetching.
    import urllib.request  # noqa: PLC0415

    req = urllib.request.Request(
        SUMMARY_URL,
        headers={"User-Agent": "rediacc-ci-github-status", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:  # noqa: S310 -- a fixed https URL, never caller input
        return resp.read()


def _first_sentence(text: str) -> str:
    flat = " ".join(str(text or "").split())
    first = _SENTENCE_END.split(flat, maxsplit=1)[0]
    if len(first) > _UPDATE_MAX:
        first = first[: _UPDATE_MAX - 3].rstrip() + "..."
    return first


def parse_summary(body: bytes | str) -> dict:
    """The fields this module keeps, out of a summary.json body. Raises ValueError (not JSON) or TypeError (wrong shape) on a body that is not the expected shape, so a captive portal's HTML or a changed API reads as a failed fetch rather than as `ok`."""
    doc = json.loads(body)
    if not isinstance(doc, dict):
        msg = "summary.json is not an object"
        raise TypeError(msg)
    status = doc.get("status")
    comps = doc.get("components")
    if not isinstance(status, dict) or not isinstance(status.get("indicator"), str):
        msg = "summary.json has no status.indicator"
        raise TypeError(msg)
    if not isinstance(comps, list):
        msg = "summary.json has no components list"
        raise TypeError(msg)
    components = {
        str(c["name"]): str(c.get("status") or "")
        for c in comps
        if isinstance(c, dict) and isinstance(c.get("name"), str)
    }
    incidents = []
    for inc in doc.get("incidents") or []:
        if not isinstance(inc, dict):
            continue
        updates = inc.get("incident_updates") or []
        latest = updates[0] if updates and isinstance(updates[0], dict) else {}
        incidents.append(
            {
                "name": str(inc.get("name") or ""),
                "status": str(inc.get("status") or ""),
                "impact": str(inc.get("impact") or ""),
                "components": [
                    str(c.get("name"))
                    for c in inc.get("components") or []
                    if isinstance(c, dict) and c.get("name")
                ],
                "update": _first_sentence(latest.get("body") or ""),
            }
        )
    return {
        "indicator": status["indicator"],
        "description": str(status.get("description") or ""),
        "components": components,
        "incidents": incidents,
    }


def _touches_relevant(incident: dict) -> bool:
    """An incident counts when it names a relevant component. One posted before GitHub attached components (an early "Incident with Actions" often has none) counts when its NAME mentions one."""
    named = incident.get("components") or []
    if named:
        return any(n in RELEVANT_COMPONENTS for n in named)
    title = incident.get("name") or ""
    return any(c in title for c in RELEVANT_COMPONENTS)


def _status_from(
    data: dict,
    fetched_at: float,
    now: float,
    stale: bool,
    error: str | None,
    history: dict | None = None,
) -> Status:
    comps = data.get("components") or {}
    bad = [
        {"name": name, "status": comps[name]}
        for name in RELEVANT_COMPONENTS
        if name in comps and comps[name] != "operational"
    ]
    incidents = [
        {k: i.get(k) for k in ("name", "status", "impact", "update")}
        for i in data.get("incidents") or []
        if isinstance(i, dict) and _touches_relevant(i)
    ]
    hist = history if isinstance(history, dict) else {}
    return Status(
        state="degraded" if (bad or incidents) else "ok",
        indicator=data.get("indicator"),
        description=data.get("description"),
        components=bad,
        incidents=incidents,
        fetched_at=fetched_at,
        age_s=max(0.0, now - fetched_at),
        stale=stale,
        error=error,
        since=hist.get("since"),
        gen=int(hist.get("gen") or 0),
        recovered=hist.get("recovered") if isinstance(hist.get("recovered"), dict) else None,
    )


def _load(path: pathlib.Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _good(doc: dict) -> dict | None:
    good = doc.get("good")
    if (
        isinstance(good, dict)
        and isinstance(good.get("fetched_at"), (int, float))
        and isinstance(good.get("data"), dict)
    ):
        return good
    return None


def _history(doc: dict) -> dict:
    hist = doc.get("history")
    return hist if isinstance(hist, dict) else {}


def _save(path: pathlib.Path, doc: dict) -> bool:
    """tmp + os.replace, so a concurrent reader sees the old file or the new one, never half of either. A write that fails is dropped (False): the next call fetches again, which is the cost of not caching, not an error."""
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        os.replace(tmp, path)
        tmp = None
    except OSError:
        return False
    finally:
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    return True


def advance_history(history: dict, data: dict, t: float) -> dict:
    """The cache's transition record after a successful fetch at `t`.

    `state` and `since` are the current ok/degraded state and when a fetch first saw it; `gen` counts the flips, so a once-only note can be keyed on it; `degraded` is the last degraded snapshot (what to name when it clears); `recovered` is set on a degraded -> ok flip and cleared when GitHub degrades again. The very first fetch sets a state without a flip, so a cold cache never announces a recovery it did not see.
    """
    st = _status_from(data, t, t, stale=False, error=None)
    hist = dict(history or {})
    prev = hist.get("state")
    if prev != st.state:
        hist["gen"] = int(hist.get("gen") or 0) + 1
        hist["since"] = t
        hist["state"] = st.state
        if prev == "degraded" and st.state == "ok":
            raw_snap = hist.get("degraded")
            snap = raw_snap if isinstance(raw_snap, dict) else {}
            hist["recovered"] = {
                "at": t,
                "gen": hist["gen"],
                "components": list(snap.get("components") or []),
                "incidents": _incident_outcomes(snap.get("incidents") or [], data),
            }
        elif st.state == "degraded":
            hist["recovered"] = None
    if st.state == "degraded":
        hist["degraded"] = {
            "components": [c["name"] for c in st.components],
            "incidents": [i["name"] for i in st.incidents],
        }
    return hist


def _incident_outcomes(names: list, data: dict) -> list[dict]:
    """Each incident named while degraded, with its status now: its current one while still unresolved, `resolved` once summary.json no longer lists it (the endpoint carries unresolved incidents only)."""
    current = {
        i.get("name"): i.get("status") for i in data.get("incidents") or [] if isinstance(i, dict)
    }
    return [{"name": n, "status": current.get(n) or "resolved"} for n in names]


def read(
    max_age_s: float = MAX_AGE_S,
    now: Callable[[], float] | None = None,
    fetch: Callable[[], bytes | str] | None = None,
    path: pathlib.Path | str | None = None,
    refresh: bool = False,
) -> Status:
    """The FOREGROUND read, for the CLI, the recovery waiter and the detached refresher only: it may fetch, for up to `FETCH_TIMEOUT_S`. Hooks and verdict printers call `read_cached`. Never raises."""
    try:
        return _read(max_age_s, now or time.time, fetch or fetch_summary, path, refresh)
    except Exception as exc:  # noqa: BLE001 -- a status note must never break its caller
        return Status(
            state="unknown",
            error="github_status internal error: %s: %s" % (type(exc).__name__, exc),
        )


def _negative_fresh(failed: dict | None, t: float) -> bool:
    return (
        failed is not None
        and isinstance(failed.get("at"), (int, float))
        and 0 <= t - failed["at"] < NEGATIVE_TTL_S
    )


def _read(max_age_s, now, fetch, path, refresh) -> Status:
    t = now()
    p = pathlib.Path(path) if path is not None else cache_path()
    doc = _load(p)
    good = _good(doc)
    hist = _history(doc)
    failed = doc.get("failed") if isinstance(doc.get("failed"), dict) else None

    if not refresh and good is not None and 0 <= t - good["fetched_at"] < max_age_s:
        return _status_from(good["data"], good["fetched_at"], t, False, None, hist)
    if not refresh and failed is not None and _negative_fresh(failed, t):
        return _fallback(good, hist, t, str(failed.get("error") or "fetch failed"))

    try:
        data = parse_summary(fetch())
    except Exception as exc:  # noqa: BLE001 -- every failure shape is the same answer: stale or unknown
        error = "%s: %s" % (type(exc).__name__, str(exc)[:200])
        new = {"failed": {"at": t, "error": error}, "history": hist}
        if good is not None:
            new["good"] = good
        _save(p, new)
        return _fallback(good, hist, t, error)
    hist = advance_history(hist, data, t)
    _save(p, {"good": {"fetched_at": t, "data": data}, "history": hist})
    return _status_from(data, t, t, False, None, hist)


def _fallback(good: dict | None, hist: dict, t: float, error: str) -> Status:
    if good is None:
        return Status(state="unknown", error=error)
    return _status_from(good["data"], good["fetched_at"], t, True, error, hist)


def _under_test() -> bool:
    """True inside a pytest run, subprocesses included (pytest exports `PYTEST_CURRENT_TEST` to the environment it runs a test in). The MACHINE cache is then not read: a suite's expected hook and verdict output must not depend on GitHub's weather, and a test must never start a detached network fetch. A suite that wants this module passes `path` explicitly, or patches this function."""
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _refresh_running(lock: pathlib.Path) -> bool:
    """True while a background refresh holds the lock. Asked of the kernel with a non-blocking flock, so a refresher killed by any signal frees it and can never wedge the next one."""
    try:
        fd = os.open(str(lock), os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True
    finally:
        os.close(fd)
    return False


def spawn_refresh(path: pathlib.Path) -> None:
    """Start ONE detached refresher of `path` and return at once: its own session, no inherited pipes, never waited on. Its exit status is nobody's business; what it leaves behind is the cache file."""
    subprocess.Popen(
        [sys.executable, str(pathlib.Path(__file__).resolve()), "--refresh-bg", str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def read_cached(
    max_age_s: float = MAX_AGE_S,
    now: Callable[[], float] | None = None,
    path: pathlib.Path | str | None = None,
    spawn: Callable[[pathlib.Path], None] | None = None,
) -> Status:
    """The HOOK-SIDE read: the cache only, never the network (operator ruling 2026-10-05, "it should not block us much").

    A hook runs on every tool call or stop, so a 5-second fetch inline would be a 5-second stall each time githubstatus.com is slow, and every session on the machine would pay it at once. Instead: a fresh cache is served as is; an old or missing one is served as it stands (stale, with its age) while ONE detached refresher is started, unless one is already running or the last fetch failed less than `NEGATIVE_TTL_S` ago. The next hook call sees the refreshed file. Never raises.
    """
    try:
        if path is None and _under_test():
            return Status(state="unknown", error="the machine cache is not read under pytest")
        t = (now or time.time)()
        p = pathlib.Path(path) if path is not None else cache_path()
        doc = _load(p)
        good = _good(doc)
        hist = _history(doc)
        failed = doc.get("failed") if isinstance(doc.get("failed"), dict) else None
        if good is not None and 0 <= t - good["fetched_at"] < max_age_s:
            return _status_from(good["data"], good["fetched_at"], t, False, None, hist)
        if failed is not None and _negative_fresh(failed, t):
            return _fallback(good, hist, t, str(failed.get("error") or "fetch failed"))
        if _refresh_running(p.parent / LOCK_NAME):
            note = "background refresh in flight"
        else:
            note = "background refresh started"
            with contextlib.suppress(Exception):
                (spawn or spawn_refresh)(p)
        if good is None:
            return Status(state="unknown", error="no cached status yet; " + note)
        return _status_from(
            good["data"],
            good["fetched_at"],
            t,
            True,
            "older than %ds; %s" % (max_age_s, note),
            hist,
        )
    except Exception as exc:  # noqa: BLE001 -- a status note must never break its caller
        return Status(
            state="unknown",
            error="github_status internal error: %s: %s" % (type(exc).__name__, exc),
        )


def refresh_background(
    path: pathlib.Path | str, fetch: Callable[[], bytes | str] | None = None
) -> int:
    """The detached refresher's body: take the lock without waiting (another refresher holding it means this one has nothing to do), then fetch unless the cache turned fresh meanwhile. Exit 0 always."""
    p = pathlib.Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(str(p.parent / LOCK_NAME), os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return 0
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return 0
        read(path=p, fetch=fetch)
    finally:
        os.close(fd)
    return 0


def _hhmm(t: float | None) -> str:
    if t is None:
        return "?"
    return datetime.datetime.fromtimestamp(t, datetime.UTC).strftime("%H:%MZ")


def _age_text(age_s: float | None) -> str:
    if age_s is None:
        return "?"
    mins = int(age_s // 60)
    if mins < 60:
        return "%dm" % mins
    return "%dh%02dm" % (mins // 60, mins % 60)


def line(st: Status) -> str:
    """The ONE line for a status that is not ok, or "" when it is. A degraded line ends with the command that wakes a session on recovery: a background task re-invokes the session only by exiting, and `--wait-recovery` exits exactly then."""
    if st.state == "ok":
        return ""
    if st.state == "unknown":
        return "GITHUB: status unknown -- githubstatus.com unreadable: %s" % (st.error or "?")
    parts = []
    if st.components:
        parts.append(", ".join("%s %s" % (c["name"], c["status"]) for c in st.components))
    incs = "; ".join(
        "%s: %s" % (i["name"], i["update"]) if i.get("update") else str(i["name"])
        for i in st.incidents
    )
    if incs:
        parts.append(incs)
    where = "githubstatus.com, %s old" % _age_text(st.age_s)
    if st.since is not None:
        where += ", degraded since %s" % _hhmm(st.since)
    if st.stale:
        where += ", STALE: %s" % (st.error or "?")
    return "GITHUB: %s (%s). To be woken when it clears, run in the background: %s" % (
        " -- ".join(parts),
        where,
        WAIT_CMD,
    )


def recovered_text(rec: dict) -> str:
    """`GITHUB RECOVERED: Actions operational again at 21:02Z; incident 'Incident with Actions' resolved`."""
    names = list(rec.get("components") or [])
    what = (
        "%s operational again" % ", ".join(names)
        if names
        else "every relevant component operational"
    )
    incs = "".join(
        "; incident '%s' %s" % (i.get("name"), i.get("status")) for i in rec.get("incidents") or []
    )
    return "GITHUB RECOVERED: %s at %s%s" % (what, _hhmm(rec.get("at")), incs)


def _seen_file(path: pathlib.Path, key: str | None) -> pathlib.Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key or "anon")[:64] or "anon"
    return path.parent / SEEN_DIR / safe


def _claim_recovery(path: pathlib.Path, key: str | None, gen: int) -> bool:
    """True exactly once per (reader key, recovery generation): the reader's marker holds the last generation it was shown, and a recovery is claimed by writing a higher one. One small file per key, so two sessions never race on a shared record. A marker that cannot be written claims nothing, which keeps the note once-only at the price of silence."""
    marker = _seen_file(path, key)
    try:
        seen = int(marker.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        seen = 0
    if seen >= gen:
        return False
    return _save_text(marker, str(gen))


def _save_text(path: pathlib.Path, text: str) -> bool:
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
        tmp = None
    except OSError:
        return False
    finally:
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    return True


def surface(
    session: str | None = None,
    now: Callable[[], float] | None = None,
    path: pathlib.Path | str | None = None,
    spawn: Callable[[pathlib.Path], None] | None = None,
    green: bool = False,
) -> str:
    """What an automatic surface prints, cache-only (`read_cached`): the degraded line, or a one-time `GITHUB RECOVERED` note, or "".

    THE DEGRADED LINE is suppressed when `green` (a green CI verdict needs no excuse). A bare `unknown` stays silent: a sandbox with no route to githubstatus.com would otherwise stamp a note on every verdict that says nothing about GitHub; `--line` still prints it for a reader who asked.

    THE RECOVERY NOTE is shown once per `session` key per recovery (`_claim_recovery`), and only within `RECOVERY_NOTE_MAX_AGE_S` of the flip, so a session started the next day is not told about yesterday. Never raises.
    """
    try:
        t = (now or time.time)()
        st = read_cached(now=lambda: t, path=path, spawn=spawn)
        if st.state == "degraded":
            return "" if green else line(st)
        rec = st.recovered
        if st.state != "ok" or not rec or not isinstance(rec.get("at"), (int, float)):
            return ""
        if not 0 <= t - rec["at"] < RECOVERY_NOTE_MAX_AGE_S:
            return ""
        p = pathlib.Path(path) if path is not None else cache_path()
        if _claim_recovery(p, session, int(rec.get("gen") or 0)):
            return recovered_text(rec)
    except Exception:  # noqa: BLE001 -- a status note must never break its caller
        return ""
    return ""


def surface_line(st: Status) -> str:
    """The degraded line alone, for a caller holding a Status (no recovery bookkeeping)."""
    return line(st) if st.state == "degraded" else ""


def wait_recovery(
    timeout_s: float,
    now: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    fetch: Callable[[], bytes | str] | None = None,
    path: pathlib.Path | str | None = None,
    out: Callable[[str], None] | None = None,
) -> int:
    """Block until every relevant component is operational, then print one line and exit 0; on timeout print the state and exit 2.

    MEANT FOR run_in_background: the harness re-invokes a session only when a background task exits, so this exits on recovery and nothing else. It reads the shared cache every `WAIT_POLL_S` and lets `read` refetch only once the cache is older than `WAIT_REFRESH_S` (150 s), so a machine full of waiters still asks githubstatus.com at most once per 2.5 minutes between them. A failed fetch is not recovery: an `unknown` keeps waiting.
    """
    now = now or time.time
    sleep = sleep or time.sleep
    out = out or print
    deadline = now() + timeout_s
    last_degraded = None
    st = read(max_age_s=WAIT_REFRESH_S, now=now, fetch=fetch, path=path)
    while True:
        if st.state == "degraded":
            last_degraded = st
        elif st.state == "ok":
            if last_degraded is None:
                out(
                    "GITHUB: operational, nothing to wait for (githubstatus.com, %s old)"
                    % _age_text(st.age_s)
                )
            else:
                out(
                    recovered_text(
                        {
                            "at": st.fetched_at,
                            "components": [c["name"] for c in last_degraded.components],
                            "incidents": _incident_outcomes(
                                [i["name"] for i in last_degraded.incidents],
                                {"incidents": st.incidents},
                            ),
                        }
                    )
                )
            return EXIT_OK
        remaining = deadline - now()
        if remaining <= 0:
            out(
                "GITHUB: not recovered after %dm -- %s"
                % (timeout_s // 60, line(st) or "status unknown")
            )
            return EXIT_WAIT_TIMEOUT
        sleep(min(WAIT_POLL_S, remaining))
        st = read(max_age_s=WAIT_REFRESH_S, now=now, fetch=fetch, path=path)


def transitions_text(samples: list[tuple[float, str, list[str]]]) -> str:
    """One line out of the (time, state, degraded component names) samples a long wait took, collapsing repeats and skipping `unknown`: `GitHub Actions: degraded 19:11Z -> operational 21:02Z during this wait`. "" when GitHub was never degraded during the wait."""
    runs: list[tuple[float, str]] = []
    names: list[str] = []
    for t, state, comps in samples:
        if state not in ("ok", "degraded"):
            continue
        for c in comps:
            if c not in names:
                names.append(c)
        if not runs or runs[-1][1] != state:
            runs.append((t, state))
    if not any(state == "degraded" for _, state in runs):
        return ""
    label = "GitHub %s" % ", ".join(names) if names else "GitHub"
    seq = " -> ".join(
        "%s %s" % ("operational" if state == "ok" else "degraded", _hhmm(t)) for t, state in runs
    )
    if len(runs) == 1:
        return "%s: degraded throughout this wait (seen %s)" % (label, _hhmm(runs[0][0]))
    return "%s: %s during this wait" % (label, seq)


def exit_code(st: Status) -> int:
    return {"ok": EXIT_OK, "degraded": EXIT_DEGRADED}.get(st.state, EXIT_UNKNOWN)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python3 -m rediacc_ci.ci.github_status",
        description="GitHub service status for the components this repo depends on (cached 15 min per machine).",
        epilog="Exit 0 ok, 1 degraded, 3 unknown. --wait-recovery: 0 recovered, 2 timed out.",
    )
    ap.add_argument("--json", action="store_true", help="print the whole status as JSON")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache and fetch now")
    ap.add_argument("--line", action="store_true", help="one line when not ok, nothing when ok")
    ap.add_argument(
        "--wait-recovery",
        action="store_true",
        help="block until every relevant component is operational (for run_in_background)",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=WAIT_DEFAULT_MIN,
        metavar="MIN",
        help="--wait-recovery only: give up after MIN minutes (default %d)" % WAIT_DEFAULT_MIN,
    )
    ap.add_argument("--refresh-bg", metavar="CACHE", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.refresh_bg:
        return refresh_background(args.refresh_bg)
    if args.wait_recovery:
        return wait_recovery(args.timeout * 60)
    st = read(refresh=args.refresh)
    if args.json:
        print(json.dumps(st.to_dict(), indent=2, sort_keys=True))
    elif args.line:
        text = line(st)
        if text:
            print(text)
    else:
        print(
            line(st)
            or "GITHUB: operational (%s; githubstatus.com, %s old)"
            % (", ".join(RELEVANT_COMPONENTS), _age_text(st.age_s))
        )
    return exit_code(st)


if __name__ == "__main__":
    sys.exit(main())
