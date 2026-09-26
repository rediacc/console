"""Port of `.ci/scripts/test/gates/test-worktree-devbox-teardown.sh`, retired in W7 P5.

`worktree remove` must tear the devbox down BEFORE it deletes the directory.

THE BUG THIS PINS. The container is found by a label whose VALUE is the worktree's absolute path (`com.rediacc.devbox.worktree`, `.ci/lib/devbox.sh`). `remove_worktree` killed tmux, deleted the directory and deleted the branch, and never stopped the devbox. After the directory is gone, `devbox_worktree()` (`cd "$path" && pwd -P`) yields nothing, the filter becomes
`label=...worktree=`, `docker ps -aq` matches nothing, and teardown reports
"No devbox container for this worktree" and returns 0. The container is orphaned
with nothing able to name it again.

ORDER IS THE INVARIANT, NOT PRESENCE. A teardown that runs AFTER `git worktree remove` looks identical in a call log that only asks "was devbox remove called?", and it leaks every time. So this asserts the SEQUENCE.

HERMETIC: git, docker and run.sh are all shimmed. Nothing here touches a real worktree or a real container.

WHAT THIS CANNOT SEE: it drives the LIFTED `remove_worktree` body, so it does not prove that `prune` reaches the same function, nor that `devbox_remove` actually removes anything. `devbox.sh`'s own gates own that.

WHERE THE PORT REIMPLEMENTS THE TWIN. The lift. The twin extracts the two real
function bodies with `sed -n '/^name() {/,/^}/p'` -- column-0 opener to column-0
closer. `lift()` below is that same rule expressed as a regex, and it is asserted rather than assumed: an empty lift is a LOUD failure naming the function whose shape moved, which is what stops the harness from running an empty file and reporting that no call was made in the wrong order. Running the SHIPPED body, and not a copy of it, is the point of the lift in either language.

NO `xdist_group`. Every case builds its own harness directory under pytest's `tmp_path`, shims PATH for one `bash -c` subprocess only, and writes nothing in the repository.
"""

import os
import pathlib
import re
import stat

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

SUT = paths.from_root("scripts", "dev", "worktree.sh")


def lift(gate, name: str) -> str:
    """The shipped body of `name`, column-0 opener to column-0 closer."""
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(SUT))
    source = SUT.read_text(encoding="utf-8")
    match = re.search(r"^%s\(\) \{.*?^\}" % re.escape(name), source, re.MULTILINE | re.DOTALL)
    if not match:
        gate.log_fail(
            "could not lift %s from %s (its shape changed). The cases below would then "
            "drive an empty harness and report that nothing ran in the wrong order, "
            "which is a green over an absent subject." % (name, paths.relative_to_root(SUT))
        )
    return match.group(0)


def _write_exec(path: pathlib.Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def build_harness(gate, root: pathlib.Path, docker_rc: int, remove_rc: int) -> pathlib.Path:
    """A harness that lifts the two real bodies and drives them against shims."""
    directory = root / "h"
    (directory / "bin").mkdir(parents=True)
    _write_exec(
        directory / "bin" / "docker",
        '#!/bin/bash\n[ "$1" = "info" ] && exit %d\nexit 0\n' % docker_rc,
    )
    _write_exec(
        directory / "bin" / "git",
        '#!/bin/bash\nfor a in "$@"; do\n'
        '  if [ "$a" = "worktree" ]; then echo "git-worktree" >>"$CALLS"; fi\n'
        "done\nexit 0\n",
    )
    _write_exec(directory / "bin" / "tmux", "#!/bin/bash\nexit 1\n")
    _write_exec(
        directory / "run.sh",
        '#!/bin/bash\necho "devbox-remove" >>"$CALLS"\nexit %d\n' % remove_rc,
    )
    (directory / "harness.sh").write_text(
        "\n".join(
            [
                "set -u",
                "log_info() { :; }",
                "log_warn() { :; }",
                'log_error() { echo "ERR: $*" >&2; }',
                "tmux_session_exists() { return 1; }",
                "ROOT_DIR='%s'" % directory,
                lift(gate, "devbox_teardown_available"),
                lift(gate, "remove_worktree"),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return directory


def run_removal(directory: pathlib.Path) -> tuple[int, str]:
    """(exit code, the call log) for one `remove_worktree` against the shims."""
    calls = directory / "calls"
    calls.write_text("", encoding="utf-8")
    result = harness.run(
        [
            "bash",
            "-c",
            "source '%s/harness.sh'; remove_worktree '%s/wt' sess br" % (directory, directory),
        ],
        env={"CALLS": str(calls), "PATH": "%s/bin:%s" % (directory, os.environ["PATH"])},
    )
    return result.rc, calls.read_text(encoding="utf-8")


def test_teardown_runs_before_the_directory_is_deleted(gate, tmp_path: pathlib.Path):
    gate.log_test("devbox teardown must precede git worktree remove")
    directory = build_harness(gate, tmp_path, 0, 0)
    rc, calls = run_removal(directory)
    gate.assert_exit_code(0, rc, "a clean removal should succeed")
    # ANTI-VACUITY: both calls must actually be present, or "order" is trivial.
    gate.assert_contains(calls, "devbox-remove", "devbox teardown never ran at all")
    gate.assert_contains(
        calls, "git-worktree", "git worktree remove never ran; the order test is vacuous"
    )
    first = calls.splitlines()[0] if calls.splitlines() else ""
    if first != "devbox-remove":
        gate.log_fail(
            "ORDER WRONG: %r ran first. After the directory is gone the container's "
            "label value is unrecoverable and it is orphaned forever." % first
        )
    gate.assertions += 1
    gate.log_pass("teardown runs first: %s" % " ".join(calls.split()))


def test_failed_teardown_aborts_the_removal(gate, tmp_path: pathlib.Path):
    gate.log_test("a FAILED teardown must abort, not press on")
    directory = build_harness(gate, tmp_path, 0, 1)
    rc, calls = run_removal(directory)
    if rc == 0:
        gate.log_fail(
            "removal returned 0 despite teardown failing; refusing is recoverable, orphaning is not"
        )
    gate.assertions += 1
    gate.assert_not_contains(
        calls,
        "git-worktree",
        "the worktree was deleted anyway after teardown failed -- this is the orphan",
    )
    gate.log_pass("a failed teardown aborts before the directory is touched")


def test_no_docker_keeps_todays_behaviour(gate, tmp_path: pathlib.Path):
    gate.log_test("a docker-less machine must behave exactly as before")
    # `docker info` failing means no daemon: there is no container to orphan, so removal must proceed rather than start refusing where it always worked.
    directory = build_harness(gate, tmp_path, 1, 1)
    rc, calls = run_removal(directory)
    gate.assert_exit_code(0, rc, "removal must still succeed with no docker daemon")
    gate.assert_not_contains(calls, "devbox-remove", "teardown was attempted with no docker daemon")
    gate.assert_contains(
        calls,
        "git-worktree",
        "the worktree was NOT removed on a docker-less machine; behaviour changed",
    )
    gate.log_pass("no daemon: teardown skipped, removal proceeds")


def test_control_ordering_can_fail(gate, tmp_path: pathlib.Path):
    gate.log_test("CONTROL: move teardown after the delete and the order test MUST go red")
    # BY CONSTRUCTION: a harness whose remove_worktree calls them in the WRONG order. If the assertion cannot see that, it is not testing order.
    directory = tmp_path / "ctl"
    directory.mkdir()
    (directory / "harness.sh").write_text(
        "set -u\n"
        "remove_worktree() {\n"
        '  echo "git-worktree" >>"$CALLS"\n'
        '  echo "devbox-remove" >>"$CALLS"\n'
        "  return 0\n"
        "}\n",
        encoding="utf-8",
    )
    calls = directory / "calls"
    calls.write_text("", encoding="utf-8")
    harness.run(
        ["bash", "-c", "source '%s/harness.sh'; remove_worktree a b c" % directory],
        env={"CALLS": str(calls)},
    )
    lines = calls.read_text(encoding="utf-8").splitlines()
    first = lines[0] if lines else ""
    if first != "git-worktree":
        gate.log_fail(
            "CONTROL DID NOT FIRE: the wrong-order harness did not produce the wrong order "
            "(log: %r)" % lines
        )
    gate.assertions += 1
    gate.log_pass("control fires: the assertion distinguishes the two orderings")


def test_the_lift_really_found_both_shipped_bodies(gate):
    """PORT-ONLY. `lift()` refuses an empty match, but nothing above proves the text it returned is the FUNCTION rather than a one-line stub that happens to match the anchors. A body that no longer calls the devbox teardown at all would satisfy `test_no_docker_keeps_todays_behaviour` on its own."""
    gate.log_test("the lifted bodies are the shipped ones")
    removal = lift(gate, "remove_worktree")
    gate.assert_contains(
        removal, "devbox_teardown_available", "remove_worktree no longer consults the daemon probe"
    )
    gate.assert_contains(
        removal, "worktree", "the lifted remove_worktree never mentions a worktree"
    )
    probe = lift(gate, "devbox_teardown_available")
    gate.assert_contains(
        probe, "docker", "devbox_teardown_available no longer asks docker anything"
    )
    gate.log_pass(
        "both lifted bodies carry the calls the cases above shim (%d and %d bytes)"
        % (len(removal), len(probe))
    )
