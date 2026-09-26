"""`check:ci-agent-session-archival` driven as a process, against a real git tree with the REAL oracle reachable.

Port of `.ci/scripts/test/gates/test-agent-session-archival.sh`, retired 2026-09-23 (Ruling 7: `.ci/` is a Python tree). No `BASH_TWIN` is declared, and that is deliberate rather than forgotten: the bash original was never in a commit, so there is no committed twin left to diff a port against, and `test_twin_parity.py` only compares modules that name one. This follows
`test_gate_bws_rotate.py`, which retired its own uncommitted original the same day for the same reason.

WHAT THIS ADDS TO THE GATE'S OWN `--selftest`. Those controls call `move_refusal()` with six booleans and assert the sentence that comes back; they prove the DECISION and nothing else. Everything between the decision and a moved directory is untested by them: where the six facts come from, the `git mv`, whether the old path is really empty afterwards, and the exit code. So
every case here drives the entry point as a PROCESS against a real git repository it built, and reads the exit code rather than a return value.

WHAT THIS ADDS TO `test_quality_agent_session_archival.py`. That file is the port of the LIBRARY's reasoning: it imports `rediacc_ci.quality.agent_session_archival` and calls `idle_hours`, `classify_due`, `vacuity_reason`, `label_for` and `move_refusal` directly, and nothing in it calls `main`. Neither the CLI as a process, nor the real `git mv`, nor the exit codes, nor the
read-only guarantee of `--check`/`--status`/`--selftest` is covered there. The two files ask different questions and neither implies the other.

THE FIXTURE IS A REAL GIT REPOSITORY because the thing under test is `git mv`: a directory of files would pass a rename that had stopped staging anything, and `git status --porcelain` reporting `R ` is the only evidence the directory's history really follows it.

`.claude/` IS SYMLINKED TO THE REAL ONE RATHER THAN COPIED. The gate derives its liveness oracle from `.claude/hooks/stop/wl_store.py` (`check_agent_session_archival.py:262-277`, `paths.hooks_stop_dir` + `paths.on_sys_path`) and must reach the REAL oracle, not a stale copy that could drift out from under the gate while every case here still passed. That is why this file, alone
in its family, needs a real filesystem and a live oracle rather than a fixture record, and it is what the retired manifest entry declared `reads: ['tree:repo']` for.

NOTHING TRACKED IS EVER MUTATED. Every case builds inside its own pytest `tmp_path` and the subject is pointed at it with `AGENT_SESSION_ARCHIVAL_ROOT`. Other sessions share this worktree.

EVERY REFUSAL CASE HAS ITS MIRROR: the same fixture with the one refused fact changed, and the move asserted to succeed. A rail that cannot be crossed on purpose is indistinguishable from a verb that never moves anything.
"""

import datetime
import pathlib
import shutil
import sys
import time

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_agent_session_archival.py")
CONFIG = paths.from_root(".ci", "config", "agent-session-archival.json")

LABEL = "test-label"

#: The reserved names the move rail reads as a SET. Mirrored from
#: `wl_store.AGENT_RESERVED_DIRS`; the subject reads the real set at run time, and
#: this copy exists so the loop below names each one in its own assertion message.
RESERVED = ("archive", "programs", "worklist", "reggate", "plans", "ledgers", "pr", "legacy")


def _ago(seconds: float) -> str:
    """An ISO8601Z stamp that far in the past, in the shape `wl_store.AGENT_STATE_HEAD_RE` parses out of a `## SESSION` heading."""
    moment = datetime.datetime.fromtimestamp(time.time() - seconds, tz=datetime.UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(repo: pathlib.Path, *args: str) -> str:
    result = harness.run(["git", "-C", str(repo), *args])
    if result.rc != 0:
        raise harness.GateAssertionError(
            "git %s failed in the fixture (rc=%d): %s" % (" ".join(args), result.rc, result.err)
        )
    return result.out


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def seed(tmp_path: pathlib.Path) -> pathlib.Path:
    """A committed fixture tree with one ABANDONED session directory and one LIVE one.

    `deadbeef` is roughly 34 days idle, well past the 24h dead horizon plus the 14-day grace. `live5678` is a minute old. Both are needed in every case: the abandoned one is what a move is allowed to take, and the live one is what keeps the gate's own vacuity floor satisfied once the other has gone.
    """
    root = tmp_path / "tree"
    (root / "agent" / "archive").mkdir(parents=True)
    (root / ".ci" / "config").mkdir(parents=True)
    (root / ".claude").symlink_to(paths.repo_root() / ".claude")
    shutil.copy(CONFIG, root / ".ci" / "config" / "agent-session-archival.json")
    _write(
        root,
        "agent/deadbeef/STATE.md",
        "## SESSION deadbeef %s\n\nAn abandoned session, idle well past the grace period.\n"
        % _ago(3_000_000),
    )
    _write(
        root,
        "agent/live5678/STATE.md",
        "## SESSION live5678 %s\n\nA live session, writing right now.\n" % _ago(60),
    )
    _write(root, "agent/archive/.gitkeep", "")
    _git(root, "init", "-q", ".")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "fixture")
    _git(root, "add", "-A", "--", ".")
    _git(root, "commit", "-qm", "base")
    return root


def _gate(root: pathlib.Path, *argv: str) -> harness.RunResult:
    """The subject, seam-pointed at the fixture."""
    return harness.run(
        [sys.executable, str(GATE), *argv],
        cwd=paths.repo_root(),
        env={"AGENT_SESSION_ARCHIVAL_ROOT": str(root)},
    )


def _listing(root: pathlib.Path) -> str:
    """Every path under `agent/` with its size, sorted. The bash twin's `find -printf '%P %s'`."""
    rows = [
        "%s %d" % (path.relative_to(root / "agent"), path.stat().st_size)
        for path in sorted((root / "agent").rglob("*"))
    ]
    return "\n".join(rows)


# --------------------------------------------------------------------------- Preconditions. A missing tool is an unrun file, never flake.


def test_the_subject_and_its_tools_are_present(gate):
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    if shutil.which("git") is None:
        gate.log_fail(
            "git is absent; every case below builds a repository and would assert nothing"
        )
    gate.log_pass(
        "the subject is present and git is available, so the fixtures below are real repositories"
    )


# --------------------------------------------------------------------------- The move that must work. Everything below is a refusal measured against it.


def test_an_abandoned_directory_moves_and_leaves_nothing_behind(gate, tmp_path):
    root = seed(tmp_path)
    result = _gate(root, "--move", "deadbeef", "--label", LABEL)
    if result.rc != 0:
        gate.log_fail("the abandoned directory was refused", result)
    gate.assert_contains(
        result.combined,
        "agent/deadbeef -> agent/archive/%s/deadbeef" % LABEL,
        "the move did not report the destination it used",
    )
    if (root / "agent/deadbeef").exists():
        gate.log_fail(
            "agent/deadbeef survives the move. A same-named leftover is read by "
            "agent_peer_sections as a brand-new peer, which is the resurrection --move "
            "exists to avoid"
        )
    moved = root / "agent/archive" / LABEL / "deadbeef" / "STATE.md"
    if not moved.is_file():
        gate.log_fail("the content did not arrive at agent/archive/%s/deadbeef/" % LABEL)
    gate.assert_contains(
        moved.read_text(encoding="utf-8"),
        "An abandoned session",
        "the moved STATE.md is not the one that was there",
    )
    gate.assert_contains(
        _git(root, "status", "--porcelain"),
        "R  agent/deadbeef/STATE.md",
        "git did not stage this as a RENAME, so the directory's history does not follow it",
    )
    gate.log_pass(
        "--move renames the whole directory, stages it as a rename, and leaves nothing at the old path"
    )


def test_the_promotion_reminder_is_printed_before_it_acts(gate, tmp_path):
    root = seed(tmp_path)
    result = _gate(root, "--move", "deadbeef", "--label", LABEL)
    if result.rc != 0:
        gate.log_fail("the move failed", result)
    gate.assert_contains(
        result.combined,
        "promote anything in agent/RULES.md",
        "the README's own RULES.md promotion step is not mentioned, so the advisory half of "
        "the archival contract is silent",
    )
    gate.log_pass("--move prints the RULES.md promotion reminder and enforces nothing")


# --------------------------------------------------------------------------- The rails.


def test_a_reserved_name_is_refused_outright(gate, tmp_path):
    root = seed(tmp_path)
    result = _gate(root, "--move", "archive", "--label", LABEL)
    gate.assert_exit(1, result, "a reserved directory name was accepted as a session")
    gate.assert_contains(result.combined, "reserved directory", "the refusal does not say why")
    if not (root / "agent/archive").is_dir():
        gate.log_fail("agent/archive was moved into itself; the reserved-name rail did not hold")
    # MIRROR: the same verb, one fact changed, moves. Without it this case is satisfied by a verb that refuses everything.
    mirror = _gate(root, "--move", "deadbeef", "--label", LABEL)
    if mirror.rc != 0:
        gate.log_fail("the mirror move was refused too, so the rail above proves nothing", mirror)
    gate.log_pass("--move refuses every reserved name and still moves a real session")


def test_every_reserved_name_is_refused_not_just_the_first(gate, tmp_path):
    root = seed(tmp_path)
    for name in RESERVED:
        result = _gate(root, "--move", name, "--label", LABEL)
        gate.assert_exit(1, result, "the reserved name '%s' was accepted" % name)
        gate.assert_contains(
            result.combined, "reserved directory", "'%s' was refused for the wrong reason" % name
        )
    gate.log_pass(
        "all eight reserved names are refused, so the rail reads the SET rather than one literal"
    )


def test_a_live_target_is_refused_without_force_and_moves_with_it(gate, tmp_path):
    root = seed(tmp_path)
    result = _gate(root, "--move", "live5678", "--label", LABEL)
    gate.assert_exit(
        1, result, "a session the oracle still calls LIVE was archived without --force"
    )
    gate.assert_contains(
        result.combined, "still LIVE", "the refusal does not name liveness as the reason"
    )
    if not (root / "agent/live5678/STATE.md").is_file():
        gate.log_fail("the live session's directory moved anyway")
    # MIRROR: --force is the README's own same-day self-archival door and must still open.
    forced = _gate(root, "--move", "live5678", "--label", LABEL, "--force")
    if forced.rc != 0:
        gate.log_fail("--force did not open the door for a live session", forced)
    if (root / "agent/live5678").exists():
        gate.log_fail("--force reported success without moving anything")
    gate.log_pass("--move refuses a live target and --force archives it deliberately")


def test_a_dirty_target_is_refused_because_a_peer_may_be_writing(gate, tmp_path):
    root = seed(tmp_path)
    _write(root, "agent/deadbeef/NOTE.md", "half a note another session is still typing\n")
    result = _gate(root, "--move", "deadbeef", "--label", LABEL)
    gate.assert_exit(
        1, result, "a directory with uncommitted content was moved out from under its writer"
    )
    gate.assert_contains(
        result.combined, "race a live writer", "the refusal does not name the hazard"
    )
    if not (root / "agent/deadbeef/NOTE.md").is_file():
        gate.log_fail("the uncommitted note was moved anyway")
    # MIRROR: commit the note and the SAME directory moves. The rail keys on the tree being dirty, not on the directory.
    _git(root, "add", "-A", "--", "agent/deadbeef")
    _git(root, "commit", "-qm", "note")
    mirror = _gate(root, "--move", "deadbeef", "--label", LABEL)
    if mirror.rc != 0:
        gate.log_fail("a quiet tree was still refused, so the dirty rail is unconditional", mirror)
    if not (root / "agent/archive" / LABEL / "deadbeef" / "NOTE.md").is_file():
        gate.log_fail("the committed note did not travel with the directory")
    gate.log_pass("--move refuses a dirty target and accepts the same one once the tree is quiet")


def test_an_occupied_archive_path_is_refused(gate, tmp_path):
    root = seed(tmp_path)
    occupant = "agent/archive/%s/deadbeef/STATE.md" % LABEL
    _write(
        root,
        occupant,
        "an earlier archive of a different session that happened to share the name\n",
    )
    result = _gate(root, "--move", "deadbeef", "--label", LABEL)
    gate.assert_exit(1, result, "two sessions' directories were merged into one archive path")
    gate.assert_contains(
        result.combined, "already exists", "the refusal does not say the path is taken"
    )
    gate.assert_contains(
        (root / occupant).read_text(encoding="utf-8"),
        "an earlier archive",
        "the occupant was overwritten",
    )
    gate.log_pass("--move refuses to merge into an occupied archive path")


def test_a_missing_directory_is_refused(gate, tmp_path):
    root = seed(tmp_path)
    result = _gate(root, "--move", "nosuchxx", "--label", LABEL)
    gate.assert_exit(1, result, "a session directory that is not there was reported as moved")
    gate.assert_contains(
        result.combined, "does not exist", "the refusal does not say what is missing"
    )
    gate.log_pass("--move refuses a name with no directory behind it")


def test_move_without_a_target_is_a_setup_error_not_a_verdict(gate, tmp_path):
    root = seed(tmp_path)
    result = _gate(root, "--move")
    gate.assert_exit(2, result, "a missing argument was reported as a finding about the tree")
    gate.assert_contains(
        result.combined, "needs a session directory name", "the error does not say what is missing"
    )
    gate.log_pass(
        "--move with no target exits 2, which is a broken invocation rather than a tree with a problem"
    )


# --------------------------------------------------------------------------- The read-only half, which is the hard constraint.


def test_check_and_status_write_nothing_at_all(gate, tmp_path):
    root = seed(tmp_path)
    before = _listing(root)
    _gate(root)
    _gate(root, "--status")
    _gate(root, "--selftest")
    gate.assert_eq(
        _listing(root),
        before,
        "a read-only verb mutated agent/; --check must never write, under any argument",
    )
    gate.assert_eq(
        _git(root, "status", "--porcelain"), "", "a read-only verb left the git index dirty"
    )
    gate.log_pass("--check, --status and --selftest leave agent/ and the index byte-identical")


def test_the_gate_fires_on_the_backlog_and_goes_green_once_it_is_archived(gate, tmp_path):
    root = seed(tmp_path)
    red = _gate(root)
    gate.assert_exit(1, red, "the gate stayed green over a directory 34 days idle; it cannot fire")
    gate.assert_contains(
        red.combined, "agent/deadbeef/ has been idle", "the finding does not name the directory"
    )
    gate.assert_contains(
        red.combined, "--move deadbeef", "the finding does not name the verb that fixes it"
    )
    fix = _gate(root, "--move", "deadbeef", "--label", LABEL)
    if fix.rc != 0:
        gate.log_fail("the fix the finding named failed", fix)
    green = _gate(root)
    gate.assert_exit(0, green, "the gate stayed red after its own remedy was applied")
    gate.assert_contains(
        green.combined, "1 session director(ies)", "the green line does not print what it counted"
    )
    gate.log_pass("the gate reds on the backlog, and the verb it names turns it green")


def test_an_empty_agent_tree_refuses_rather_than_passing(gate, tmp_path):
    root = seed(tmp_path)
    shutil.rmtree(root / "agent/deadbeef")
    shutil.rmtree(root / "agent/live5678")
    result = _gate(root)
    gate.assert_exit(
        77, result, "an enumeration that found NO session directory reported a clean tree"
    )
    gate.assert_contains(
        result.combined, "CANNOT RUN", "the vacuity floor did not announce itself as a refusal"
    )
    gate.log_pass("zero session directories is CANNOT RUN (77), never a green")


def test_a_missing_archive_directory_refuses_rather_than_passing(gate, tmp_path):
    root = seed(tmp_path)
    shutil.rmtree(root / "agent/archive")
    result = _gate(root)
    gate.assert_exit(77, result, "a tree with nowhere to archive to reported a clean bill")
    gate.assert_contains(
        result.combined, "nowhere to archive", "the refusal does not say what is missing"
    )
    gate.log_pass("a missing agent/archive/ is CANNOT RUN (77), never a green")


def test_a_missing_oracle_refuses_rather_than_inventing_one(gate, tmp_path):
    root = seed(tmp_path)
    (root / ".claude").unlink()
    result = _gate(root)
    gate.assert_exit(
        77, result, "the gate reached a verdict with no liveness oracle to reach it with"
    )
    gate.assert_contains(
        result.combined, "cannot import wl_store", "the refusal does not name the missing oracle"
    )
    gate.log_pass(
        "an unreachable wl_store is CANNOT RUN (77), so no verdict is ever invented locally"
    )
