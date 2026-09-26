"""`rediacc_ci.ops.derive_shadow_pass_list`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `scripts/ops/derive-shadow-pass-list.sh` and the port over the same throwaway root, one after the other, and compared exit code, stdout, stderr and the fake `gh`'s call log. The K=5 ledger `.ci/shadow/w9p3-derive-shadow-pass-list.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been deleted and every
case compares against `goldens/derive-shadow-pass-list/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

THE TWO STREAMS CARRY DIFFERENT HALVES OF THE ANSWER and both are compared. stdout is the deletable list, which is the artifact an operator acts on; stderr is every count, every SKIP line and the refusal, which is the reasoning that makes the list trustworthy. A port that printed the right list for the wrong reason would pass a stdout-only comparison, and a port that dropped a
SKIP would pass one on stderr counts alone.

THE CALL LOG IS THE THIRD SECTION, and it exists because the whole program is a shape of `gh` queries. `--limit` carrying the wrong value, or `run view --json jobs` being skipped so that a cancelled run's verdicts are trusted, changes nothing on either stream in the cases where the fake answers the same way regardless.

THE FAKE `gh` ANSWERS FROM FILES, never from a network. It logs its argv and then serves `gh/runs-<workflow>`, `gh/jobs-<id>`, `gh/log-<id>`, `gh/org.json` and `gh/repo.json` out of the fixture, exiting non-zero where the fixture says the query could not be answered. `test_the_scratch_path_cannot_reach_a_real_gh` asserts the PATH replacement holds in both directions, because a
real `gh` here would query the real rediacc org.

THREE THINGS ARE NORMALIZED. `$0` and bash's location prefix, for the reason `test_ops_build_server.py` records at length: a port must not forge a line number. `the-raw-twin-location-prefix` holds the twin's unmasked bytes for one such case so the mask can be shown to hide a prefix that was really there. The fixture root is the second, through `frozen.mask_root`.

THE THIRD IS THE TRACEBACK FRAMES, and only the frames. The twin ran its Python half as a `python3 - <<PY` heredoc, so an unreachable API produced a traceback of one frame reading `File "<stdin>", line 7`; the same failure in a module produces four frames naming real functions. The frames describe where the program lives, the terminating line describes what happened, and the
terminating line is compared verbatim. `test_the_traceback_mask_keeps_the_line_that_matters` is the control: both sides must still end on the same `CalledProcessError` naming the same `gh api` argv, and the mask must really have removed something.

THE EMPTY-GLOB CASE IS THE ONE WORTH READING. With no `.github/workflows/` at all, bash hands grep the LITERAL pattern, grep reports a missing file, and `xargs -n1` over empty input still runs `basename` once with no operand, which prints its own usage. Three programs' diagnostics, none of them the script's, all on stderr, and the port reproduces them by running the same
pipeline rather than by reimplementing it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()

SLUG = "derive-shadow-pass-list"

TWIN_REL = "scripts/ops/derive-shadow-pass-list.sh"
PORT_REL = ".ci/rediacc_ci/ops/derive_shadow_pass_list.py"

VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/ops/__init__.py",
)

# `grep`, `xargs` and `basename` are the pipeline both sides run; `sort`, `awk`, `wc`, `mktemp`, `rm` and `cat` are the twin's own staging; `python3` is the twin's heredoc interpreter. Anything not listed is ABSENT from both sides.
PATH_MINIMUM = (
    "grep",
    "xargs",
    "basename",
    "sort",
    "awk",
    "wc",
    "mktemp",
    "rm",
    "cat",
    "dirname",
    "python3",
)

NEEDLE = "Compare shadow secrets against GitHub"

FAKE_GH = """#!/bin/bash
printf 'CALL gh' >>"$FAKE_CALL_LOG"
for a in "$@"; do printf '\\t%s' "$a" >>"$FAKE_CALL_LOG"; done
printf '\\n' >>"$FAKE_CALL_LOG"
GH="$FIXTURE_GH"
if [[ "$1" == "run" && "$2" == "list" ]]; then
    wf="${3#--workflow=}"
    [[ -f "$GH/runs-$wf" ]] && cat "$GH/runs-$wf"
    exit 0
fi
if [[ "$1" == "run" && "$2" == "view" && "$4" == "--json" ]]; then
    if [[ -f "$GH/jobs-$3" ]]; then cat "$GH/jobs-$3"; exit 0; fi
    echo "no such run" >&2
    exit 1
fi
if [[ "$1" == "run" && "$2" == "view" && "$4" == "--log" ]]; then
    [[ -f "$GH/log-$3" ]] && cat "$GH/log-$3"
    exit 0
fi
if [[ "$1" == "api" ]]; then
    case "$2" in
        orgs/*) f="$GH/org.json" ;;
        *) f="$GH/repo.json" ;;
    esac
    if [[ -f "$f" ]]; then cat "$f"; exit 0; fi
    echo "gh: could not reach the api" >&2
    exit 1
fi
exit 0
"""

SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))
LOCATION_RE = re.compile(r"^<SELF>: line \d+: ", re.MULTILINE)

# The FRAMES of a traceback, never its terminating line. Frame and caret lines all open with two spaces; the exception line opens at column zero.
TRACEBACK_RE = re.compile(r"^(Traceback \(most recent call last\):\n)(?:  .*\n)+", re.MULTILINE)

CALLS_MARKER = "--- calls ---\n"

WORKFLOW_WITH_COMPARE = (
    """name: shadow-a
jobs:
  compare:
    steps:
      - name: %s
        env:
          GH_ALPHA: ${{ secrets.ALPHA }}
          GH_BETA: ${{ secrets.BETA_RENAMED }}
          GH_GAMMA: ${{ secrets.GAMMA }}
          GH_DELTA: ${{ secrets.DELTA }}
"""
    % NEEDLE
)

WORKFLOW_SECOND_BINDING = """name: shadow-b
jobs:
  other:
    steps:
      - env:
          GH_GAMMA: ${{ secrets.GAMMA_OTHER }}
"""

WORKFLOW_WITHOUT_COMPARE = """name: plain
jobs:
  build:
    steps:
      - run: echo nothing to compare here
"""

LOG_ALL_MATCH = (
    "2026-01-01T00:00:00Z compare\tshadow ALPHA match\n"
    "2026-01-01T00:00:01Z compare\tshadow BETA match\n"
    "2026-01-01T00:00:02Z compare\tshadow GAMMA match\n"
    "2026-01-01T00:00:03Z compare\tshadow DELTA match\n"
)
LOG_WITH_MISMATCH = "2026-01-01T00:00:00Z compare\tshadow ALPHA MISMATCH\nshadow BETA match\n"
LOG_WITH_EMPTY = "shadow ALPHA EMPTY\nshadow DELTA match\n"

ORG_JSON = '["ALPHA", "BETA_RENAMED", "GAMMA", "GAMMA_OTHER"]\n'
REPO_JSON = '["GAMMA"]\n'


def fixture(
    tmp_path: pathlib.Path,
    *,
    port_source: str | None = None,
    workflows: dict[str, str] | None = None,
    gh_files: dict[str, str] | None = None,
) -> pathlib.Path:
    """A throwaway console root holding the port, a workflow set and the fake's answers."""
    root = tmp_path / "repo"
    for rel in (PORT_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    for rel in VENDORED:
        shutil.copy2(ROOT / rel, root / rel)
    if port_source is None:
        shutil.copy2(ROOT / PORT_REL, root / PORT_REL)
    else:
        (root / PORT_REL).write_text(port_source, encoding="utf-8")

    if workflows is not None:
        wfdir = root / ".github" / "workflows"
        wfdir.mkdir(parents=True, exist_ok=True)
        for name, body in workflows.items():
            (wfdir / name).write_text(body, encoding="utf-8")

    gh = root / "gh"
    gh.mkdir(parents=True, exist_ok=True)
    for name, body in (gh_files or {}).items():
        (gh / name).write_text(body, encoding="utf-8")
    return root


def scratch_bin(root: pathlib.Path, *, drop_gh: bool = False) -> str:
    """The ONLY directory on PATH for either side."""
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for name in PATH_MINIMUM:
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        link = stub / name
        if not link.exists():
            link.symlink_to(real)
    fake = stub / "gh"
    if drop_gh:
        if fake.exists():
            fake.unlink()
    else:
        fake.write_text(FAKE_GH, encoding="utf-8")
        fake.chmod(0o755)
    return str(stub)


def drive(
    root: pathlib.Path,
    argv: list[str],
    *,
    drop_gh: bool = False,
    tag: str = "new",
    **extra: str,
) -> tuple[int, str, str, str]:
    """One side, once, under a replaced PATH and a fresh call log."""
    call_log = root / ("%s-calls.log" % tag)
    call_log.write_text("", encoding="utf-8")
    env = {
        # REPLACED, never prepended: a real `gh` here would query the real org.
        "PATH": scratch_bin(root, drop_gh=drop_gh),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        "FIXTURE_GH": str(root / "gh"),
        "BRANCH": "shadow-branch",
        "TMPDIR": str(root / "tmp"),
    }
    (root / "tmp").mkdir(parents=True, exist_ok=True)
    env.update(extra)
    proc = subprocess.run(
        argv,
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc.returncode, proc.stdout, proc.stderr, call_log.read_text(encoding="utf-8")


FULL_WORKFLOWS = {
    "shadow-a.yml": WORKFLOW_WITH_COMPARE,
    "plain.yml": WORKFLOW_WITHOUT_COMPARE,
}

CASES = (
    "a-clean-pass-over-four-names",
    "an-unknown-argument",
    "branch-flag-with-no-value",
    "gh-is-absent-from-the-path",
    "no-workflow-carries-a-compare",
    "no-workflows-directory-at-all",
    "a-run-with-zero-successful-jobs-is-skipped",
    "a-mismatch-disqualifies-its-name",
    "an-empty-verdict-disqualifies-its-name",
    "a-repo-level-twin-shadows-the-org-copy",
    "a-shadow-name-with-two-github-bindings",
    "a-name-that-is-not-an-org-secret",
    "runs-and-branch-are-passed-through",
    "the-api-cannot-be-reached",
)

RAW_CASE = "the-raw-twin-location-prefix"

EXPECTED_EXIT = {
    "a-clean-pass-over-four-names": 0,
    "an-unknown-argument": 2,
    "branch-flag-with-no-value": 1,
    "gh-is-absent-from-the-path": 2,
    "no-workflow-carries-a-compare": 1,
    "no-workflows-directory-at-all": 1,
    "a-run-with-zero-successful-jobs-is-skipped": 1,
    "a-mismatch-disqualifies-its-name": 0,
    "an-empty-verdict-disqualifies-its-name": 0,
    "a-repo-level-twin-shadows-the-org-copy": 0,
    "a-shadow-name-with-two-github-bindings": 0,
    "a-name-that-is-not-an-org-secret": 0,
    "runs-and-branch-are-passed-through": 0,
    "the-api-cannot-be-reached": 1,
}


def build(tmp_path: pathlib.Path, name: str, *, port_source: str | None = None):
    """The fixture tree, the argv tail and the run keywords for one recorded case."""
    args: list[str] = []
    kw: dict[str, object] = {}
    workflows: dict[str, str] | None = dict(FULL_WORKFLOWS)
    gh_files = {
        "runs-shadow-a.yml": "101\n",
        "jobs-101": "6\n",
        "log-101": LOG_ALL_MATCH,
        "org.json": ORG_JSON,
        "repo.json": REPO_JSON,
    }

    if name == "an-unknown-argument":
        args = ["--nope"]
    elif name == "branch-flag-with-no-value":
        args = ["--branch"]
    elif name == "gh-is-absent-from-the-path":
        kw["drop_gh"] = True
    elif name == "no-workflow-carries-a-compare":
        workflows = {"plain.yml": WORKFLOW_WITHOUT_COMPARE}
    elif name == "no-workflows-directory-at-all":
        workflows = None
    elif name == "a-run-with-zero-successful-jobs-is-skipped":
        gh_files["jobs-101"] = "0\n"
    elif name == "a-mismatch-disqualifies-its-name":
        gh_files["log-101"] = LOG_WITH_MISMATCH
    elif name == "an-empty-verdict-disqualifies-its-name":
        gh_files["log-101"] = LOG_WITH_EMPTY
    elif name == "a-repo-level-twin-shadows-the-org-copy":
        gh_files["log-101"] = "shadow GAMMA match\nshadow ALPHA match\n"
    elif name == "a-shadow-name-with-two-github-bindings":
        workflows = dict(FULL_WORKFLOWS)
        workflows["shadow-b.yml"] = WORKFLOW_SECOND_BINDING
        gh_files["log-101"] = "shadow GAMMA match\nshadow ALPHA match\n"
    elif name == "a-name-that-is-not-an-org-secret":
        gh_files["org.json"] = '["ALPHA"]\n'
    elif name == "runs-and-branch-are-passed-through":
        args = ["--branch", "release-x", "--runs", "2"]
        gh_files["runs-shadow-a.yml"] = "101\n102\n"
        gh_files["jobs-102"] = "1\n"
        gh_files["log-102"] = "shadow DELTA match\n"
    elif name == "the-api-cannot-be-reached":
        del gh_files["org.json"]

    root = fixture(tmp_path, port_source=port_source, workflows=workflows, gh_files=gh_files)
    return root, args, kw


def mask(text: str, root: pathlib.Path) -> str:
    """`$0`, bash's location prefix, a traceback's frames, and the fixture root. Nothing else."""
    text = LOCATION_RE.sub("", SELF_RE.sub("<SELF>", text))
    return frozen.mask_root(TRACEBACK_RE.sub(r"\1<frames>\n", text), root)


def render(returncode: int, stdout: str, stderr: str, calls: str) -> str:
    return "%s%s%s" % (frozen.render(returncode, stdout, stderr), CALLS_MARKER, calls)


def split_golden(text: str) -> tuple[int, str, str, str]:
    exit_line, rest = text.split("\n", 1)
    body, calls = rest.split(CALLS_MARKER, 1)
    stdout, stderr = body.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, calls


def run_port(root: pathlib.Path, args: list[str], **kw) -> tuple[int, str, str, str]:
    return drive(root, [sys.executable, str(root / PORT_REL), *args], **kw)


def compare(root: pathlib.Path, name: str, args: list[str], **kw):
    want = split_golden(frozen.read(SLUG, name))
    returncode, stdout, stderr, calls = run_port(root, args, **kw)
    assert returncode == want[0], "%s: the twin exited %d, the port %d\n%s" % (
        name,
        want[0],
        returncode,
        stderr,
    )
    assert mask(stdout, root) == want[1], "%s: stdout diverged from the recorded bytes" % name
    assert mask(stderr, root) == want[2], "%s: stderr diverged from the recorded bytes" % name
    assert mask(calls, root) == want[3], "%s: the gh call log diverged" % name
    return returncode, stdout, stderr, calls


# ---------------------------------------------------------------------------
# The control on the control
# ---------------------------------------------------------------------------


def test_the_scratch_path_cannot_reach_a_real_gh(tmp_path: pathlib.Path) -> None:
    """A real `gh` on this PATH would query the real rediacc org and print real secret names, so the fixture REPLACES the PATH and this asserts the replacement holds in both directions."""
    root = fixture(tmp_path)
    sealed = scratch_bin(root)
    assert shutil.which("gh", path=sealed) == str(root / "fixture-bin" / "gh")
    dropped = scratch_bin(root, drop_gh=True)
    assert shutil.which("gh", path=dropped) is None, "a real gh is reachable from the fixture"
    assert shutil.which("git", path=dropped) is None


# ---------------------------------------------------------------------------
# Every recorded case
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    root, args, kw = build(tmp_path, name)
    returncode = compare(root, name, args, **kw)[0]
    assert returncode == EXPECTED_EXIT[name], "the recorded verdict moved"


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, {*CASES, RAW_CASE})


def test_the_green_case_is_not_vacuously_equal() -> None:
    """Two implementations that both print nothing agree about nothing, so the recorded green case must carry a real derivation: a deletable list on stdout and every count on stderr."""
    _, stdout, stderr, calls = split_golden(frozen.read(SLUG, "a-clean-pass-over-four-names"))
    assert stdout == (
        "gh secret delete ALPHA --org rediacc\ngh secret delete BETA_RENAMED --org rediacc\n"
    )
    assert "# 1 shadow-carrying workflow(s)\n" in stderr
    assert "# verdicts seen: 4, clean-pass names: 4, names with a non-match: 0\n" in stderr
    # FOUR names passed the compare and TWO are deletable, which is the point: a clean compare is necessary and not sufficient.
    assert "# SKIP DELTA: DELTA is not an org secret\n" in stderr
    assert "# 2 deletable, 2 skipped\n" in stderr
    assert "CALL gh\trun\tlist\t--workflow=shadow-a.yml" in calls


def test_the_rename_is_followed_rather_than_the_shadow_name_deleted() -> None:
    """`GH_BETA: ${{ secrets.BETA_RENAMED }}`. Deleting by the shadow name would delete a secret nothing compared, or nothing at all."""
    stdout = split_golden(frozen.read(SLUG, "a-clean-pass-over-four-names"))[1]
    assert "gh secret delete BETA_RENAMED --org rediacc\n" in stdout
    assert "gh secret delete BETA --org rediacc\n" not in stdout


def test_a_repo_level_twin_is_refused_rather_than_deleted() -> None:
    """The CLAUDE_CODE_OAUTH_TOKEN shape: a repo-level secret shadows the org one, so the compare tested the repo copy and the org copy has never been compared."""
    _, stdout, stderr, _ = split_golden(frozen.read(SLUG, "a-repo-level-twin-shadows-the-org-copy"))
    assert "GAMMA" not in stdout
    assert "# SKIP GAMMA: GAMMA also exists REPO-level" in stderr


def test_a_non_match_anywhere_disqualifies_the_name() -> None:
    """One MISMATCH or one EMPTY is enough, and neither may read as a pass."""
    for case, name in (
        ("a-mismatch-disqualifies-its-name", "ALPHA"),
        ("an-empty-verdict-disqualifies-its-name", "ALPHA"),
    ):
        stdout = split_golden(frozen.read(SLUG, case))[1]
        assert "gh secret delete %s --org rediacc\n" % name not in stdout


def test_a_run_whose_jobs_all_failed_contributes_nothing() -> None:
    """A job whose own conclusion is not success did not report, and the absence of a verdict must never read as a pass. The log is never even fetched."""
    rc, stdout, stderr, calls = split_golden(
        frozen.read(SLUG, "a-run-with-zero-successful-jobs-is-skipped")
    )
    assert rc == 1
    assert stdout == ""
    assert "REFUSING: no passing compare found on shadow-branch." in stderr
    assert "--log" not in calls, "the log was fetched for a run with no successful job"


def test_the_flags_reach_gh_verbatim() -> None:
    """`--limit` carrying the wrong value changes neither stream when the fake answers the same way regardless, so the call log is the only section that can see it."""
    calls = split_golden(frozen.read(SLUG, "runs-and-branch-are-passed-through"))[3]
    listing = next(c for c in calls.splitlines() if "\trun\tlist\t" in c)
    fields = listing.split("\t")
    assert fields[fields.index("--branch") + 1] == "release-x"
    assert fields[fields.index("--limit") + 1] == "2"


def test_three_other_programs_diagnostics_survive_the_empty_glob() -> None:
    """With no `.github/workflows/` at all, bash hands grep the LITERAL pattern and `xargs -n1` still runs `basename` once with no operand. Neither diagnostic is the script's own, and both are part of what an operator sees."""
    rc, _, stderr, _ = split_golden(frozen.read(SLUG, "no-workflows-directory-at-all"))
    assert rc == 1
    assert ".github/workflows/*.yml" in stderr
    assert "# 0 shadow-carrying workflow(s)\n" in stderr


def test_an_unreachable_api_is_a_crash_rather_than_a_short_list() -> None:
    """A silently short org list would reclassify a deletable secret as "not an org secret", which is the wrong direction to be wrong in."""
    rc, stdout, stderr, _ = split_golden(frozen.read(SLUG, "the-api-cannot-be-reached"))
    assert rc == 1
    assert stdout == ""
    assert stderr.endswith(
        "Traceback (most recent call last):\n<frames>\n"
        "subprocess.CalledProcessError: Command '['gh', 'api', "
        "'orgs/rediacc/actions/secrets', '--paginate', '-q', '[.secrets[].name]']' "
        "returned non-zero exit status 1.\n"
    )


def test_the_location_prefix_mask_hides_a_prefix_that_was_really_there() -> None:
    """THE CONTROL ON `LOCATION_RE`. Every compared golden has the prefix already stripped, so on its own the mask is indistinguishable from a mask that matches nothing."""
    raw = split_golden(frozen.read(SLUG, RAW_CASE))
    stripped = split_golden(frozen.read(SLUG, "branch-flag-with-no-value"))
    assert raw[2].startswith("<SELF>: line "), "the twin printed no location prefix: %r" % raw[2]
    assert LOCATION_RE.sub("", raw[2]) == stripped[2]
    assert raw[2] != stripped[2], "the mask matched nothing, so it is proving nothing"
    assert raw[0] == stripped[0] == 1


def test_the_traceback_mask_keeps_the_line_that_matters(tmp_path: pathlib.Path) -> None:
    """CONTROL for `TRACEBACK_RE`: it must really remove frames from the port's own output, and must leave the terminating exception line untouched."""
    root, args, kw = build(tmp_path, "the-api-cannot-be-reached")
    _, _, stderr, _ = run_port(root, args, **kw)
    assert "  File " in stderr, "the port printed no frames, so the mask is proving nothing"
    masked = mask(stderr, root)
    assert "  File " not in masked
    assert masked.count("<frames>") == 1
    assert masked.endswith("returned non-zero exit status 1.\n")


def test_the_recorded_bytes_are_not_a_hash_of_themselves() -> None:
    """A last anti-vacuity guard on the corpus: no two goldens may be byte-identical, which is what a recorder that wrote one case fifteen times would produce."""
    seen: dict[str, str] = {}
    for name in (*CASES, RAW_CASE):
        digest = hashlib.sha256(frozen.read(SLUG, name).encode("utf-8")).hexdigest()
        assert digest not in seen, "%s and %s recorded identical bytes" % (name, seen[digest])
        seen[digest] = name


# ---------------------------------------------------------------------------
# The controls: these goldens can actually fail
# ---------------------------------------------------------------------------


def test_a_planted_run_conclusion_filter_is_caught(tmp_path: pathlib.Path) -> None:
    """Trust a run whose jobs all failed. The twin's own comment says this exact relaxation must never happen, and only one case can see it."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    anchor = '            if successful_job_count(run_id) in ("", "0"):\n                continue\n'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    planted = source.replace(anchor, "")
    root, args, kw = build(
        tmp_path, "a-run-with-zero-successful-jobs-is-skipped", port_source=planted
    )
    with pytest.raises(AssertionError):
        compare(root, "a-run-with-zero-successful-jobs-is-skipped", args, **kw)
    clean = build(tmp_path / "clean", "a-run-with-zero-successful-jobs-is-skipped")
    compare(clean[0], "a-run-with-zero-successful-jobs-is-skipped", clean[1], **clean[2])
    assert (ROOT / PORT_REL).read_text(encoding="utf-8") == source


def test_a_planted_repo_level_relaxation_is_caught(tmp_path: pathlib.Path) -> None:
    """Delete the repo-level guard, which is the arm a reader would call redundant because the name is in the org list anyway."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    anchor = "        if name in repo:\n"
    assert source.count(anchor) == 1, "the plant's anchor moved"
    planted = source.replace(anchor, "        if False:\n")
    root, args, kw = build(tmp_path, "a-repo-level-twin-shadows-the-org-copy", port_source=planted)
    with pytest.raises(AssertionError):
        compare(root, "a-repo-level-twin-shadows-the-org-copy", args, **kw)
    clean = build(tmp_path / "clean", "a-repo-level-twin-shadows-the-org-copy")
    compare(clean[0], "a-repo-level-twin-shadows-the-org-copy", clean[1], **clean[2])
    assert (ROOT / PORT_REL).read_text(encoding="utf-8") == source


def test_the_fixture_org_list_really_is_json() -> None:
    """A guard on the fixture rather than on the subject: a malformed `org.json` would make every case take the unreachable-api path and agree trivially."""
    assert json.loads(ORG_JSON) == ["ALPHA", "BETA_RENAMED", "GAMMA", "GAMMA_OTHER"]
    assert json.loads(REPO_JSON) == ["GAMMA"]
