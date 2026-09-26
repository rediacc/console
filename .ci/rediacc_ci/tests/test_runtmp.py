"""The control for `rediacc_ci.runtmp`: a run that is KILLED leaves nothing a later sweep does not remove.

The case that matters is driven for real. A child process creates its run directory through the helper, fills it, and is SIGKILLed mid-run, so neither `atexit` nor any `finally` gets a chance. The sweep then has to remove that directory while a directory stamped with a LIVE pid survives beside it.

A CONTROL THAT CANNOT FAIL IS NOT A CONTROL, so the same scenario is also run with the sweep replaced by a no-op, and that run must fail the assertion. If it ever passes, the scenario stopped exercising the sweep and its green means nothing.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys

import pytest

from rediacc_ci import runtmp

CI_DIR = pathlib.Path(__file__).resolve().parents[2]

_CHILD = r"""
import os, pathlib, sys, time
sys.path.insert(0, sys.argv[1])
from rediacc_ci import runtmp
d = pathlib.Path(runtmp.run_dir("runtmp-ctl-", base=sys.argv[2]))
for i in range(50):
    (d / ("f%d" % i)).write_text("x")
(d / "nested").mkdir()
print(d, flush=True)
time.sleep(120)
"""


def _killed_child_dir(base: pathlib.Path) -> pathlib.Path:
    child = subprocess.Popen(
        [sys.executable, "-c", _CHILD, str(CI_DIR), str(base)],
        stdout=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
    )
    assert child.stdout is not None
    try:
        line = child.stdout.readline().strip()
        assert line, "the child never reported its run dir; the control did not start"
        run = pathlib.Path(line)
        assert run.is_dir(), "the child never created its run dir"
        assert len(list(run.iterdir())) == 51, "the child's run dir is not populated"
    finally:
        child.send_signal(signal.SIGKILL)
        # Reaped before the sweep: an unreaped zombie still answers kill(pid, 0) and counts as alive.
        child.wait(timeout=10)
        child.stdout.close()
    assert child.returncode == -signal.SIGKILL
    # SIGKILL skips atexit, which is the whole premise; prove the leak exists before crediting the sweep.
    assert run.is_dir(), (
        "the killed child's dir vanished on its own, so the sweep is not what removes it"
    )
    return run


def _scenario(base: pathlib.Path, sweep) -> None:
    # The live dir first: `run_dir` sweeps before it creates, so making it AFTER the kill would sweep the dead one before the sweep under test ever ran.
    live = pathlib.Path(runtmp.run_dir("runtmp-ctl-", base=str(base)))
    (live / "keep").write_text("x")
    dead = _killed_child_dir(base)
    removed = sweep("runtmp-ctl-", str(base))
    assert live.is_dir(), "the sweep removed a LIVE run's directory"
    assert (live / "keep").is_file(), "the sweep emptied a LIVE run's directory"
    assert not dead.exists(), "the killed run's directory survived the sweep: %s" % dead
    assert removed == [str(dead)]


def test_a_killed_run_is_swept_and_a_live_one_survives(tmp_path: pathlib.Path) -> None:
    _scenario(tmp_path, runtmp.sweep_dead)


def test_planted_defect_a_disabled_sweep_fails_the_control(tmp_path: pathlib.Path) -> None:
    with pytest.raises(AssertionError, match="survived the sweep"):
        _scenario(tmp_path, lambda _prefix, _base: [])


def _dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_the_sweep_leaves_everything_it_cannot_prove_dead(tmp_path: pathlib.Path) -> None:
    dead = _dead_pid()
    ns = runtmp.stamp("x-").split("-n", 1)[1].rstrip("-")
    keep = [
        "runtmp-ctl-notapid-n%s-abc" % ns,  # unparseable pid
        "runtmp-ctl-%d-n%s-abc" % (os.getpid(), ns),  # this process
        "runtmp-ctl-%d-n999999999999-abc" % dead,  # another pid namespace
        "other-%d-n%s-abc" % (dead, ns),  # another prefix
        "runtmp-ctl-x-%d-n%s-abc" % (dead, ns),  # a longer prefix that merely starts the same
    ]
    for name in keep:
        (tmp_path / name).mkdir()
    (tmp_path / ("runtmp-ctl-%d-n%s-file" % (dead, ns))).write_text("not a dir")
    gone = tmp_path / ("runtmp-ctl-%d-n%s-abc" % (dead, ns))
    gone.mkdir()
    assert runtmp.sweep_dead("runtmp-ctl-", str(tmp_path)) == [str(gone)]
    assert not gone.exists()
    for name in keep:
        assert (tmp_path / name).is_dir(), name
    assert (tmp_path / ("runtmp-ctl-%d-n%s-file" % (dead, ns))).is_file()


def test_run_dir_is_stamped_with_this_pid_and_namespace(tmp_path: pathlib.Path) -> None:
    d = pathlib.Path(runtmp.run_dir("runtmp-ctl-", base=str(tmp_path)))
    assert d.parent == tmp_path
    assert d.name.startswith(runtmp.stamp("runtmp-ctl-"))
    assert d.name.startswith("runtmp-ctl-%d-n" % os.getpid())


@pytest.mark.parametrize("bad", ["", "nodash", "-lead-", "9digit-", "sp ace-"])
def test_a_prefix_that_could_collide_is_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="must be non-empty"):
        runtmp.stamp(bad)
    with pytest.raises(ValueError, match="must be non-empty"):
        runtmp.sweep_dead(bad)


def test_a_normal_exit_leaves_nothing(tmp_path: pathlib.Path) -> None:
    code = "import sys; sys.path.insert(0, sys.argv[1]); from rediacc_ci import runtmp; print(runtmp.run_dir('runtmp-ctl-', base=sys.argv[2]))"
    done = subprocess.run(
        [sys.executable, "-c", code, str(CI_DIR), str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    made = pathlib.Path(done.stdout.strip())
    assert made.name.startswith("runtmp-ctl-")
    assert not made.exists()
    assert list(tmp_path.iterdir()) == []


def test_shared_is_one_run_dir_per_prefix_and_is_remade_when_removed(
    tmp_path: pathlib.Path,
) -> None:
    a = runtmp.shared("runtmp-ctl-", base=str(tmp_path))
    assert runtmp.shared("runtmp-ctl-", base=str(tmp_path)) == a
    assert runtmp.shared("runtmp-other-", base=str(tmp_path)) != a
    os.rmdir(a)
    b = runtmp.shared("runtmp-ctl-", base=str(tmp_path))
    assert b != a
    assert os.path.isdir(b)


# --------------------------------------------------------------------------- the BASH contract
# A bash script cannot import runtmp, so it carries `runtmp.SHELL_MKTEMP` verbatim and relies on a Python `run_dir` (every suite and gate start) to sweep what it left. These cases run that line under a REAL bash.

# The directories holding the four external tools the spelling and these scripts use, so the bash's PATH is built without reading this process's environment.
_BASH_PATH = os.pathsep.join(
    sorted(
        {
            os.path.dirname(shutil.which(tool) or "/usr/bin/" + tool)
            for tool in ("bash", "mktemp", "stat", "sleep")
        }
    )
)

# How long the LIVE script waits: long enough to outlast the case, and it is killed in `finally` anyway.
_LIVE_FOR = "sleep %d" % 120


def _bash_run(
    base: pathlib.Path, spelling: str, *, then: str
) -> tuple[subprocess.Popen, pathlib.Path]:
    child = subprocess.Popen(
        ["bash", "-c", 'd="$(%s)" || exit 3; echo "$d"; %s' % (spelling, then)],
        stdout=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        env={"PATH": _BASH_PATH, "TMPDIR": str(base)},
    )
    assert child.stdout is not None
    made = pathlib.Path(child.stdout.readline().strip())
    assert made.is_dir(), "the bash spelling did not create a directory"
    (made / "payload").write_text("x")
    return child, made


def _reap(child: subprocess.Popen) -> None:
    child.wait(timeout=10)
    assert child.stdout is not None
    child.stdout.close()


def _shell_scenario(base: pathlib.Path, spelling: str) -> None:
    live, live_dir = _bash_run(base, spelling, then=_LIVE_FOR)
    try:
        # `kill -9 $$`: the script kills ITSELF, so no EXIT trap can run, which is the case the contract exists for.
        dead, dead_dir = _bash_run(base, spelling, then="kill -9 $$")
        _reap(dead)
        assert dead.returncode == -signal.SIGKILL
        assert dead_dir.is_dir(), (
            "the killed script's dir vanished on its own; the sweep is not what removes it"
        )
        removed = runtmp.sweep_dead(runtmp.SHELL_PREFIX, str(base))
        assert live_dir.is_dir(), "the sweep removed a LIVE script's directory"
        assert not dead_dir.exists(), (
            "the killed script's directory survived the sweep: %s" % dead_dir
        )
        assert removed == [str(dead_dir)]
    finally:
        live.kill()
        _reap(live)


def test_a_killed_bash_script_is_swept_and_a_live_one_survives(tmp_path: pathlib.Path) -> None:
    _shell_scenario(tmp_path, runtmp.shell_mktemp("ctl"))


def test_planted_defect_a_spelling_that_drops_the_namespace_fails_the_control(
    tmp_path: pathlib.Path,
) -> None:
    planted = runtmp.shell_mktemp("ctl").replace(
        "$(stat -Lc %i /proc/self/ns/pid 2>/dev/null || echo 0)", "0"
    )
    assert planted != runtmp.shell_mktemp("ctl"), (
        "the plant did not apply; the control is broken, not the contract"
    )
    with pytest.raises(AssertionError, match="survived the sweep"):
        _shell_scenario(tmp_path, planted)


def test_run_dir_also_sweeps_dead_bash_dirs(tmp_path: pathlib.Path) -> None:
    dead, dead_dir = _bash_run(tmp_path, runtmp.shell_mktemp("ctl"), then="kill -9 $$")
    _reap(dead)
    runtmp.run_dir("runtmp-ctl-", base=str(tmp_path))
    assert not dead_dir.exists()


def test_a_bad_shell_tag_is_refused() -> None:
    with pytest.raises(ValueError, match="lowercase words"):
        runtmp.shell_mktemp("Bad Tag")


# The bash files that carry the contract today. A KNOWN-POSITIVE set rather than a count: a scan that stops seeing them reports each one missing instead of a clean tree.
_SHELL_USERS = {
    ".ci/media/coverage.sh",
    ".ci/scripts/test/gates/test-toolchain.sh",
    ".ci/scripts/test/lib/test-helpers.sh",
    ".ci/scripts/test/run-account-e2e.sh",
    ".ci/scripts/test/test-install-methods.sh",
    ".ci/tutorials/record.sh",
}


def test_every_bash_use_of_the_prefix_is_the_canonical_spelling() -> None:
    root = CI_DIR.parent
    shape = re.compile(
        re.escape(runtmp.SHELL_MKTEMP)
        .replace("%%", "%")
        .replace("%s", "([a-z0-9]+(?:-[a-z0-9]+)*)")
    )
    users: set[str] = set()
    drift: list[str] = []
    for top in (".ci", ".claude", "scripts"):
        for path in sorted((root / top).rglob("*.sh")):
            text = path.read_text(encoding="utf-8", errors="replace")
            for n, line in enumerate(text.splitlines(), 1):
                if runtmp.SHELL_PREFIX not in line:
                    continue
                rel = str(path.relative_to(root))
                users.add(rel)
                if not shape.search(line):
                    drift.append("%s:%d  %s" % (rel, n, line.strip()))
    assert not drift, (
        "a bash use of %r drifted from runtmp.SHELL_MKTEMP; copy it verbatim:\n  %s"
        % (
            runtmp.SHELL_PREFIX,
            "\n  ".join(drift),
        )
    )
    missing = _SHELL_USERS - users
    assert not missing, "known users of the contract no longer found by the scan: %s" % sorted(
        missing
    )
