"""Port of `.ci/scripts/test/gates/test-backfill-commit-resolve.sh`.

Both-ways test for `.ci/scripts/release/resolve-backfill-commit.sh` -- the step
that decides which commit a backfilled release sentinel records.

WHY THIS CLASS NEEDS A GATE. The script had none, and its only caller is a
manually-dispatched workflow (`.github/workflows/backfill-release-sentinel.yml`),
so its failure paths are seen by a human roughly never, and then only by a human
already mid-incident, reading the message to decide what went wrong. A wrong
message there does not fail loudly; it sends the investigation somewhere else.

THE DEFECT THIS PINS. `git merge-base --is-ancestor` returns non-zero for two
unrelated situations: a commit that exists but sits off main, and a SHA that is not
an object in this repository at all. Git's own "Not a valid object name" for the
second went to a `2>/dev/null`, so BOTH produced "commit <sha> is not reachable
from origin/main" -- which reads as a real tag pointing somewhere odd. After the
2026-08-23 history rewrite the second case is the LIKELY one, because any SHA
copied out of an old release note or an R2 sentinel no longer exists.

HOW. Every case runs the REAL script (not a copy) with its working directory set to
a purpose-built synthetic repository, so the git behaviour under test is git's and
not a fake's. The one exception is the anti-swallow control, which needs the
existence probe neutralised and says so.

EXIT CODES ARE PART OF THE CONTRACT. This was a diagnosis change, not a
control-flow change, so every case asserts the exit code as well as the text. A
"clearer message" that also changed which inputs are accepted would be a different
and much worse change.

WHERE THE PORT REIMPLEMENTS THE TWIN. `swallowed_distinction` only. The twin builds
it from `grep -a '::error::'` piped into two `sed` substitutions; the port filters
the same lines and applies the same two substitutions with `re.sub`. Both
normalise every 40-hex run to `<SHA>` before comparing, which is what keeps the
comparison from being trivially true -- the informational echoes name the SHA, so
raw outputs always differ and comparing them would make the whole check vacuous.

NO `xdist_group`. Each case builds its own git repository under pytest's `tmp_path`
and runs the script with that directory as cwd. Nothing in the real tree is read
for state or written at all.
"""

import os
import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-backfill-commit-resolve.sh"

SUT = paths.from_root(".ci", "scripts", "release", "resolve-backfill-commit.sh")

NOT_A_COMMIT = "does not name a commit in this repository"
DETACHED = "refusing to backfill a sentinel for a detached tag"
GHOST_SHA = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

SHA_RE = re.compile(r"[0-9a-f]{40}")


def _git(gate, repo: pathlib.Path, *args: str) -> str:
    result = harness.run(["git", "-C", str(repo), *args])
    if result.rc != 0:
        gate.log_fail(
            "git %s failed in the fixture (rc=%d): %s"
            % (" ".join(args), result.rc, (result.err or result.out).strip())
        )
    return result.out.strip()


def make_repo(gate, base: pathlib.Path) -> pathlib.Path:
    """A repository with, deliberately:

      * `main`, with `origin/main` pointing at its tip
      * `v1.0.0` on main            (reachable)
      * `v9.9.9` on an off-main commit that REALLY EXISTS (detached, not a ghost)

    The detached commit is the whole point: it is the case the existence probe
    could plausibly break by re-classifying it as "does not exist".
    """
    harness.require_tool("git", "install git; this gate drives real git deliberately")
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(SUT))
    repo = base / "repo"
    repo.mkdir(parents=True)
    _git(gate, repo, "init", "-q")
    _git(gate, repo, "config", "user.email", "test@example.invalid")
    _git(gate, repo, "config", "user.name", "test")
    _git(gate, repo, "config", "commit.gpgsign", "false")
    (repo / "f").write_text("base\n", encoding="utf-8")
    _git(gate, repo, "add", "f")
    _git(gate, repo, "commit", "-qm", "base")
    _git(gate, repo, "branch", "-q", "-M", "main")
    _git(gate, repo, "tag", "v1.0.0", "main")
    _git(gate, repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(gate, repo, "checkout", "-q", "-b", "side")
    (repo / "f").write_text("off-main\n", encoding="utf-8")
    _git(gate, repo, "commit", "-qam", "off main")
    _git(gate, repo, "tag", "v9.9.9")
    _git(gate, repo, "checkout", "-q", "main")
    return repo


def detached_sha(gate, repo: pathlib.Path) -> str:
    """The real, existing, off-main commit."""
    return _git(gate, repo, "rev-list", "-n1", "v9.9.9")


class Resolved:
    def __init__(self, rc: int, out: str, step_output: str) -> None:
        self.rc = rc
        self.out = out
        self.step_output = step_output


def run_resolve(repo: pathlib.Path, script: pathlib.Path, **env: str) -> Resolved:
    step_output = repo / "step-output"
    result = harness.run(
        ["bash", str(script)],
        cwd=repo,
        env={"VERSION": "v9.9.9", "GITHUB_OUTPUT": str(step_output), "NO_COLOR": "1", **env},
    )
    return Resolved(
        result.rc,
        result.combined,
        step_output.read_text(encoding="utf-8") if step_output.is_file() else "",
    )


def test_a_nonexistent_sha_is_named_as_nonexistent(gate, tmp_path: pathlib.Path):
    gate.log_test("FIRE: the post-rewrite case, a SHA that is not in the repository at all")
    repo = make_repo(gate, tmp_path)
    got = run_resolve(repo, SUT, INPUT_SHA=GHOST_SHA)
    gate.assert_exit_code(
        1, got.rc, "a SHA that does not exist must still fail, and fail the same way it always did"
    )
    gate.assert_contains(got.out, NOT_A_COMMIT, "it says the SHA does not name a commit here")
    gate.assert_contains(
        got.out,
        "no such object exists here at all",
        "in words that stop the operator hunting for a detached tag",
    )
    gate.assert_contains(
        got.out,
        "2026-08-23 git history rewrite",
        "and names the rewrite that most likely caused it",
    )
    gate.assert_not_contains(
        got.out,
        DETACHED,
        "and must NOT claim a detached tag, which is the misdiagnosis this fix removes",
    )
    gate.assert_eq(got.step_output, "", "nothing is written to the step output on a failure")
    gate.log_pass("FIRE: a non-existent SHA is diagnosed as non-existent, not as a detached tag")


def test_a_real_but_detached_sha_still_says_detached(gate, tmp_path: pathlib.Path):
    gate.log_test("THE CONTROL THAT MATTERS: a commit that genuinely exists and is off main")
    # If the probe were too broad -- a bare `cat-file -e` on the wrong argument, or
    # the check applied to the tag path -- this would flip to the not-an-object
    # message and the fix would have traded one misdiagnosis for another.
    repo = make_repo(gate, tmp_path)
    got = run_resolve(repo, SUT, INPUT_SHA=detached_sha(gate, repo))
    gate.assert_exit_code(1, got.rc, "a detached commit still fails, with the same exit code")
    gate.assert_contains(got.out, DETACHED, "and is still diagnosed as a detached tag")
    gate.assert_contains(
        got.out, "not reachable from origin/main", "naming reachability, which IS the real problem"
    )
    gate.assert_not_contains(
        got.out,
        NOT_A_COMMIT,
        "and must NOT claim the commit is missing -- it is right there, just not on main",
    )
    gate.assert_not_contains(
        got.out, "2026-08-23", "nor blame the history rewrite for an ordinary detached tag"
    )
    gate.log_pass("CONTROL: a real-but-detached SHA keeps the detached diagnosis")


def test_the_tag_path_is_untouched_by_the_probe(gate, tmp_path: pathlib.Path):
    gate.log_test("the probe is scoped to the operator-supplied path")
    repo = make_repo(gate, tmp_path)
    got = run_resolve(repo, SUT)
    gate.assert_exit_code(1, got.rc, "the tag path still rejects a detached tag")
    gate.assert_contains(got.out, "resolved v9.9.9", "having resolved the tag itself")
    gate.assert_contains(got.out, DETACHED, "with the detached diagnosis")
    gate.assert_not_contains(
        got.out, NOT_A_COMMIT, "and no existence complaint about a tag it just resolved"
    )
    gate.log_pass("CONTROL: the tag path is unchanged -- the probe never runs there")


def test_a_non_commit_object_is_rejected(gate, tmp_path: pathlib.Path):
    gate.log_test("THE `^{commit}` PEEL: a tree SHA is a real object and must still be refused")
    # A bare `cat-file -e <sha>` waves a tree through -- it then fails reachability
    # and gets reported as a DETACHED TAG, the same misdiagnosis one layer down.
    repo = make_repo(gate, tmp_path)
    tree_sha = _git(gate, repo, "rev-parse", "main^{tree}")
    got = run_resolve(repo, SUT, INPUT_SHA=tree_sha)
    gate.assert_exit_code(1, got.rc, "a tree SHA is not backfillable and must fail")
    gate.assert_contains(got.out, NOT_A_COMMIT, "and is diagnosed as not naming a commit")
    gate.assert_contains(
        got.out,
        "the object is not a commit",
        "with the message covering this half of the probe, not just the missing-object half",
    )
    gate.assert_not_contains(got.out, DETACHED, "and must NOT be reported as a detached tag")
    # CONTROL: the COMMIT that owns that very tree is accepted, so the rejection
    # above is about the object's TYPE and not about that repository.
    (repo / "step-output").unlink(missing_ok=True)
    commit_sha = _git(gate, repo, "rev-list", "-n1", "main")
    ok = run_resolve(repo, SUT, VERSION="v1.0.0", INPUT_SHA=commit_sha)
    gate.assert_exit_code(0, ok.rc, "CONTROL: the commit holding that tree resolves fine")
    gate.log_pass("a tree SHA is rejected as not-a-commit (control: its own commit is accepted)")


def test_a_reachable_commit_still_succeeds(gate, tmp_path: pathlib.Path):
    gate.log_test("CONTROL for the happy path, both ways in")
    # If this broke, every case above would be asserting that a script which
    # rejects everything is correct.
    repo = make_repo(gate, tmp_path)
    main_sha = _git(gate, repo, "rev-list", "-n1", "main")
    got = run_resolve(repo, SUT, VERSION="v1.0.0")
    gate.assert_exit_code(0, got.rc, "a reachable tag exits 0")
    gate.assert_contains(
        got.step_output, "commit_sha=%s" % main_sha, "and writes the commit to the step output"
    )
    gate.assert_contains(got.out, "commit reachable from origin/main", "and says so")

    (repo / "step-output").unlink(missing_ok=True)
    again = run_resolve(repo, SUT, VERSION="v1.0.0", INPUT_SHA=main_sha)
    gate.assert_exit_code(
        0, again.rc, "a reachable operator-supplied SHA also exits 0 -- the probe passes it through"
    )
    gate.assert_contains(again.step_output, "commit_sha=%s" % main_sha, "and it too is written out")
    gate.log_pass("CONTROL: a reachable commit exits 0 and writes commit_sha, from both paths")


def test_a_missing_tag_is_unchanged(gate, tmp_path: pathlib.Path):
    gate.log_test("the one other failure path in the script must not have moved")
    repo = make_repo(gate, tmp_path)
    got = run_resolve(repo, SUT, VERSION="v4.5.6")
    gate.assert_exit_code(1, got.rc, "an unknown tag still exits 1")
    gate.assert_contains(got.out, "tag v4.5.6 not found in this checkout", "with its own message")
    gate.assert_not_contains(got.out, NOT_A_COMMIT, "and not the new one")
    gate.log_pass("CONTROL: the missing-tag path is untouched")


def swallowed_distinction(ghost_out: str, detached_out: str) -> str:
    """One line describing a swallowed distinction, or "" when the two differ.

    Compares only `::error::` lines: the informational echoes name the SHA, so raw
    outputs always differ and comparing them would make this vacuous.
    """

    def errors(text: str) -> str:
        lines = [ln for ln in text.splitlines() if "::error::" in ln]
        return SHA_RE.sub("<SHA>", "\n".join(lines).replace(GHOST_SHA, "<SHA>"))

    a, b = errors(ghost_out), errors(detached_out)
    if not a or not b:
        return (
            "one of the two failure paths emitted no ::error:: line at all, so there is "
            "nothing for an operator to read"
        )
    if a == b:
        return (
            "a non-existent SHA and a real-but-detached SHA produce IDENTICAL "
            "operator-visible errors, so the distinction is swallowed"
        )
    return ""


def test_the_two_failures_are_distinguishable(gate, tmp_path: pathlib.Path):
    gate.log_test("ANTI-SWALLOW: the two situations must reach the operator as DIFFERENT diagnoses")
    repo = make_repo(gate, tmp_path)
    sha = detached_sha(gate, repo)
    ghost_out = run_resolve(repo, SUT, INPUT_SHA=GHOST_SHA).out
    detached_out = run_resolve(repo, SUT, INPUT_SHA=sha).out
    found = swallowed_distinction(ghost_out, detached_out)
    if found:
        gate.log_fail("resolve-backfill-commit.sh: %s" % found)
    gate.assertions += 1

    # CONTROL: reproduce the PRE-FIX behaviour and require it to be reported.
    #
    # NOT by editing the script. An earlier version of this control cut the probe
    # block out of a copy with a regex, which coupled it to the exact spelling of
    # one `if` header: a harmless refactor made the regex miss and the gate died
    # with a traceback instead of a verdict. Shimming `git` so `cat-file` cannot
    # fail is behaviourally identical to having no probe at all, costs nothing when
    # the script is rewritten, and exercises the REAL script rather than a mutant.
    real_git = harness.require_tool("git", "install git; this control shims the real binary")
    nogit = tmp_path / "nogit"
    nogit.mkdir()
    shim = nogit / "git"
    shim.write_text(
        "#!/bin/bash\n"
        "# Pre-fix simulator: an existence probe that cannot fail. Everything else\n"
        "# is real git, so the reachability check behaves exactly as in production.\n"
        '[[ "${1:-}" == "cat-file" ]] && exit 0\n'
        'exec "%s" "$@"\n' % real_git,
        encoding="utf-8",
    )
    shim.chmod(0o755)
    shimmed = "%s%s%s" % (nogit, os.pathsep, os.environ["PATH"])
    ghost_out = run_resolve(repo, SUT, PATH=shimmed, INPUT_SHA=GHOST_SHA).out
    detached_out = run_resolve(repo, SUT, PATH=shimmed, INPUT_SHA=sha).out
    found = swallowed_distinction(ghost_out, detached_out)
    if not found:
        gate.log_fail(
            "CONTROL FAILED: with the existence probe neutralised -- the pre-fix "
            "behaviour, which reported both failures identically -- nothing was "
            "reported, so this check cannot detect a re-swallow"
        )
    gate.assert_contains(
        found, "IDENTICAL operator-visible errors", "and the control names what it found"
    )
    gate.log_pass(
        "the two failures reach the operator as different diagnoses "
        "(control: the pre-fix script IS reported)"
    )
