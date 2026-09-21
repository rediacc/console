"""Port of `.ci/scripts/test/gates/test-devbox-probes.sh`, retired in W7 P5.

Controls for `devbox_exec` and the three usability probes in `.ci/lib/devbox.sh`.

WHY THESE MATTER MORE THAN MOST. All three failure modes present IDENTICALLY: a gate that exits 0 having read nothing. An empty bind mount (macOS outside Docker Desktop's sharing list, WSL2 via Desktop integration) auto-creates the directory, so the path EXISTS and the tree is empty. A root exec makes git refuse the worktree, so `git ls-files` returns nothing. A read-only mount
lets reads succeed and writes fail late. In each case the honest-looking answer is a green.

So each probe is asserted in BOTH directions against fixtures built by CONSTRUCTION -- fake `docker` binaries in a temp directory, never the real daemon -- which also keeps this hermetic and runnable where no devbox exists.

THE PROBE BODIES ARE LIFTED FROM THE REAL LIBRARY, unchanged from the twin, so this cannot drift into testing a copy. An extraction that comes back short is a refusal here, not a quieter suite.

THE TWIN USES THE `ok`/`no` TALLY, so the port does too: `gate.ok()` prints the same uncoloured `PASS:` line and, unlike `log_fail`, does not stop the file at the first bad probe. Six probe outcomes and two source properties, eight controls, which is what the twin's `tally_finish` counts.
"""

import re
import stat

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

LIB = paths.from_root(".ci", "lib", "devbox.sh")

# The four functions the twin lifts. Named here so a rename fails LOUDLY at the extraction rather than silently reducing what is exercised.
WANTED = ("devbox_exec", "devbox_mount_ok", "devbox_identity_ok", "devbox_writable_ok")

# A stand-in for the whole library surface the probes touch, so the fixtures decide what "the container" answers.
STUB = """
log_error() { echo "error: $*" >&2; }
log_info()  { echo "info: $*"; }
devbox_docker() { printf '%s' "$FAKE_DOCKER"; }
devbox_container_id() { printf 'cid0'; }
devbox_container_running() { return 0; }
devbox_worktree() { printf '%s' "$WT"; }
devbox_mount_root() { printf '%s' "$WT"; }
"""


def extract(gate) -> str:
    """The four probe bodies, lifted from the live library."""
    if not LIB.is_file():
        gate.log_fail("subject under test is missing: %s" % LIB)
    source = LIB.read_text(encoding="utf-8")
    bodies = []
    for name in WANTED:
        match = re.search(r"^%s\(\) \{.*?^\}" % re.escape(name), source, re.MULTILINE | re.DOTALL)
        if not match:
            gate.log_fail(
                "could not lift %s() out of %s. The probes are extracted rather than "
                "restated so this file cannot drift into testing a copy; a rename must "
                "red here, not quietly shrink what is exercised."
                % (name, paths.relative_to_root(LIB))
            )
        bodies.append(match.group(0))
    return "\n".join(bodies)


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


def probe(gate, tmp_path, name: str, exit_code: int, stdout: str) -> bool:
    """True when the probe ACCEPTED. One bash process per call, no shared state."""
    worktree = tmp_path / "wt"
    (worktree / ".ci" / "cache").mkdir(parents=True, exist_ok=True)
    (worktree / "run.sh").write_text("", encoding="utf-8")
    docker = fake_docker(tmp_path, exit_code, stdout)
    script = STUB + extract(gate) + "\n%s 2>/dev/null\n" % name
    result = harness.run(
        ["bash", "-c", script, "devbox-probe-port"],
        env={"WT": str(worktree), "FAKE_DOCKER": str(docker)},
    )
    return result.rc == 0


def test_mount_probe(gate, tmp_path):
    if probe(gate, tmp_path / "healthy", "devbox_mount_ok", 0, ".git"):
        gate.ok("mount: a container that finds the repo passes")
    else:
        gate.no("mount: a healthy mount was rejected")
    if probe(gate, tmp_path / "empty", "devbox_mount_ok", 1, ""):
        gate.no("CONTROL: an EMPTY mount passed -- the vacuous-green case is undetected")
    else:
        gate.ok("CONTROL: an empty/absent mount is refused")
    gate.tally_finish("devbox mount probe")


def test_identity_probe(gate, tmp_path):
    if probe(gate, tmp_path / "clean", "devbox_identity_ok", 0, ""):
        gate.ok("identity: a clean git status passes")
    else:
        gate.no("identity: a healthy identity was rejected")
    dubious = "fatal: detected dubious ownership in repository at '/x'"
    if probe(gate, tmp_path / "root", "devbox_identity_ok", 0, dubious):
        gate.no("CONTROL: a root exec (dubious ownership) passed")
    else:
        gate.ok("CONTROL: dubious ownership is refused")
    gate.tally_finish("devbox identity probe")


def test_writable_probe(gate, tmp_path):
    if probe(gate, tmp_path / "rw", "devbox_writable_ok", 0, ""):
        gate.ok("writable: a writable mount passes")
    else:
        gate.no("writable: a writable mount was rejected")
    if probe(gate, tmp_path / "ro", "devbox_writable_ok", 1, "touch: Read-only file system"):
        gate.no("CONTROL: a READ-ONLY mount passed")
    else:
        gate.ok("CONTROL: a read-only mount is refused")
    gate.tally_finish("devbox writable probe")


def test_exec_shape(gate):
    source = LIB.read_text(encoding="utf-8")
    # -u vscode BY NAME: a numeric id is only correct where the host's numbering
    # is meaningful, which macOS breaks (501:20, gid 20 = dialout in the image).
    if "-u vscode" in source:
        gate.ok("exec: runs as 'vscode' by name, not a numeric uid")
    else:
        gate.no("exec: does not pin the user by name")
    if "bash -lc" in source:
        gate.ok("exec: uses a LOGIN shell, so /etc/environment supplies go and node on PATH")
    else:
        gate.no("exec: not a login shell; go/node would be missing from PATH")
    gate.tally_finish("devbox exec shape")


def test_the_extraction_covers_every_named_probe(gate):
    """PORT-ONLY ANTI-VACUITY. Every case above runs against extracted text, and an extraction that silently returned less would make each probe pass by not being defined -- `bash` reports command-not-found as 127, which is non-zero, so the REFUSAL cases would all still look correct."""
    body = extract(gate)
    for name in WANTED:
        gate.assert_contains(body, "%s() {" % name, "lifted body is missing %s" % name)
    gate.log_pass(
        "all %d probe bodies lifted from %s (%d lines)"
        % (len(WANTED), paths.relative_to_root(LIB), len(body.splitlines()))
    )
