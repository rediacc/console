"""`rediacc_ci.core_lease`: the machine-wide core lease, driven through its real CLI over a 4-token pool in a temp directory.

WHAT IS AT RISK. A lease that only looks like one: a pool that never refills after a holder is killed (sidecar files counted instead of locks held), or an acquirer that parks in the kernel on one held token while others are free (a flock without LOCK_NB). Both read as "the lease works" in any test that only takes and releases politely, so each scenario below is ALSO run against a copy of the module with that defect planted (`core_lease.DEFECTS`), and the scenario must go red there. A plant that does not apply is itself a failure, so a reworded line cannot void its control.

Every process is started with the pool pointed at the temp directory and with `CI_CORE_LEASE_HELD` / `CI_RUNNER_CORES` removed, so neither the real pool nor an enclosing grant leaks in.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import selectors
import signal
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import core_lease

if TYPE_CHECKING:
    from collections.abc import Callable

MODULE = pathlib.Path(core_lease.__file__).resolve()
TOKENS = 4
# How long a step that should answer may take, and how long a step that should NOT answer is watched before it counts as blocked.
ANSWER_S = 10.0
BLOCKED_S = 1.5


class Lease:
    """A pool directory plus the module file to drive (the real one, or a planted copy)."""

    def __init__(self, module: pathlib.Path, pool: pathlib.Path) -> None:
        self.module = module
        self.pool = pool
        self.procs: list[subprocess.Popen[str]] = []

    def env(self) -> dict[str, str]:
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in {core_lease.HELD_ENV, core_lease.ENV, "PYTEST_ADDOPTS"}
        }
        env[core_lease.DIR_ENV] = str(self.pool)
        env[core_lease.TOKENS_ENV] = str(TOKENS)
        return env

    def spawn(self, *args: str) -> subprocess.Popen[str]:
        proc = subprocess.Popen(
            [sys.executable, str(self.module), *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env(),
        )
        self.procs.append(proc)
        return proc

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.module), *args],
            capture_output=True,
            text=True,
            env=self.env(),
            timeout=ANSWER_S,
            check=False,
        )

    def free(self) -> int:
        out = self.run("free")
        assert out.returncode == 0, out.stderr
        return int(out.stdout.strip())

    def close(self) -> None:
        for proc in self.procs:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=ANSWER_S)
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()


def readline(proc: subprocess.Popen[str], timeout: float) -> str | None:
    """One stdout line, or None when none arrives within `timeout` seconds."""
    assert proc.stdout is not None
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)
    try:
        if not sel.select(timeout):
            return None
    finally:
        sel.close()
    return proc.stdout.readline().strip()


def kill9(proc: subprocess.Popen[str]) -> None:
    os.kill(proc.pid, signal.SIGKILL)
    proc.wait(timeout=ANSWER_S)


# --------------------------------------------------------------------------- scenarios
# Each returns a list of failure strings; an empty list is green. Kept as plain functions so the same scenario runs against the real module and against each planted copy.


def scenario_over_grant(lease: Lease) -> list[str]:
    """Two `acquire --max 3` over 4 tokens get 3 and then 1."""
    fails = []
    first = lease.spawn("acquire", "--max", "3", "--label", "first")
    got1 = readline(first, ANSWER_S)
    if got1 != "3":
        fails.append("first acquire --max 3 printed %r, want '3'" % got1)
    second = lease.spawn("acquire", "--max", "3", "--label", "second")
    got2 = readline(second, ANSWER_S)
    if got2 != "1":
        fails.append("second acquire --max 3 printed %r, want '1' (None = it hung)" % got2)
    return fails


def scenario_kill_frees(lease: Lease) -> list[str]:
    """With the pool full, `--min 1 --wait` blocks; kill -9 of the 3-token holder frees them, and the waiter gets all 3."""
    first = lease.spawn("acquire", "--max", "3")
    if readline(first, ANSWER_S) != "3":
        return ["setup: the first holder did not get 3"]
    second = lease.spawn("acquire", "--max", "3")
    if readline(second, ANSWER_S) != "1":
        return ["setup: the second holder did not get the last 1"]
    waiter = lease.spawn("acquire", "--min", "1", "--wait")
    early = readline(waiter, BLOCKED_S)
    if early is not None:
        return ["the waiter answered %r with every token held; it must block" % early]
    # The waiter is stopped across the kill: the kernel frees a dying holder's tokens one descriptor at a time, and a waiter polling mid-teardown legitimately sees a part of them (scenario_partial_release covers that). Stopped, its first look is after the holder is fully reaped, so the answer is 3 however loaded the machine is.
    os.kill(waiter.pid, signal.SIGSTOP)
    try:
        kill9(first)
    finally:
        os.kill(waiter.pid, signal.SIGCONT)
    got = readline(waiter, ANSWER_S)
    if got != "3":
        return ["after kill -9 of the 3-token holder the waiter printed %r, want '3'" % got]
    return []


PARTIAL_POLL_S = 0.002
PARTIAL_GAP_S = 0.015


def scenario_partial_release(lease: Lease) -> list[str]:
    """A waiter that wakes while a holder's 3 tokens are freed one at a time, polling much faster than they are freed, still ends with all 3."""
    mod = load_module(lease.module)
    mod.WAIT_POLL_SECONDS = PARTIAL_POLL_S  # type: ignore[attr-defined]
    pool = mod.Pool(lease.pool, TOKENS)  # type: ignore[attr-defined]
    pool.ensure()
    holder = pool.try_acquire(3, 3)
    other = pool.try_acquire(1, 1)
    if len(holder) != 3 or len(other) != 1:
        return ["setup: holder got %d and other %d, want 3 and 1" % (len(holder), len(other))]
    waiting = threading.Event()
    got: list[object] = []

    def wait_for_tokens() -> None:
        got.extend(pool.acquire(1, 3, wait=True, timeout=ANSWER_S, on_wait=waiting.set))

    def free_one_by_one() -> None:
        for token in holder:
            time.sleep(PARTIAL_GAP_S)
            pool.release([token])

    waiter = threading.Thread(target=wait_for_tokens)
    waiter.start()
    if not waiting.wait(ANSWER_S):
        return ["the waiter never started waiting"]
    freer = threading.Thread(target=free_one_by_one)
    freer.start()
    freer.join(ANSWER_S)
    waiter.join(ANSWER_S * 2)
    pool.release([*got, *other])  # type: ignore[arg-type]
    if len(got) != 3:
        return ["a waiter woken by tokens freed one by one took %d, want 3" % len(got)]
    return []


def scenario_partial_release_silent(lease: Lease) -> list[str]:
    """The same partial release with a waiter that passes no on_wait callback: it blocks just the same, so it must settle just the same (review finding e2a16724.1)."""
    mod = load_module(lease.module)
    mod.WAIT_POLL_SECONDS = PARTIAL_POLL_S  # type: ignore[attr-defined]
    pool = mod.Pool(lease.pool, TOKENS)  # type: ignore[attr-defined]
    pool.ensure()
    holder = pool.try_acquire(3, 3)
    other = pool.try_acquire(1, 1)
    if len(holder) != 3 or len(other) != 1:
        return ["setup: holder got %d and other %d, want 3 and 1" % (len(holder), len(other))]
    got: list[object] = []
    waiter = threading.Thread(
        target=lambda: got.extend(pool.acquire(1, 3, wait=True, timeout=ANSWER_S))
    )
    waiter.start()
    time.sleep(PARTIAL_GAP_S * 3)
    for token in holder:
        time.sleep(PARTIAL_GAP_S)
        pool.release([token])
    waiter.join(ANSWER_S * 2)
    pool.release([*got, *other])  # type: ignore[arg-type]
    if len(got) != 3:
        return [
            "a waiter with no on_wait, woken by tokens freed one by one, took %d, want 3" % len(got)
        ]
    return []


def scenario_short_without_wait(lease: Lease) -> list[str]:
    """Fewer than --min free and no --wait: prints 0, exit 75, keeps nothing."""
    holder = lease.spawn("acquire", "--max", "3")
    if readline(holder, ANSWER_S) != "3":
        return ["setup: the holder did not get 3"]
    out = lease.run("acquire", "--min", "2", "--max", "2")
    fails = []
    if (out.returncode, out.stdout.strip()) != (core_lease.EXIT_SHORT, "0"):
        fails.append("short acquire gave rc=%d stdout=%r" % (out.returncode, out.stdout))
    if lease.free() != 1:
        fails.append("a refused short grant must keep nothing; free=%d" % lease.free())
    return fails


def scenario_broker_eof(lease: Lease) -> list[str]:
    """A broker grants, releases by id, and frees everything when its stdin closes."""
    broker = lease.spawn("broker", "--label", "test-runner")
    assert broker.stdin is not None

    def ask(req: dict[str, object]) -> dict[str, object] | None:
        assert broker.stdin is not None
        broker.stdin.write(json.dumps(req) + "\n")
        broker.stdin.flush()
        line = readline(broker, ANSWER_S)
        return None if line is None else json.loads(line)

    fails = []
    a = ask({"op": "acquire", "min": 1, "max": 3, "label": "gate-a"})
    if not a or a.get("k") != 3:
        fails.append("broker acquire max 3 answered %r" % a)
    b = ask({"op": "acquire", "min": 2, "max": "all", "label": "gate-b"})
    if b != {"k": 0, "ids": []}:
        fails.append("broker acquire min 2 with 1 free must grant nothing, answered %r" % b)
    f = ask({"op": "free"})
    if not f or (f.get("free"), f.get("total")) != (1, TOKENS):
        fails.append("broker free answered %r, want free 1 of %d" % (f, TOKENS))
    ids = a.get("ids") if a else None
    if isinstance(ids, list) and ids:
        r = ask({"op": "release", "ids": [ids[0], 99]})
        if r != {"released": [ids[0]], "unknown": [99]}:
            fails.append("broker release answered %r" % r)
    if lease.free() != 2:
        fails.append("with the broker holding 2, free must be 2; got %d" % lease.free())
    broker.stdin.close()
    try:
        rc = broker.wait(timeout=ANSWER_S)
    except subprocess.TimeoutExpired:
        return [*fails, "the broker did not exit on stdin EOF"]
    if rc != 0:
        fails.append("the broker exited %d on EOF, want 0" % rc)
    if lease.free() != TOKENS:
        fails.append("after the broker's EOF every token must be free; got %d" % lease.free())
    return fails


# Four processes running `free_count` in a tight loop beside an acquirer. Measured 2026-10-05 over 16 tokens: with the pool mutex removed, 233 of 1,444 whole-pool acquires came back short in 3 s; with it, 0 of 175.
PROBER = """
import importlib.util, pathlib, sys, time
spec = importlib.util.spec_from_file_location("probed", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
sys.modules["probed"] = mod
spec.loader.exec_module(mod)
pool = mod.Pool(pathlib.Path(sys.argv[2]), int(sys.argv[3]))
end = time.monotonic() + float(sys.argv[4])
while time.monotonic() < end:
    pool.free_count()
"""
RACE_TOKENS = 16
RACE_PROBERS = 4
RACE_S = 2.0


def load_module(path: pathlib.Path) -> object:
    name = "core_lease_under_test_%d" % abs(hash(str(path)))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def scenario_probe_race(lease: Lease) -> list[str]:
    """`free` probes running beside an acquirer never make it come back short: every whole-pool acquire over a free pool gets the whole pool."""
    mod = load_module(lease.module)
    pool = mod.Pool(lease.pool, RACE_TOKENS)  # type: ignore[attr-defined]
    pool.ensure()
    race_args = [str(RACE_TOKENS), str(RACE_S + 1.0)]
    probers = [
        subprocess.Popen(
            [sys.executable, "-c", PROBER, str(lease.module), str(lease.pool), *race_args]
        )
        for _ in range(RACE_PROBERS)
    ]
    try:
        time.sleep(0.3)
        short = tries = 0
        end = time.monotonic() + RACE_S
        while time.monotonic() < end:
            got = pool.try_acquire(1, RACE_TOKENS)
            tries += 1
            short += len(got) != RACE_TOKENS
            pool.release(got)
    finally:
        for proc in probers:
            proc.kill()
            proc.wait(timeout=ANSWER_S)
    if tries == 0:
        return ["no acquire ran in %.1fs: the scenario measured nothing" % RACE_S]
    if short:
        return ["%d of %d whole-pool acquires came back short while `free` probed" % (short, tries)]
    return []


def broker_asker(
    lease: Lease, label: str
) -> Callable[[dict[str, object]], dict[str, object] | None]:
    broker = lease.spawn("broker", "--label", label)

    def ask(req: dict[str, object]) -> dict[str, object] | None:
        assert broker.stdin is not None
        broker.stdin.write(json.dumps(req) + "\n")
        broker.stdin.flush()
        line = readline(broker, ANSWER_S)
        return None if line is None else json.loads(line)

    ask.proc = broker  # type: ignore[attr-defined]
    return ask


def scenario_runs_registered(lease: Lease) -> list[str]:
    """Two brokers each report runs 2; after kill -9 of one the survivor reports 1 and the dead marker is gone."""
    first = broker_asker(lease, "first")
    second = broker_asker(lease, "second")
    fails = []
    # A broker registers before it reads stdin, so one answered request apiece means both are registered.
    for ask in (first, second):
        ask({"op": "free"})
    for name, ask in (("second", second), ("first", first)):
        reply = ask({"op": "free"})
        if not reply or reply.get("runs") != 2:
            fails.append("%s broker's free reply is %r, want runs 2" % (name, reply))
    kill9(first.proc)  # type: ignore[attr-defined]
    reply = second({"op": "free"})
    if not reply or reply.get("runs") != 1:
        fails.append(
            "after kill -9 of one broker the survivor's free reply is %r, want runs 1" % reply
        )
    left = sorted((lease.pool / "runs").glob("*.lock"))
    if len(left) != 1:
        fails.append("the dead run's marker must be unlinked; %d marker file(s) remain" % len(left))
    return fails


# Each child registers, counts at once and lets go, over and over, beside the others: a counter that sees another's half-made marker must not be able to void it.
REGISTRAR = """
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("registered", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
sys.modules["registered"] = mod
spec.loader.exec_module(mod)
pool = mod.Pool(pathlib.Path(sys.argv[2]), 4)
pool.ensure()
zero = 0
for _ in range(int(sys.argv[3])):
    run = pool.register("race")
    zero += pool.live_runs() < 1
    run.close()
print(zero)
"""


def scenario_register_and_count(lease: Lease) -> list[str]:
    """Registering and counting at once, from several processes, never reads 0 for the run just registered."""
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", REGISTRAR, str(lease.module), str(lease.pool), "60"],
            stdout=subprocess.PIPE,
            text=True,
        )
        for _ in range(4)
    ]
    zeros = 0
    try:
        for proc in procs:
            out, _ = proc.communicate(timeout=ANSWER_S * 3)
            if proc.returncode != 0 or not out.strip().isdigit():
                return ["a registrar exited %s with output %r" % (proc.returncode, out)]
            zeros += int(out)
    finally:
        # The early return above leaves the other registrars running; reap them and close
        # their pipes, or their leaked FileIO is finalized inside a later test on this worker.
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
            proc.communicate(timeout=ANSWER_S)
    return ["%d count(s) read 0 for a live, just-registered run" % zeros] if zeros else []


def scenario_share_cap(lease: Lease) -> list[str]:
    """With two live runs on a 4-token pool, the pytest verb asked for `-n auto` takes 2, not 4."""
    other = broker_asker(lease, "other")
    reply = other({"op": "free"})
    if not reply or reply.get("runs") != 1:
        return ["setup: the other broker's free reply is %r, want runs 1" % reply]
    real = fake_pytest(lease.pool.parent)
    out = lease.run("pytest", "--real", str(real), "--", "-n", "auto")
    if out.returncode != 0:
        return ["the pytest verb exited %d: %s" % (out.returncode, out.stderr)]
    seen = json.loads(out.stdout)
    if seen["cores"] != "2" or seen["argv"] != ["-n", "2"]:
        return ["pytest -n auto beside 1 other run took %r, want 2 of 4" % seen]
    return []


SCENARIOS = {
    "over_grant": scenario_over_grant,
    "kill_frees": scenario_kill_frees,
    "partial_release": scenario_partial_release,
    "partial_release_silent": scenario_partial_release_silent,
    "short_without_wait": scenario_short_without_wait,
    "broker_eof": scenario_broker_eof,
    "probe_race": scenario_probe_race,
    "runs_registered": scenario_runs_registered,
    "register_and_count": scenario_register_and_count,
    "share_cap": scenario_share_cap,
}

# The plant that each scenario must catch, per the plan's Writer split (C).
PLANTED = [
    ("sidecar-count", "kill_frees"),
    ("no-settle", "partial_release"),
    ("blocking-flock", "over_grant"),
    ("unguarded-scan", "probe_race"),
    ("runs-file-count", "runs_registered"),
    ("runs-no-mutex", "register_and_count"),
    ("runs-no-cap", "share_cap"),
]


def drive(module: pathlib.Path, pool: pathlib.Path, name: str) -> list[str]:
    lease = Lease(module, pool)
    try:
        return SCENARIOS[name](lease)
    finally:
        lease.close()


def planted_copy(tmp_path: pathlib.Path, defect: str) -> pathlib.Path:
    original, replacement = core_lease.DEFECTS[defect]
    source = MODULE.read_text(encoding="utf-8")
    count = source.count(original)
    assert count == 1, "plant %r must match exactly once in %s, matched %d" % (
        defect,
        MODULE,
        count,
    )
    copy = tmp_path / ("core_lease_%s.py" % defect.replace("-", "_"))
    copy.write_text(source.replace(original, replacement), encoding="utf-8")
    return copy


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_scenario_is_green_on_the_real_module(name: str, tmp_path: pathlib.Path) -> None:
    fails = drive(MODULE, tmp_path / "pool", name)
    assert not fails, "\n".join(fails)


@pytest.mark.parametrize(("defect", "name"), PLANTED)
def test_planted_defect_turns_its_scenario_red(
    defect: str, name: str, tmp_path: pathlib.Path
) -> None:
    started = time.monotonic()
    fails = drive(planted_copy(tmp_path, defect), tmp_path / "pool", name)
    assert fails, "plant %r left scenario %r green: the scenario cannot see that defect" % (
        defect,
        name,
    )
    assert time.monotonic() - started < 6 * ANSWER_S


def test_every_defect_has_a_control() -> None:
    assert {d for d, _ in PLANTED} == set(core_lease.DEFECTS)


def test_selftest_is_green() -> None:
    out = subprocess.run(
        [sys.executable, str(MODULE), "selftest"],
        capture_output=True,
        text=True,
        timeout=ANSWER_S * 3,
        check=False,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert " 0 failed" in out.stdout


# --------------------------------------------------------------------------- the pytest verb


def fake_pytest(tmp_path: pathlib.Path) -> pathlib.Path:
    """A stand-in for the real pytest that prints the argv and environment it was exec'd with."""
    fake = tmp_path / "fake-pytest"
    fake.write_text(
        "#!%s\nimport json, os, sys\n"
        "print(json.dumps({'argv': sys.argv[1:], 'cores': os.environ.get('CI_RUNNER_CORES'),"
        " 'held': os.environ.get('CI_CORE_LEASE_HELD'),"
        " 'addopts': os.environ.get('PYTEST_ADDOPTS')}))\n" % sys.executable,
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake


@pytest.mark.parametrize(
    ("args", "addopts", "want_argv", "want_cores", "want_addopts"),
    [
        (["-q", "-n", "auto", "t.py"], None, ["-q", "-n", "4", "t.py"], "4", None),
        (["-q", "-n", "2"], None, ["-q", "-n", "2"], "2", None),
        (["-q", "-n", "16"], None, ["-q", "-n", "4"], "4", None),
        (["-q", "t.py"], None, ["-q", "t.py"], "1", None),
        (["-q"], "-n logical", ["-q"], "4", "-n 4"),
    ],
)
def test_wrapper_verb_rewrites_n_to_the_grant(
    tmp_path: pathlib.Path,
    args: list[str],
    addopts: str | None,
    want_argv: list[str],
    want_cores: str,
    want_addopts: str | None,
) -> None:
    lease = Lease(MODULE, tmp_path / "pool")
    env = lease.env()
    if addopts is not None:
        env["PYTEST_ADDOPTS"] = addopts
    out = subprocess.run(
        [sys.executable, str(MODULE), "pytest", "--real", str(fake_pytest(tmp_path)), "--", *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=ANSWER_S,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    seen = json.loads(out.stdout)
    assert seen == {
        "argv": want_argv,
        "cores": want_cores,
        "held": "1",
        "addopts": want_addopts,
    }


def test_wrapper_verb_with_a_held_lease_passes_through_untouched(tmp_path: pathlib.Path) -> None:
    lease = Lease(MODULE, tmp_path / "pool")
    holder = lease.spawn("acquire", "--max", "all")
    try:
        assert readline(holder, ANSWER_S) == str(TOKENS)
        env = {**lease.env(), core_lease.HELD_ENV: "1", core_lease.ENV: "7"}
        real = str(fake_pytest(tmp_path))
        out = subprocess.run(
            [sys.executable, str(MODULE), "pytest", "--real", real, "--", "-n", "auto"],
            capture_output=True,
            text=True,
            env=env,
            timeout=ANSWER_S,
            check=False,
        )
        # Every token is held, so a wrapper that leased anyway would block here until the timeout.
        assert out.returncode == 0, out.stderr
        assert json.loads(out.stdout)["argv"] == ["-n", "auto"]
    finally:
        lease.close()


def test_run_verb_holds_until_the_command_exits(tmp_path: pathlib.Path) -> None:
    lease = Lease(MODULE, tmp_path / "pool")
    try:
        child = lease.spawn(
            "run", "--max", "3", "--", sys.executable, "-c", "import sys; sys.stdin.read()"
        )
        deadline = time.monotonic() + ANSWER_S
        while lease.free() != 1 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert lease.free() == 1, "run --max 3 must hold 3 of 4 while its command lives"
        kill9(child)
        assert lease.free() == TOKENS, "the command's death must free the tokens it inherited"
    finally:
        lease.close()


def test_a_lease_dir_owned_by_another_user_is_refused(tmp_path: pathlib.Path) -> None:
    if pathlib.Path("/").stat().st_uid == os.getuid():
        pytest.skip("running as the owner of /, so / is not another user's directory here")
    # "/" is root's: pointing the pool at it shows the ownership refusal without a second user.
    env = {**Lease(MODULE, tmp_path).env(), core_lease.DIR_ENV: "/"}
    out = subprocess.run(
        [sys.executable, str(MODULE), "free"],
        capture_output=True,
        text=True,
        env=env,
        timeout=ANSWER_S,
        check=False,
    )
    assert out.returncode == core_lease.EXIT_UNUSABLE, out.stderr
    assert core_lease.DIR_ENV in out.stderr


def test_status_judges_liveness_only_inside_its_own_pid_namespace(tmp_path: pathlib.Path) -> None:
    """A live holder in this namespace is alive; the same sidecar stamped with another namespace (the devbox versus the host, sharing the directory through a bind mount) is reported as unknown, never as gone."""
    lease = Lease(MODULE, tmp_path / "pool")
    try:
        holder = lease.spawn("acquire", "--max", "1", "--label", "probe")
        assert readline(holder, ANSWER_S) == "1"
        rows = json.loads(lease.run("status", "--json").stdout)["held"]
        assert [(r["label"], r["holder_alive"], r["foreign_pidns"]) for r in rows] == [
            ("probe", True, False)
        ]
        sidecar = tmp_path / "pool" / "0.json"
        sidecar.write_text(
            json.dumps({**json.loads(sidecar.read_text()), "pidns": "not-this-one"}),
            encoding="utf-8",
        )
        out = lease.run("status")
        assert "another pid namespace" in out.stdout
        assert "gone" not in out.stdout
        rows = json.loads(lease.run("status", "--json").stdout)["held"]
        assert [(r["holder_alive"], r["foreign_pidns"]) for r in rows] == [(None, True)]
    finally:
        lease.close()


def test_broker_min_zero_takes_whatever_is_free(tmp_path: pathlib.Path) -> None:
    """The ci-runner's lease client asks `min: 0`: a full grant, then a short one, then an empty one, and never an error."""
    lease = Lease(MODULE, tmp_path / "pool")
    try:
        broker = lease.spawn("broker")
        assert broker.stdin is not None
        replies = []
        for req in (
            {"op": "free"},
            {"op": "acquire", "min": 0, "max": 3},
            {"op": "acquire", "min": 0, "max": 3},
            {"op": "acquire", "min": 0, "max": 2},
            {"op": "acquire", "min": 0, "max": "all"},
            {"op": "free"},
        ):
            broker.stdin.write(json.dumps(req) + "\n")
            broker.stdin.flush()
            line = readline(broker, ANSWER_S)
            assert line is not None, "the broker did not answer %r" % req
            replies.append(json.loads(line))
        assert [r.get("ids") for r in replies[1:5]] == [[0, 1, 2], [3], [], []]
        assert all("error" not in r for r in replies), replies
        assert (replies[0]["free"], replies[5]["free"]) == (TOKENS, 0)
        assert replies[5]["held"] == [0, 1, 2, 3]
        broker.stdin.close()
        assert broker.wait(timeout=ANSWER_S) == 0
        assert lease.free() == TOKENS
    finally:
        lease.close()


def test_module_form_runs_the_same_cli(tmp_path: pathlib.Path) -> None:
    """`python3 -m rediacc_ci.core_lease broker`, the lease client's spawn, answers like the file form."""
    lease = Lease(MODULE, tmp_path / "pool")
    env = {**lease.env(), "PYTHONPATH": str(MODULE.parent.parent)}
    out = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core_lease", "broker"],
        input='{"op":"free"}\n',
        capture_output=True,
        text=True,
        env=env,
        cwd=str(MODULE.parent.parent.parent),
        timeout=ANSWER_S,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == {"free": TOKENS, "held": [], "runs": 1, "total": TOKENS}


def test_unusable_runs_dir_is_exit_69(tmp_path: pathlib.Path) -> None:
    pool = tmp_path / "pool"
    pool.mkdir(mode=0o700)
    (pool / "runs").write_text("not a directory", encoding="utf-8")
    out = Lease(MODULE, pool).run("free")
    assert out.returncode == core_lease.EXIT_UNUSABLE, out.stderr
    assert "run marker directory" in out.stderr


def test_status_reports_the_live_run_count(tmp_path: pathlib.Path) -> None:
    lease = Lease(MODULE, tmp_path / "pool")
    try:
        ask = broker_asker(lease, "counted")
        assert ask({"op": "free"}) is not None
        assert "1 live run(s)" in lease.run("status").stdout
        assert json.loads(lease.run("status", "--json").stdout)["runs"] == 1
    finally:
        lease.close()
