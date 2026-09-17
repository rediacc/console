"""Differential: `.ci/rediacc_ci/private/renet_ebpf_e2e.py` against its twin `.ci/scripts/private/renet-ebpf-e2e.sh`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new code is correct", it is "the new code says what the old code said". Only running BOTH, on the same fixture, in the same run, can support that.

NOTHING PRIVILEGED IS EVER INVOKED. The subject probes a filesystem type, MOUNTS bpffs and runs root-only eBPF tests; a suite that let any of that reach the real system would need root, would alter the host's mount table, and would SKIP wherever it could not, which is the exact vacuity this campaign exists to avoid. `stat`, `mount` and `go` are all recording fakes on a scratch
PATH: each appends its cwd and full argv to one shared log and returns canned bytes and a canned status. That is also the only way to drive the two cases that matter most and cannot be produced on a developer machine at all: "bpffs is already mounted" and "the tests ran green having skipped every one of them".

WHAT IS COMPARED, AND WHY IT IS FOUR THINGS. Every case compares:

  1. the exit code, which for a failed mount is MOUNT'S OWN status, not 1;
  2. stdout, which carries the go transcript, anything `mount` printed, and the
     `::error::` annotation;
  3. stderr, which carries the `log_step`/`log_info` lines and anything `mount`
     wrote there;
  4. the CALL LOG, in ORDER: whether `stat` was asked, whether `mount` followed,
     and the exact `go` argv. A port that printed the same transcript while
     never mounting, or while mounting when the probe already said `bpf_fs`,
     passes a stdout-only comparison and is a different program.

PATH IS REPLACED, NEVER PREPENDED. This host has a real `go`, a real `stat` and a real `mount`, and a prepend would leave the "not installed" cases silently consulting them. `_binder` builds the ENTIRE PATH out of named tools and asserts that what it was asked to exclude really is absent, because a probe that cannot fire looks exactly like a subject that cannot fail.

THE ONE MASK. Bash prefixes its own diagnostics with `<$0>: line <n>: `, naming the file it is running; the port composes the same prefix from `sys.argv[0]` and its own live frame. Those can never be equal, so `_mask` collapses exactly that prefix on both sides and compares everything after it byte for byte. `test_the_mask_does_not_hide_the_message` pins the mask so it cannot
quietly grow into something that hides a real divergence.
"""

import os
import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "private" / "renet-ebpf-e2e.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "private" / "renet_ebpf_e2e.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/private/renet-ebpf-e2e.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/private/renet_ebpf_e2e.py")

# U+2014, as an escape: this file lives under `.ci`, which `check:ci-em-dash-surfaces` scans, and the twin's annotation contains the character itself.
EM_DASH = "\u2014"
ZERO_TESTS_ERROR = (
    "::error::ebpf_e2e executed zero tests (all skipped) %s "
    "root/bpffs/cgroup2 prerequisites not met on this runner" % EM_DASH
)

# The three recording fakes. Each is configured by its own TEXT rather than through the environment: the subject advertises "No env vars", and a fixture that added several would make any env-shaped divergence unattributable.
#
# RAW BYTES ON BOTH STREAMS, each flushed immediately: one case drives `go` output that is not valid UTF-8, and the flushes make the `2>&1` interleaving deterministic where an unflushed pair would not be.
FAKE_TOOL = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
ROOT = %(root)r
NAME = %(name)r
RC = %(rc)d
OUT = %(out)r
ERR = %(err)r
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join([NAME, os.path.relpath(os.getcwd(), ROOT), *sys.argv[1:]]) + "\\n")
sys.stdout.buffer.write(OUT)
sys.stdout.buffer.flush()
sys.stderr.buffer.write(ERR)
sys.stderr.buffer.flush()
sys.exit(RC)
"""

# Everything both subjects need once PATH is rebuilt from scratch. `stat` and `mount` are DELIBERATELY ABSENT from this list: they are supplied as fakes, and a real one leaking in would touch the host's mount table.
NEEDED = (
    "bash",
    "sh",
    "python3",
    "uname",
    "dirname",
    "cat",
    "grep",
    "sed",
    "rm",
    "mkdir",
    "env",
    "ls",
)

# A green `go test -tags ebpf_e2e` transcript, and one in which every test skipped -- the second is the whole reason the loud-skip guard exists.
EBPF_NAMES = ("TestEBPF_BindRewrite", "TestEBPF_ConnectIsolation")
ALL_PASS = (
    "".join("=== RUN   %s\n--- PASS: %s (0.11s)\n" % (name, name) for name in EBPF_NAMES)
    + "PASS\nok\tgithub.com/rediacc/renet/pkg/ebpf\t0.310s\n"
).encode("utf-8")
ALL_SKIP = (
    "".join(
        "=== RUN   %s\n--- SKIP: %s (0.00s)\n    ebpf_test.go:22: requires root\n" % (name, name)
        for name in EBPF_NAMES
    )
    + "PASS\nok\tgithub.com/rediacc/renet/pkg/ebpf\t0.004s\n"
).encode("utf-8")

SHELL_PREFIX = re.compile(r"^[^\n]*?: line \d+: ", re.MULTILINE)


def _mask(text: str, root: pathlib.Path, tmp: pathlib.Path) -> str:
    text = SHELL_PREFIX.sub("<shell>: ", text)
    return text.replace(str(root), "<root>").replace(str(tmp), "<tmp>")


def _fixture(tmp_path: pathlib.Path, *, submodule: str = "dir") -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    Copies, because each subject derives the console root from its own location and driving the tracked files with a `cwd` would point both at the REAL repository. `.resolve()` on the root is load-bearing: bash's `cd X && pwd` reports the LOGICAL path while `pathlib.resolve()` follows symlinks, and the root string appears in the `cd` diagnostic.
    """
    root = tmp_path.resolve() / "tree"
    (root / ".ci" / "scripts" / "private").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "private").mkdir(parents=True)
    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(PORT, root / PORT_REL)

    if submodule == "dir":
        (root / "private" / "renet" / "pkg" / "ebpf").mkdir(parents=True)
    elif submodule == "file":
        (root / "private").mkdir(parents=True)
        (root / "private" / "renet").write_text("gitlink\n", encoding="utf-8")
    return root


def _binder(
    tmp_path: pathlib.Path,
    *,
    stat: str = "ok",
    fstype: bytes = b"sysfs\n",
    stat_rc: int = 0,
    mount: str = "ok",
    mount_rc: int = 0,
    mount_out: bytes = b"",
    mount_err: bytes = b"",
    go: str = "ok",
    go_rc: int = 0,
    out: bytes = ALL_PASS,
    err: bytes = b"",
) -> str:
    """The COMPLETE PATH for one case: named real tools, plus three fakes.

    Each of `stat`, `mount` and `go` takes one of "ok" (a recording fake), "missing" (absent from PATH entirely) and "noexec" (present, not executable) -- the third is the only shape for which bash names the resolved path instead of the bare word.
    """
    binder = tmp_path.resolve() / "bin"
    binder.mkdir(parents=True, exist_ok=True)
    for tool in NEEDED:
        target = shutil.which(tool)
        if target is None:
            continue
        link = binder / tool
        if not link.exists():
            link.symlink_to(target)

    spec = {
        "stat": (stat, stat_rc, fstype, b""),
        "mount": (mount, mount_rc, mount_out, mount_err),
        "go": (go, go_rc, out, err),
    }
    for name, (mode, rc, tool_out, tool_err) in spec.items():
        path = binder / name
        if path.exists():
            path.unlink()
        if mode == "missing":
            continue
        path.write_text(
            FAKE_TOOL
            % {
                "log": str(tmp_path.resolve() / "calls.log"),
                "root": str(tmp_path.resolve() / "tree"),
                "name": name,
                "rc": rc,
                "out": tool_out,
                "err": tool_err,
            },
            encoding="utf-8",
        )
        path.chmod(0o755 if mode == "ok" else 0o644)

    assert shutil.which("bash", path=str(binder)), "the restricted PATH cannot run the twin"
    assert shutil.which("python3", path=str(binder)), "the restricted PATH cannot run the port"
    for name, (mode, _rc, _o, _e) in spec.items():
        if mode == "missing":
            assert shutil.which(name, path=str(binder), mode=os.F_OK) is None, (
                "%r survived exclusion; the case that needs it absent would be vacuous" % name
            )
        if mode == "noexec":
            assert shutil.which(name, path=str(binder)) is None, (
                "the fake %r is still executable; the Permission denied case is vacuous" % name
            )
    return str(binder)


def _run(
    subject: pathlib.PurePosixPath,
    root: pathlib.Path,
    tmp_path: pathlib.Path,
    binder: str,
    argv: tuple[str, ...] = (),
) -> dict[str, object]:
    """Drive one subject and collect all four observables."""
    env = {
        "PATH": binder,
        "HOME": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
        # The port imports `rediacc_ci.log`; the COPY under the fixture is what runs, so the package has to come from the real checkout. This is the only thing the fixture borrows from outside itself.
        "PYTHONPATH": str(ROOT / ".ci"),
    }
    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(root / subject), *argv],
        capture_output=True,
        env=env,
        check=False,
        timeout=120,
        # BYTES: one case drives output that is not valid UTF-8.
    )
    log = tmp_path.resolve() / "calls.log"
    calls: list[str] = []
    if log.exists():
        calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
        log.unlink()
    return {
        "exit": proc.returncode,
        "stdout": _mask(proc.stdout.decode("utf-8", "backslashreplace"), root, tmp_path.resolve()),
        "stderr": _mask(proc.stderr.decode("utf-8", "backslashreplace"), root, tmp_path.resolve()),
        "calls": calls,
    }


CASES = [
    pytest.param({"fstype": b"bpf_fs\n"}, {}, id="already-mounted-no-mount-call"),
    pytest.param({}, {}, id="not-mounted-so-mount-runs"),
    pytest.param(
        {"fstype": b"bpf_fs\n"},
        {"argv": ("--unexpected", "arguments")},
        id="arguments-are-ignored-entirely",
    ),
    pytest.param({"fstype": b"bpf_fs"}, {}, id="probe-answer-without-a-newline"),
    pytest.param({"fstype": b"bpf_fs\n\n\n"}, {}, id="probe-answer-with-extra-newlines"),
    pytest.param({"fstype": b"bpf\n"}, {}, id="probe-says-bpf-not-bpf-fs"),
    pytest.param({"fstype": b"", "stat_rc": 1}, {}, id="probe-failed"),
    pytest.param({"stat": "missing"}, {}, id="stat-is-not-installed"),
    pytest.param({"stat": "noexec"}, {}, id="stat-is-not-executable"),
    pytest.param(
        {"mount_rc": 32, "mount_err": b"mount: /sys/fs/bpf: permission denied.\n"},
        {},
        id="mount-fails-with-its-own-status",
    ),
    pytest.param(
        {"mount_out": b"mount said something\n", "mount_err": b"and warned\n"},
        {},
        id="mount-output-passes-through",
    ),
    pytest.param({"mount": "missing"}, {}, id="mount-is-not-installed"),
    pytest.param({"mount": "noexec"}, {}, id="mount-is-not-executable"),
    pytest.param({"fstype": b"bpf_fs\n", "out": ALL_SKIP}, {}, id="every-test-skipped"),
    pytest.param({"fstype": b"bpf_fs\n", "out": b""}, {}, id="no-output-at-all"),
    pytest.param(
        {"fstype": b"bpf_fs\n", "out": ALL_PASS, "go_rc": 1},
        {},
        id="go-fails-despite-a-passing-transcript",
    ),
    pytest.param(
        {"fstype": b"bpf_fs\n", "out": ALL_SKIP, "go_rc": 2},
        {},
        id="go-fails-having-skipped",
    ),
    pytest.param(
        {"fstype": b"bpf_fs\n", "out": ALL_PASS + b"\n\n\n"},
        {},
        id="trailing-blank-lines-collapse",
    ),
    pytest.param(
        {"fstype": b"bpf_fs\n", "out": b"", "err": ALL_PASS},
        {},
        id="go-wrote-only-to-stderr",
    ),
    pytest.param(
        {"fstype": b"bpf_fs\n", "out": b"ok \xffbad-utf8\n" + ALL_PASS},
        {},
        id="output-that-is-not-valid-utf8",
    ),
    pytest.param({"fstype": b"bpf_fs\n", "go": "missing"}, {}, id="go-is-not-installed"),
    pytest.param({"fstype": b"bpf_fs\n", "go": "noexec"}, {}, id="go-is-not-executable"),
    pytest.param({}, {"submodule": "none"}, id="submodule-not-checked-out"),
    pytest.param({}, {"submodule": "file"}, id="submodule-path-is-a-file"),
]


@pytest.mark.parametrize(("binder_kw", "fixture_kw"), CASES)
def test_port_and_twin_agree(tmp_path, binder_kw, fixture_kw):
    root = _fixture(tmp_path, **{k: v for k, v in fixture_kw.items() if k == "submodule"})
    binder = _binder(tmp_path, **binder_kw)
    argv = fixture_kw.get("argv", ())

    old = _run(TWIN_REL, root, tmp_path, binder, argv=argv)
    new = _run(PORT_REL, root, tmp_path, binder, argv=argv)

    for field in ("exit", "stdout", "stderr", "calls"):
        assert new[field] == old[field], "%s diverged:\n twin: %r\n port: %r" % (
            field,
            old[field],
            new[field],
        )


def test_every_fake_is_actually_reached(tmp_path):
    """ANTI-VACUITY. Every comparison above is worthless if the fakes never ran.

    The go argv is asserted ELEMENT BY ELEMENT rather than as a blob, because `-tags ebpf_e2e` is the one flag without which these tests are not even compiled, and a port that dropped it would still print a green transcript.
    """
    root = _fixture(tmp_path)
    binder = _binder(tmp_path)
    out = _run(PORT_REL, root, tmp_path, binder)
    names = [line.split("\t")[0] for line in out["calls"]]
    assert names == ["stat", "mount", "go"], "call order was %r" % (names,)

    probe = out["calls"][0].split("\t")
    assert probe[2:] == ["-f", "-c", "%T", "/sys/fs/bpf"], "stat argv was %r" % (probe[2:],)

    mount = out["calls"][1].split("\t")
    assert mount[2:] == ["-t", "bpf", "bpffs", "/sys/fs/bpf"], "mount argv was %r" % (mount[2:],)

    go = out["calls"][2].split("\t")
    assert go[1] == "private/renet", "go ran in %r, not the renet source dir" % go[1]
    assert go[2:] == [
        "test",
        "-tags",
        "ebpf_e2e",
        "-run",
        "TestEBPF_",
        "./pkg/ebpf/",
        "-v",
        "-count=1",
        "-timeout",
        "300s",
    ], "go argv was %r" % (go[2:],)
    assert out["exit"] == 0, "the happy path must succeed: %r" % out


def test_an_already_mounted_bpffs_is_not_mounted_again(tmp_path):
    """THE NEGATIVE CONTROL on the mount decision. A port that mounted unconditionally would satisfy every positive assertion in this file and would stack a second bpffs over the live one on every CI run."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, fstype=b"bpf_fs\n")
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        names = [line.split("\t")[0] for line in out["calls"]]
        assert names == ["stat", "go"], "%s: mounted anyway (%r)" % (subject.name, names)
        assert "Mounting bpffs" not in out["stderr"]


def test_the_loud_skip_guard_fires_on_an_all_skips_run(tmp_path):
    """THE POSITIVE CONTROL for the reason this script exists. `go test` exits 0 when every test skipped, and without the guard both subjects would report success having verified nothing at all."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, fstype=b"bpf_fs\n", out=ALL_SKIP)
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 1, "%s went green on an all-skips run" % subject.name
        assert ZERO_TESTS_ERROR in out["stdout"], out["stdout"]
        assert "eBPF socket-isolation tests passed" not in out["stderr"]


def test_the_guard_does_not_fire_on_a_real_pass(tmp_path):
    """A gate with only positive controls will happily flag a healthy tree."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, fstype=b"bpf_fs\n")
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 0, "%s failed a run in which both tests passed" % subject.name
        assert "::error::" not in out["stdout"]
        assert "eBPF socket-isolation tests passed" in out["stderr"]


def test_the_em_dash_reaches_stdout_as_the_character(tmp_path):
    """The port spells U+2014 as an escape so no em dash is TYPED into a file under `.ci/rediacc_ci`; the CHARACTER still has to be printed, because the twin prints it and the whole claim is byte-identical output. Asserted on the raw bytes so an escape that never got interpreted would show up."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, fstype=b"bpf_fs\n", out=ALL_SKIP)
    for subject in (TWIN_REL, PORT_REL):
        proc = subprocess.run(
            ["bash" if subject.suffix == ".sh" else "python3", str(root / subject)],
            capture_output=True,
            env={
                "PATH": binder,
                "HOME": str(tmp_path),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(ROOT / ".ci"),
            },
            check=False,
            timeout=120,
        )
        (tmp_path.resolve() / "calls.log").unlink(missing_ok=True)
        assert EM_DASH.encode("utf-8") in proc.stdout, "%s printed no em dash" % subject.name


def test_a_failed_mount_stops_before_go(tmp_path):
    """`set -e` on the mount means the tests never run, and the script exits
    with MOUNT'S status, not 1. Both halves are easy to get wrong in a port and
    neither is visible in stdout."""
    root = _fixture(tmp_path)
    binder = _binder(tmp_path, mount_rc=32, mount_err=b"mount: only root can do that\n")
    for subject in (TWIN_REL, PORT_REL):
        out = _run(subject, root, tmp_path, binder)
        assert out["exit"] == 32, "%s exited %r, not mount's own 32" % (subject.name, out["exit"])
        names = [line.split("\t")[0] for line in out["calls"]]
        assert names == ["stat", "mount"], "%s ran go anyway: %r" % (subject.name, names)


def test_the_mask_does_not_hide_the_message(tmp_path):
    """A CONTROL ON THE CONTROL. `_mask` collapses the `<$0>: line <n>: ` prefix on both sides; if it were greedier it would hide real divergences and every
    case above would pass for the wrong reason."""
    sample = "/a/b/twin.sh: line 20: mount: command not found\nkept: line noise\n"
    masked = _mask(sample, pathlib.Path("/nowhere"), pathlib.Path("/nowhere-either"))
    assert masked == "<shell>: mount: command not found\nkept: line noise\n", masked

    root = _fixture(tmp_path)
    binder = _binder(tmp_path, mount="missing")
    raw = {}
    for subject in (TWIN_REL, PORT_REL):
        proc = subprocess.run(
            ["bash" if subject.suffix == ".sh" else "python3", str(root / subject)],
            capture_output=True,
            text=True,
            env={
                "PATH": binder,
                "HOME": str(tmp_path),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": str(ROOT / ".ci"),
            },
            check=False,
            timeout=120,
        )
        (tmp_path.resolve() / "calls.log").unlink(missing_ok=True)
        raw[subject.name] = proc.stderr
    assert raw[TWIN_REL.name] != raw[PORT_REL.name], (
        "the two prefixes are identical, so the mask is unnecessary and should be deleted"
    )
    for name, text in raw.items():
        assert "mount: command not found" in text, "%s said %r" % (name, text)
