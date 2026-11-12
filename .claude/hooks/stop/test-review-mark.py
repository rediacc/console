#!/usr/bin/env python3
"""Controls for `wl_review.mark(..., "fixed", [<sha>])`, the path `worklist.py --review-mark <me> <id> fixed <sha>` runs.

    python3 .claude/hooks/stop/test-review-mark.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py (glob over test-*.py under .claude/hooks/stop/).

THE DEFECT. On 2026-11-12 seven `--review-mark ... fixed commit:edd459ffbc` runs were refused with "does not resolve to a commit in console" although the commit existed: `commit:<sha>` is the `--tick` evidence form and mark() handed it to rev-parse whole. The prefix is now stripped. Each control runs the real mark() against a throwaway git repository holding a reviewed commit, a fix commit touching the anchored file, and one review record, so a mark() that stops stripping the prefix, or starts admitting what it must refuse, turns a control red.
"""

import atexit
import pathlib
import shutil
import subprocess
import sys
import tempfile

import wl_review as R

_SCRATCH = pathlib.Path(tempfile.mkdtemp(prefix="review-mark-"))
atexit.register(shutil.rmtree, _SCRATCH, True)


class Tally:
    count = 0
    fails = 0


def control(label, got, want):
    Tally.count += 1
    if got != want:
        Tally.fails += 1
        print("FAIL  %s: got %r, wanted %r" % (label, got, want), file=sys.stderr)


BRANCH = "0101-1"
CLAIM = "the fixture line is wrong and a later commit corrects it."
ME = "testmark"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def fixture(name):
    """(repo, reviewed sha, fix sha): the fix touches the file the finding anchors on."""
    repo = _SCRATCH / name
    repo.mkdir()
    git(repo, "init", "-q", "-b", BRANCH)
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "fixture")
    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-q", "-m", "base")
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "reviewed")
    reviewed = git(repo, "rev-parse", "HEAD")
    record = repo / "agent" / "reviews" / BRANCH / ("%s.md" % reviewed)
    record.parent.mkdir(parents=True)
    record.write_text(
        "# Review %s: reviewed\n\n"
        "Commit: %s\nRepo: console\nBranch: %s\nParent: %s\nPatch-Id: %s\n"
        "Reviewed-At: 2026-11-12T00:00:00Z\nModel: fixture\nCost: (none)\n"
        "Diff: 1 bytes, 1 files, truncated: no\nUnreviewed: (none)\nVerdict: findings\n"
        "Attempt: 1\nLabels: bump=none kind=ci why=fixture.\nDropped: 0\nBody-Sig: %s\n\n## Findings\n\n"
        "### %s.1 [medium] a.txt:1\nAnchor: in-diff\n"
        "Claim: %s\n"
        "Class: other\nResolution: open\n"
        % (
            reviewed[:8],
            reviewed,
            BRANCH,
            git(repo, "rev-parse", "HEAD~1"),
            git(repo, "rev-parse", "HEAD").replace(reviewed, "0" * 40),
            R.body_sig([R.Finding("%s.1" % reviewed[:8], "medium", "a.txt", 1, "in-diff", CLAIM)]),
            reviewed[:8],
            CLAIM,
        ),
        encoding="utf-8",
    )
    (repo / "a.txt").write_text("three\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "fix")
    return repo, reviewed, git(repo, "rev-parse", "HEAD")


def mark(repo, reviewed, arg):
    """None on success, else the refusal text."""
    try:
        R.mark(str(repo), BRANCH, "%s.1" % reviewed[:8], "fixed", [arg], ME)
    except ValueError as err:
        return str(err)
    return None


def resolution(repo, reviewed):
    text = (repo / "agent" / "reviews" / BRANCH / ("%s.md" % reviewed)).read_text(encoding="utf-8")
    return next(line for line in text.splitlines() if line.startswith("Resolution:"))


# ---- 1. CONTROL: a bare sha marks the finding fixed ---------------------------------------------------
repo, reviewed, fix = fixture("bare")
control("bare sha: accepted", mark(repo, reviewed, fix), None)
control("bare sha: resolution is fixed", resolution(repo, reviewed).split()[1], "fixed")

# ---- 2. THE DEFECT: commit:<sha>, the --tick form, names the same commit ------------------------------
repo, reviewed, fix = fixture("prefixed")
control("commit:<sha>: accepted", mark(repo, reviewed, "commit:" + fix[:10]), None)
control("commit:<sha>: resolution is fixed", resolution(repo, reviewed).split()[1], "fixed")

# ---- 3. THE REFUSALS stay refusals, with or without the prefix ----------------------------------------
repo, reviewed, fix = fixture("refused")
unknown = mark(repo, reviewed, "commit:" + "f" * 40)
control("an unknown sha: refused", unknown is not None and "does not resolve" in unknown, True)
itself = mark(repo, reviewed, "commit:" + reviewed)
control(
    "the reviewed commit itself: refused",
    itself is not None and "cannot be the reviewed" in itself,
    True,
)
control("nothing was marked by a refusal", resolution(repo, reviewed), "Resolution: open")

print("%d control(s), %d failed" % (Tally.count, Tally.fails))
sys.exit(1 if Tally.fails else 0)
