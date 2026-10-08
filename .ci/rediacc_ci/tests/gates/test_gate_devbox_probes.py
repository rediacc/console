"""Controls for `devbox_exec` and the three usability probes of `core.devbox`.

Port of `.ci/scripts/test/gates/test-devbox-probes.sh`, retired in W7 P5, which lifted the probe bodies out of `.ci/lib/devbox.sh`. That library is now `core.devbox`, so the probes are driven in process: the class under test is `Devbox` itself, with only the container lookup and the worktree path replaced so the fixtures decide what "the container" answers.

WHY THESE MATTER MORE THAN MOST. All three failure modes present IDENTICALLY: a gate that exits 0 having read nothing. An empty bind mount (macOS outside Docker Desktop's sharing list, WSL2 via Desktop integration) auto-creates the directory, so the repo is "there" and empty; root-owned exec makes git refuse the worktree, so `git ls-files` returns nothing; a read-only mount lets reads succeed and writes fail late. In each case the honest-looking answer is a green.

So each probe is asserted in BOTH directions against fixtures built by CONSTRUCTION -- fake `docker` binaries in a temp directory, never the real daemon -- which also keeps this hermetic and runnable where no devbox exists.

THE TWIN USES THE `ok`/`no` TALLY, so the port does too: `gate.ok()` prints the same uncoloured `PASS:` line and, unlike `log_fail`, does not stop the file at the first bad probe. Six probe outcomes and two source properties, eight controls.
"""

import inspect
import io
import stat

from rediacc_ci import paths
from rediacc_ci.core import devbox

# The four functions the twin lifted. Named here so a rename fails LOUDLY rather than silently reducing what is exercised.
WANTED = ("devbox_exec", "devbox_mount_ok", "devbox_identity_ok", "devbox_writable_ok")


def fake_docker(tmp_path, exit_code: int, stdout: str):
    """A `docker` that records its argv and answers `stdout` with `exit_code`."""
    script = tmp_path / "docker"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%%s' \"$*\" >> %s\n"
        "cat <<'OUT'\n%s\nOUT\nexit %d\n" % (tmp_path / "calls", stdout, exit_code),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def probe(tmp_path, name: str, exit_code: int, stdout: str) -> bool:
    """True when the probe ACCEPTED. One `Devbox` per call, no shared state."""
    worktree = tmp_path / "wt"
    (worktree / ".ci" / "cache").mkdir(parents=True, exist_ok=True)
    (worktree / "run.sh").write_text("", encoding="utf-8")
    docker = fake_docker(tmp_path, exit_code, stdout)

    class Box(devbox.Devbox):
        def container_id(self, *_argv: str) -> int:
            self.write("cid0\n")
            return 0

        def container_running(self, *_argv: str) -> int:
            return 0

        def worktree_path(self) -> str:
            return str(worktree)

        def mount_root(self, *_argv: str) -> int:
            self.write(str(worktree))
            return 0

    box = Box(
        env={"PATH": "/usr/bin:/bin", devbox.DOCKER_MEMO: str(docker)},
        cwd=str(worktree),
        repo_root=str(paths.repo_root()),
        stdout=io.BytesIO(),
        stderr=io.BytesIO(),
    )
    return box.invoke(name) == 0


def test_mount_probe(gate, tmp_path):
    if probe(tmp_path / "healthy", "devbox_mount_ok", 0, ".git"):
        gate.ok("mount: a container that finds the repo passes")
    else:
        gate.no("mount: a healthy mount was rejected")
    if probe(tmp_path / "empty", "devbox_mount_ok", 1, ""):
        gate.no("CONTROL: an EMPTY mount passed -- the vacuous-green case is undetected")
    else:
        gate.ok("CONTROL: an empty/absent mount is refused")
    gate.tally_finish("devbox mount probe")


def test_identity_probe(gate, tmp_path):
    if probe(tmp_path / "clean", "devbox_identity_ok", 0, ""):
        gate.ok("identity: a clean git status passes")
    else:
        gate.no("identity: a healthy identity was rejected")
    dubious = "fatal: detected dubious ownership in repository at '/x'"
    if probe(tmp_path / "root", "devbox_identity_ok", 0, dubious):
        gate.no("CONTROL: a root exec (dubious ownership) passed")
    else:
        gate.ok("CONTROL: dubious ownership is refused")
    gate.tally_finish("devbox identity probe")


def test_writable_probe(gate, tmp_path):
    if probe(tmp_path / "rw", "devbox_writable_ok", 0, ""):
        gate.ok("writable: a writable mount passes")
    else:
        gate.no("writable: a writable mount was rejected")
    if probe(tmp_path / "ro", "devbox_writable_ok", 1, "touch: Read-only file system"):
        gate.no("CONTROL: a READ-ONLY mount passed")
    else:
        gate.ok("CONTROL: a read-only mount is refused")
    gate.tally_finish("devbox writable probe")


def test_exec_shape(gate):
    source = inspect.getsource(devbox.Devbox.exec)
    # -u vscode BY NAME: a numeric id is only correct where the host's numbering
    # is meaningful, which macOS breaks (501:20, gid 20 = dialout in the image).
    if '"-u", "vscode"' in source:
        gate.ok("exec: runs as 'vscode' by name, not a numeric uid")
    else:
        gate.no("exec: does not pin the user by name")
    if '"bash", "-lc"' in source:
        gate.ok("exec: uses a LOGIN shell, so /etc/environment supplies go and node on PATH")
    else:
        gate.no("exec: not a login shell; go/node would be missing from PATH")
    gate.tally_finish("devbox exec shape")


def test_the_probes_are_all_defined(gate):
    """ANTI-VACUITY. Every case above drives a method by its bash name, and a name missing from `BASH_NAMES` would make `invoke` raise rather than refuse, so each named probe must resolve to a callable."""
    for name in WANTED:
        gate.assert_contains(
            list(devbox.BASH_NAMES), name, "%s is not a function of core.devbox" % name
        )
        method = getattr(devbox.Devbox, devbox.BASH_NAMES[name], None)
        gate.assert_contains([callable(method)], True, "%s has no callable on Devbox" % name)
    gate.log_pass("all %d probes resolve to a Devbox method" % len(WANTED))
