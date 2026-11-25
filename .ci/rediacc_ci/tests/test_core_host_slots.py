"""`host_slots.host_slot`: a block-scoped hold on the machine-wide core pool (PR-TASK 79b7e92e).

Every case runs against a private 2-token pool (`REDIACC_CORE_LEASE_DIR` under tmp_path, `REDIACC_CORE_LEASE_TOKENS=2`), with holders as REAL processes, because a token is a kernel flock and only another process proves what the kernel does. Both directions: two holders fill the pool and a third waits (printing one line naming the holders), then gets a slot the moment one holder leaves; a holder killed with SIGKILL frees its slot with no cleanup of its own; a block under a parent's held lease takes nothing even from a full pool; an unusable pool is named loudly and the block still runs. The planted `DEFECT` (no release) must make a second sequential block in one process wait on its own finished predecessor.
"""

import importlib.util
import io
import os
import pathlib
import signal
import subprocess
import sys
import time

import pytest

from rediacc_ci import core_lease
from rediacc_ci.core import host_slots
from rediacc_ci.dev import worktree_lease

CI_DIR = pathlib.Path(__file__).resolve().parents[2]
HOLDER = (
    "import sys\n"
    "from rediacc_ci.core.host_slots import host_slot\n"
    "with host_slot(int(sys.argv[1]), label=sys.argv[2]):\n"
    "    print('held', flush=True)\n"
    "    sys.stdin.read()\n"
)


@pytest.fixture
def pool_env(tmp_path, monkeypatch):
    env = {
        core_lease.DIR_ENV: str(tmp_path / "cores"),
        core_lease.TOKENS_ENV: "2",
    }
    for key in (core_lease.HELD_ENV, core_lease.ENV):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


def _holder(pool_env, weight=1, label="holder"):
    env = {**os.environ, **pool_env, "PYTHONPATH": str(CI_DIR)}
    env.pop(core_lease.HELD_ENV, None)
    proc = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(weight), label],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = proc.stdout.readline()
    assert line.strip() == "held", (line, proc.stderr.read() if proc.poll() is not None else "")
    return proc


def _release(proc):
    proc.stdin.close()
    proc.wait(timeout=10)
    proc.stdout.close()
    proc.stderr.close()


def _free(pool_env):
    return core_lease.Pool.from_env(pool_env).free_count()


def test_third_waits_while_two_hold_and_starts_when_one_leaves(pool_env):
    first = _holder(pool_env, label="first")
    second = _holder(pool_env, label="second")
    try:
        assert _free(pool_env) == 0
        out = io.StringIO()
        with (
            pytest.raises(TimeoutError),
            host_slots.host_slot(1, label="third", timeout=0.6, stream=out),
        ):
            pytest.fail("a third block entered a full 2-token pool")
        lines = [line for line in out.getvalue().splitlines() if line]
        assert len(lines) == 1, lines
        assert "third waits for 1 core slot(s): 2 of 2 held by 2 other live run(s)" in lines[0], (
            lines[0]
        )
        assert "core_lease.py status" in lines[0]
        _release(first)
        started = time.monotonic()
        with host_slots.host_slot(1, label="third", timeout=5, stream=io.StringIO()) as slot:
            assert slot.held
            assert slot.cores == 1
            assert slot.env == {core_lease.ENV: "1", core_lease.HELD_ENV: "1"}
            assert _free(pool_env) == 0
        assert time.monotonic() - started < 3
        assert _free(pool_env) == 1, "leaving the block must hand its token back"
    finally:
        for proc in (first, second):
            if proc.poll() is None:
                _release(proc)


def test_a_killed_holder_never_blocks(pool_env):
    holder = _holder(pool_env, weight=2, label="doomed")
    assert _free(pool_env) == 0
    os.kill(holder.pid, signal.SIGKILL)
    _release(holder)
    with host_slots.host_slot(2, label="after-kill", timeout=5, stream=io.StringIO()) as slot:
        assert slot.cores == 2


def test_under_a_held_parent_lease_it_takes_nothing(pool_env, monkeypatch):
    holder = _holder(pool_env, weight=2, label="parent")
    try:
        monkeypatch.setenv(core_lease.HELD_ENV, "1")
        monkeypatch.setenv(core_lease.ENV, "3")
        with host_slots.host_slot(8, label="child", timeout=0.5) as slot:
            assert slot.nested
            assert not slot.held
            assert slot.cores == 3
            assert slot.env[core_lease.HELD_ENV] == "1"
        assert _free(pool_env) == 0
    finally:
        _release(holder)


@pytest.mark.usefixtures("pool_env")
def test_weight_above_the_pool_is_clamped():
    with host_slots.host_slot(32, label="wide", timeout=2, stream=io.StringIO()) as slot:
        assert slot.cores == 2


def test_an_unusable_pool_is_loud_and_runs_unthrottled(tmp_path, monkeypatch):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv(core_lease.DIR_ENV, str(blocker / "cores"))
    monkeypatch.delenv(core_lease.HELD_ENV, raising=False)
    out = io.StringIO()
    ran = []
    with host_slots.host_slot(2, label="seed", stream=out) as slot:
        ran.append(slot)
    assert ran
    assert not ran[0].held
    assert "the core pool is unusable" in out.getvalue()
    assert "seed runs UNTHROTTLED" in out.getvalue()


@pytest.mark.parametrize("failing", ["register", "acquire"])
@pytest.mark.parametrize("exc_type", [OSError, core_lease.LeaseError])
def test_a_pool_that_fails_after_opening_is_loud_and_runs_unthrottled(
    pool_env, monkeypatch, failing, exc_type
):
    """Reviews 426f94b6.1 and b04212c7.1: the docstring promises an unusable pool (`LeaseError` or `OSError`) runs the block unthrottled, and that holds for a pool that opens and then fails on `register` or `acquire` with either."""
    pool = core_lease.Pool.from_env(pool_env)

    def broken(*_a, **_k):
        if exc_type is OSError:
            raise OSError(28, "No space left on device")
        raise exc_type("No space left on device")

    monkeypatch.setattr(pool, failing, broken)
    out = io.StringIO()
    ran = []
    with host_slots.host_slot(2, label="seed", stream=out, pool=pool) as slot:
        ran.append(slot)
    assert ran
    assert not ran[0].held
    assert "the core pool is unusable" in out.getvalue()
    assert "No space left on device" in out.getvalue()
    assert "seed runs UNTHROTTLED" in out.getvalue()


def test_control_an_oserror_from_the_block_body_is_not_swallowed(pool_env):
    """A pool failure is forgiven, the caller's own OSError is not: it must still reach the caller, and the tokens still come back."""
    with (
        pytest.raises(OSError, match="from the body"),
        host_slots.host_slot(1, label="body", timeout=2, stream=io.StringIO()),
    ):
        raise OSError("from the body")
    assert _free(pool_env) == 2


def test_control_a_timeout_is_still_a_refusal_not_an_unthrottled_run(pool_env):
    holder = _holder(pool_env, weight=2, label="full")
    try:
        with (
            pytest.raises(TimeoutError),
            host_slots.host_slot(1, label="late", timeout=0.3, stream=io.StringIO()),
        ):
            pass
    finally:
        _release(holder)


@pytest.mark.usefixtures("pool_env")
def test_weight_below_one_is_refused():
    with pytest.raises(ValueError, match="at least 1"), host_slots.host_slot(0):
        pass


def test_sequential_blocks_reuse_the_slot(pool_env):
    for _ in range(3):
        with host_slots.host_slot(2, label="again", timeout=2, stream=io.StringIO()) as slot:
            assert slot.cores == 2
    assert _free(pool_env) == 2


@pytest.mark.usefixtures("pool_env")
def test_planted_defect_leaks_the_tokens(tmp_path):
    """Red-once control: with the release planted out, the second block of one process waits on the first one's tokens."""
    old, new = host_slots.DEFECT
    source = pathlib.Path(host_slots.__file__).read_text(encoding="utf-8")
    assert source.count(old) == 1, "the DEFECT anchor moved; this control would plant nothing"
    planted = tmp_path / "host_slots_planted.py"
    planted.write_text(source.replace(old, new), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("host_slots_planted", planted)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    with module.host_slot(2, label="leaky", timeout=2, stream=io.StringIO()):
        pass
    with (
        pytest.raises(TimeoutError),
        module.host_slot(2, label="leaky", timeout=0.5, stream=io.StringIO()),
    ):
        pass


def _fake_seed(pool_env, seen):
    def run(argv, code, env):
        seen.append({"env": env, "free": _free(pool_env), "argv": argv, "code": code})
        return subprocess.CompletedProcess(argv, 0)

    return run


def test_the_lease_seed_runs_inside_a_host_slot(pool_env, monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(worktree_lease, "_seed_process", _fake_seed(pool_env, seen))
    worktree_lease._run_seed(tmp_path / "lease-x", tmp_path, "0" * 40)
    assert len(seen) == 1
    assert seen[0]["free"] == 0, "the seed must hold SEED_SLOTS of the 2-token pool while it runs"
    assert seen[0]["env"][core_lease.ENV] == str(worktree_lease.SEED_SLOTS)
    assert seen[0]["env"][core_lease.HELD_ENV] == "1"
    assert _free(pool_env) == 2, "the seed's slot must be handed back"


def test_a_full_pool_delays_the_seed_only_up_to_the_bound(pool_env, monkeypatch, tmp_path, capsys):
    holder = _holder(pool_env, weight=2, label="ci-quick")
    try:
        seen = []
        monkeypatch.setattr(worktree_lease, "_seed_process", _fake_seed(pool_env, seen))
        monkeypatch.setattr(worktree_lease, "SEED_SLOT_WAIT_S", 0.4)
        worktree_lease._run_seed(tmp_path / "lease-y", tmp_path, "0" * 40)
        assert len(seen) == 1
        assert core_lease.HELD_ENV not in seen[0]["env"]
        err = capsys.readouterr().err
        assert (
            "lease seed lease-y waits for 2 core slot(s): 2 of 2 held by 1 other live run(s)" in err
        )
        assert "lease seed lease-y runs unthrottled" in err
    finally:
        _release(holder)
