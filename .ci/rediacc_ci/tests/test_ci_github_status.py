"""`rediacc_ci.ci.github_status` and its four surfaces, driven with a fake fetch and a fake clock.

CONTROL FIRST. Every cache rule is pinned by a pair: the case where the rule must act and the neighbouring case where it must not, so a rule that stopped acting (a TTL ignored, a negative cache never consulted, a recovery note never claimed) fails a named test rather than passing silently. The time budget has its own control: the same measurement over a read that DOES fetch inline must exceed the budget, so the 200 ms assertion is not one that cannot fail.

NO NETWORK. `fetch_summary` is replaced in every test that could reach it, and the machine cache is never touched: each test points `cache_path` at its own temp directory. Under pytest the module also refuses to read the machine cache on its own (`_under_test`), which is what keeps every OTHER suite's hook and verdict output independent of GitHub's weather; the tests here switch that off explicitly.
"""

from __future__ import annotations

import importlib.util
import io
import json
import time
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.ci import github_status as gs

if TYPE_CHECKING:
    import pathlib

T0 = 1_791_232_400.0  # 2026-10-05T20:33:20Z


def summary(actions="operational", incidents=(), copilot="operational", indicator="none"):
    return json.dumps(
        {
            "page": {"id": "kctbh9vrtdwd", "name": "GitHub"},
            "status": {"indicator": indicator, "description": "x"},
            "components": [
                {"name": "Git Operations", "status": "operational"},
                {"name": "API Requests", "status": "operational"},
                {"name": "Actions", "status": actions},
                {"name": "Copilot", "status": copilot},
                {"name": "Pages", "status": "operational"},
            ],
            "incidents": list(incidents),
        }
    )


ACTIONS_INCIDENT = {
    "name": "Incident with Actions",
    "status": "investigating",
    "impact": "minor",
    "components": [{"name": "Actions"}],
    "incident_updates": [
        {
            "body": "We are investigating delays in assigning GitHub-hosted runners. More soon.",
        }
    ],
}
DEGRADED = summary("degraded_performance", [ACTIONS_INCIDENT], indicator="minor")
OK = summary()
COPILOT_ONLY = summary(
    copilot="major_outage",
    incidents=[
        {
            "name": "Copilot is down",
            "status": "investigating",
            "impact": "major",
            "components": [{"name": "Copilot"}],
            "incident_updates": [{"body": "x."}],
        }
    ],
    indicator="major",
)
MALFORMED = "<html>captive portal</html>"


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


class Fetch:
    """Answers from a list of bodies (an Exception instance is raised), counting calls."""

    def __init__(self, *bodies):
        self.bodies = list(bodies)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        body = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(body, Exception):
            raise body
        return body


@pytest.fixture
def cache(tmp_path, monkeypatch) -> pathlib.Path:
    path = tmp_path / "lease" / gs.CACHE_NAME
    monkeypatch.setattr(gs, "cache_path", lambda: path)
    monkeypatch.setattr(gs, "_under_test", lambda: False)

    def no_network():
        msg = "a test reached the real fetch"
        raise AssertionError(msg)

    monkeypatch.setattr(gs, "fetch_summary", no_network)
    # A detached refresher started from a test would be a real network call outliving it.
    monkeypatch.setattr(gs, "spawn_refresh", lambda _p: None)
    return path


# ---------------------------------------------------------------------------- the foreground read


def test_fresh_cache_is_served_without_a_fetch(cache):
    clock, fetch = Clock(), Fetch(DEGRADED)
    first = gs.read(now=clock, fetch=fetch, path=cache)
    clock.t += gs.MAX_AGE_S - 1
    second = gs.read(now=clock, fetch=fetch, path=cache)
    assert fetch.calls == 1, "a cache younger than the TTL was refetched"
    assert first.state == second.state == "degraded"
    assert second.age_s == gs.MAX_AGE_S - 1
    assert not second.stale


def test_control_expired_cache_is_refetched(cache):
    clock, fetch = Clock(), Fetch(DEGRADED, OK)
    gs.read(now=clock, fetch=fetch, path=cache)
    clock.t += gs.MAX_AGE_S
    st = gs.read(now=clock, fetch=fetch, path=cache)
    assert fetch.calls == 2
    assert st.state == "ok"


def test_fetch_failure_serves_the_stale_value_with_its_error(cache):
    clock, fetch = Clock(), Fetch(DEGRADED, OSError("network is unreachable"))
    gs.read(now=clock, fetch=fetch, path=cache)
    clock.t += gs.MAX_AGE_S + 120
    st = gs.read(now=clock, fetch=fetch, path=cache)
    assert st.state == "degraded"
    assert st.stale
    assert "network is unreachable" in (st.error or "")
    assert st.age_s == gs.MAX_AGE_S + 120


def test_no_cache_and_a_failure_is_unknown(cache):
    st = gs.read(now=Clock(), fetch=Fetch(OSError("boom")), path=cache)
    assert st.state == "unknown"
    assert "boom" in (st.error or "")


def test_malformed_body_is_a_failure_not_ok(cache):
    st = gs.read(now=Clock(), fetch=Fetch(MALFORMED), path=cache)
    assert st.state == "unknown"
    st = gs.read(now=Clock(), fetch=Fetch(json.dumps({"status": {}})), path=cache, refresh=True)
    assert st.state == "unknown"


def test_negative_cache_suppresses_a_refetch_within_60s(cache):
    clock, fetch = Clock(), Fetch(OSError("down"), OK)
    gs.read(now=clock, fetch=fetch, path=cache)
    clock.t += gs.NEGATIVE_TTL_S - 1
    st = gs.read(now=clock, fetch=fetch, path=cache)
    assert fetch.calls == 1, "a failure less than 60 s old was retried"
    assert st.state == "unknown"
    # CONTROL: past the window the next read asks again.
    clock.t += 2
    st = gs.read(now=clock, fetch=fetch, path=cache)
    assert fetch.calls == 2
    assert st.state == "ok"


def test_corrupt_cache_is_ignored(cache):
    cache.parent.mkdir(parents=True)
    cache.write_text("{not json", encoding="utf-8")
    fetch = Fetch(OK)
    st = gs.read(now=Clock(), fetch=fetch, path=cache)
    assert fetch.calls == 1
    assert st.state == "ok"
    assert json.loads(cache.read_text(encoding="utf-8"))["good"]["data"]["indicator"] == "none"


def test_irrelevant_component_degraded_reads_ok(cache):
    st = gs.read(now=Clock(), fetch=Fetch(COPILOT_ONLY), path=cache)
    assert st.indicator == "major"
    assert st.state == "ok", "a Copilot outage is not a reason to doubt a CI verdict"
    assert gs.line(st) == ""


def test_line_output_is_exact(cache):
    clock = Clock()
    gs.read(now=clock, fetch=Fetch(DEGRADED), path=cache)
    clock.t += 180
    st = gs.read(now=clock, fetch=Fetch(DEGRADED), path=cache)
    assert gs.line(st) == (
        "GITHUB: Actions degraded_performance -- Incident with Actions: We are investigating "
        "delays in assigning GitHub-hosted runners. (githubstatus.com, 3m old, degraded since "
        "20:33Z). To be woken when it clears, run in the background: "
        "PYTHONPATH=.ci python3 -m rediacc_ci.ci.github_status --wait-recovery"
    )


def test_cli_line_and_exit_codes(cache, monkeypatch, capsys):
    monkeypatch.setattr(gs, "fetch_summary", Fetch(DEGRADED))
    assert gs.main(["--line"]) == gs.EXIT_DEGRADED
    assert capsys.readouterr().out.startswith("GITHUB: Actions degraded_performance -- ")
    monkeypatch.setattr(gs, "fetch_summary", Fetch(OK))
    assert gs.main(["--line", "--refresh"]) == gs.EXIT_OK
    assert capsys.readouterr().out == ""
    cache.unlink()
    monkeypatch.setattr(gs, "fetch_summary", Fetch(OSError("x")))
    assert gs.main(["--line"]) == gs.EXIT_UNKNOWN
    assert capsys.readouterr().out.startswith("GITHUB: status unknown")


# ---------------------------------------------------------------------------- the hook-side read


def test_read_cached_never_fetches_and_spawns_one_refresh_when_old(cache):
    clock = Clock()
    gs.read(now=clock, fetch=Fetch(DEGRADED), path=cache)
    spawned = []
    st = gs.read_cached(now=clock, path=cache, spawn=spawned.append)
    assert st.state == "degraded"
    assert spawned == [], "a fresh cache started a refresh"
    clock.t += gs.MAX_AGE_S + 60
    st = gs.read_cached(now=clock, path=cache, spawn=spawned.append)
    assert spawned == [cache]
    assert st.stale
    assert st.state == "degraded"


def test_read_cached_skips_the_spawn_while_a_refresh_holds_the_lock(cache):
    import fcntl  # noqa: PLC0415

    cache.parent.mkdir(parents=True)
    lock = cache.parent / gs.LOCK_NAME
    with lock.open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        spawned = []
        st = gs.read_cached(now=Clock(), path=cache, spawn=spawned.append)
    assert spawned == []
    assert st.state == "unknown"
    assert "in flight" in (st.error or "")
    # CONTROL: the lock released, the same read spawns.
    gs.read_cached(now=Clock(), path=cache, spawn=spawned.append)
    assert spawned == [cache]


def test_read_cached_honours_the_negative_cache(cache):
    clock = Clock()
    gs.read(now=clock, fetch=Fetch(OSError("down")), path=cache)
    spawned = []
    gs.read_cached(now=clock, path=cache, spawn=spawned.append)
    assert spawned == []


def test_refresh_background_fetches_once_under_the_lock(cache):
    fetch = Fetch(DEGRADED)
    assert gs.refresh_background(cache, fetch=fetch) == 0
    assert fetch.calls == 1
    assert gs.read_cached(path=cache, spawn=lambda _p: None).state == "degraded"


def test_under_pytest_the_machine_cache_is_not_read(monkeypatch):
    def boom():
        msg = "the machine cache path was resolved under pytest"
        raise AssertionError(msg)

    monkeypatch.setattr(gs, "cache_path", boom)
    st = gs.read_cached(spawn=lambda _p: pytest.fail("spawned under pytest"))
    assert st.state == "unknown"
    assert gs.surface() == ""


# ---------------------------------------------------------------------------- the four surfaces, timed


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def note_hook():
    return _load(
        "github_status_note_under_test",
        paths.from_root(".claude", "hooks", "post-bash", "github_status_note.py"),
    )


@pytest.fixture
def trace():
    return _load(
        "ci_trace_github_under_test", paths.from_root(".ci", "scripts", "ci", "ci-trace.py")
    )


@pytest.fixture
def wl_checks():
    paths.on_sys_path(paths.from_root(".claude"))
    paths.on_sys_path(paths.from_root(".claude", "hooks", "stop"))
    import wl_checks  # noqa: PLC0415

    return wl_checks


def _post(cmd, session="sess-a"):
    return json.dumps({"session_id": session, "tool_name": "Bash", "tool_input": {"command": cmd}})


def _run_hook(note_hook, argv, payload):
    out = io.StringIO()
    rc = note_hook.main(argv, io.StringIO(payload), out)
    return rc, out.getvalue()


SLOW_S = 30


def _surfaces(note_hook, trace, wl_checks):
    return {
        "post-bash": lambda: _run_hook(note_hook, [], _post("git push origin b")),
        "session-start": lambda: _run_hook(note_hook, ["--session-start"], _post("")),
        "stop-advisory": lambda: wl_checks.github_status_line("sess-a"),
        "ci-trace": trace._github_note,
    }


def _elapsed(fn):
    t = time.monotonic()
    fn()
    return time.monotonic() - t


@pytest.mark.parametrize("state", ["empty", "stale"])
def test_every_hook_surface_returns_in_under_200ms_with_a_30s_fetch(
    cache, monkeypatch, note_hook, trace, wl_checks, state
):
    """The operator's must-not-block ruling: no surface ever calls the fetch inline. Both shapes that WANT a refresh are driven (no cache at all, a cache past its TTL); the refresh is the detached spawn, recorded here instead of started."""
    if state == "stale":
        gs.read(now=Clock(time.time() - gs.MAX_AGE_S - 60), fetch=Fetch(DEGRADED), path=cache)

    def slow():
        time.sleep(SLOW_S)
        return OK

    spawned = []
    monkeypatch.setattr(gs, "fetch_summary", slow)
    monkeypatch.setattr(gs, "spawn_refresh", spawned.append)
    for name, fn in _surfaces(note_hook, trace, wl_checks).items():
        took = _elapsed(fn)
        assert took < 0.2, "%s took %.3fs with a %ds fetch: it fetched inline" % (
            name,
            took,
            SLOW_S,
        )
    assert spawned, "nothing started the background refresh"


def test_control_the_time_budget_catches_an_inline_fetch(cache, monkeypatch, note_hook):
    """The 200 ms assertion above can fail: a read_cached planted to fetch inline is measured over it."""

    def slow():
        time.sleep(0.5)
        return OK

    monkeypatch.setattr(gs, "fetch_summary", slow)
    monkeypatch.setattr(gs, "read_cached", lambda **_kw: gs.read(path=cache))
    took = _elapsed(lambda: _run_hook(note_hook, [], _post("git push origin b")))
    assert took >= 0.2


def test_post_bash_note_on_a_ci_command_while_degraded(cache, note_hook):
    gs.read(fetch=Fetch(DEGRADED), path=cache)
    rc, out = _run_hook(note_hook, [], _post("python3 .ci/scripts/ci/ci-trace.py --wait"))
    assert rc == 0
    doc = json.loads(out)
    assert doc["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert doc["hookSpecificOutput"]["additionalContext"].startswith("GITHUB: Actions degraded")


@pytest.mark.parametrize(
    "cmd",
    [
        "git push origin b",
        "git -C /x push -q origin b",
        "cd /x && git push",
        "gh run list",
        "gh pr view 5",
        "gh workflow run ci.yml",
        "gh api repos/a/b/actions/runs",
        "python3 .ci/scripts/ci/ci-trace.py --wait",
        ".ci/scripts/ci/ci-trace.py",
        "FOO=1 python3 .ci/scripts/ci/ci-trace.py --why",
        "python3 .claude/hooks/stop/wl_prreview.py --wait",
        "echo x; python3 .ci/scripts/ci/ci-trace.py",
    ],
)
def test_post_bash_ci_invocations_fire(cmd, note_hook):
    assert note_hook.is_ci_command(cmd)


@pytest.mark.parametrize(
    "cmd",
    [
        "ls .ci/scripts/ci/ci-trace.py",
        "grep ci-trace.py x",
        "ls -l .claude/hooks/post-bash/github_status_note.py .ci/scripts/ci/ci-trace.py",
        'git commit -m "then git push"',
        "cat <<EOF\ngit push\nEOF",
        "git log --oneline",
        "ghx run",
        "",
    ],
)
def test_control_post_bash_a_mention_is_not_an_invocation(cmd, note_hook):
    assert not note_hook.is_ci_command(cmd)


def test_control_post_bash_is_silent_on_a_non_ci_command_or_when_ok(cache, note_hook):
    gs.read(fetch=Fetch(DEGRADED), path=cache)
    assert _run_hook(note_hook, [], _post("ls -la")) == (0, "")
    cache.unlink()
    gs.read(fetch=Fetch(OK), path=cache)
    assert _run_hook(note_hook, [], _post("git push origin b")) == (0, "")


@pytest.mark.usefixtures("cache")
def test_post_bash_never_fails_the_chain(note_hook, monkeypatch):
    monkeypatch.setattr(gs, "surface", lambda **_kw: 1 / 0)
    assert _run_hook(note_hook, [], _post("git push")) == (0, "")
    assert _run_hook(note_hook, [], "not json") == (0, "")


def test_session_start_note(cache, note_hook):
    gs.read(fetch=Fetch(DEGRADED), path=cache)
    rc, out = _run_hook(note_hook, ["--session-start"], _post(""))
    assert rc == 0
    assert json.loads(out)["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_ci_trace_note_is_suppressed_on_green(cache, trace):
    gs.read(fetch=Fetch(DEGRADED), path=cache)
    assert trace._github_note().startswith("GITHUB: Actions degraded")
    assert trace._github_note(green=True) == ""


# ---------------------------------------------------------------------------- recovery


def test_recovery_note_appears_exactly_once_per_session(cache):
    clock = Clock()
    gs.read(now=clock, fetch=Fetch(DEGRADED), path=cache)
    assert gs.surface("a", now=clock, path=cache).startswith("GITHUB: Actions degraded")
    clock.t += gs.MAX_AGE_S
    gs.read(now=clock, fetch=Fetch(OK), path=cache)
    first = gs.surface("a", now=clock, path=cache)
    assert first == (
        "GITHUB RECOVERED: Actions operational again at 20:48Z; "
        "incident 'Incident with Actions' resolved"
    )
    assert gs.surface("a", now=clock, path=cache) == "", "the recovery note repeated"
    assert gs.surface("b", now=clock, path=cache) == first, "another session never heard"
    assert gs.surface("b", now=clock, path=cache) == ""


def test_control_a_cold_cache_announces_no_recovery(cache):
    clock = Clock()
    gs.read(now=clock, fetch=Fetch(OK), path=cache)
    assert gs.surface("a", now=clock, path=cache) == ""


def test_a_recovery_note_expires(cache):
    clock = Clock()
    gs.read(now=clock, fetch=Fetch(DEGRADED), path=cache)
    clock.t += gs.MAX_AGE_S
    gs.read(now=clock, fetch=Fetch(OK), path=cache)
    clock.t += gs.RECOVERY_NOTE_MAX_AGE_S + 1
    assert gs.surface("late", now=lambda: clock.t, path=cache) == ""


def test_degrading_again_clears_the_recovery(cache):
    clock = Clock()
    for body in (DEGRADED, OK, DEGRADED):
        gs.read(now=clock, fetch=Fetch(body), path=cache, refresh=True)
        clock.t += 1
    assert gs.surface("a", now=clock, path=cache).startswith("GITHUB: Actions degraded")


def test_stop_advisory_hands_over_to_the_recovery_note(cache, wl_checks):
    gs.read(fetch=Fetch(DEGRADED), path=cache)
    assert wl_checks.github_status_line("s1").startswith("GITHUB: Actions degraded")
    gs.read(fetch=Fetch(OK), path=cache, refresh=True)
    assert wl_checks.github_status_line("s1").startswith("GITHUB RECOVERED")
    assert wl_checks.github_status_line("s1") == ""


def test_wait_recovery_exits_0_on_recovery(cache):
    clock = Clock()
    fetch = Fetch(DEGRADED, DEGRADED, OK)
    lines = []

    def sleep(s):
        clock.t += s

    rc = gs.wait_recovery(3600, now=clock, sleep=sleep, fetch=fetch, path=cache, out=lines.append)
    assert rc == gs.EXIT_OK
    assert lines == [
        (
            "GITHUB RECOVERED: Actions operational again at 20:38Z; "
            "incident 'Incident with Actions' resolved"
        )
    ]
    # Refetches are spaced by the 150 s floor, never by the 30 s poll.
    assert fetch.calls == 3
    assert clock.t - T0 == 2 * gs.WAIT_REFRESH_S


def test_control_wait_recovery_times_out_with_exit_2(cache):
    clock = Clock()
    lines = []

    def sleep(s):
        clock.t += s

    rc = gs.wait_recovery(
        600, now=clock, sleep=sleep, fetch=Fetch(DEGRADED), path=cache, out=lines.append
    )
    assert rc == gs.EXIT_WAIT_TIMEOUT
    assert lines[0].startswith("GITHUB: not recovered after 10m -- GITHUB: Actions degraded")


def test_ci_trace_wait_names_the_transition_in_its_verdict(cache, trace, monkeypatch, capsys):
    """A --wait that lived through degraded -> ok says so beside its final verdict; the wait itself still ends on the CI verdict."""
    clock = Clock()
    gs.read(now=clock, fetch=Fetch(DEGRADED), path=cache)
    bodies = iter([None, OK])
    snaps = iter(
        [
            {"verdict": "running", "head": "a" * 40, "ref": "b", "source": "branch", "waiting": 3},
            {"verdict": "green", "head": "a" * 40, "ref": "b", "source": "branch"},
        ]
    )

    def snapshot(*_a, **_kw):
        body = next(bodies)
        if body:
            clock.t += gs.MAX_AGE_S
            gs.read(now=clock, fetch=Fetch(body), path=cache)
        return next(snaps), None

    monkeypatch.setattr(trace, "_snapshot", snapshot)
    monkeypatch.setattr(trace, "_attach_signals", lambda *_a: None)
    monkeypatch.setattr(trace, "_show_signals", lambda *_a: None)
    monkeypatch.setattr(trace, "_record_final", lambda *_a, **_kw: None)
    monkeypatch.setattr(trace, "_signals_tick", lambda *_a: None)
    monkeypatch.setattr(trace, "POLL_SECONDS", 0)
    monkeypatch.setattr(gs, "time", type("T", (), {"time": staticmethod(clock)}))
    rc = trace.main(["--wait", "--ref", "b"])
    out = capsys.readouterr().out
    assert rc == trace.EXIT_GREEN
    assert "GITHUB: Actions degraded_performance" in out
    assert "GitHub Actions: degraded 20:33Z -> operational 20:48Z during this wait" in out


def test_the_hook_runs_as_a_real_process_loading_the_module_by_file(tmp_path):
    """The hook process has no `.ci` on sys.path, so it loads github_status BY FILE; a dataclass module loaded that way must be registered in sys.modules before it runs, which no in-process test (where the module is importable by name) can see. Driven as the harness runs it, outside pytest's environment marker, over a fresh cache in a temp lease directory, so no refresh is spawned and nothing touches the network."""
    import os  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    lease = tmp_path / "lease"
    gs.read(fetch=Fetch(DEGRADED), path=lease / gs.CACHE_NAME)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTEST_CURRENT_TEST", "PYTHONPATH")}
    env["REDIACC_CORE_LEASE_DIR"] = str(lease)
    hook = paths.from_root(".claude", "hooks", "post-bash", "github_status_note.py")
    done = subprocess.run(
        [sys.executable, str(hook)],
        input=_post("gh run list"),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"].startswith(
        "GITHUB: Actions degraded"
    )
