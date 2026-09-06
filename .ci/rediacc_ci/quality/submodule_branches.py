"""Submodule branch, PR-linking and review-comment validation.

Ported from `.ci/scripts/quality/check-submodule-branches.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__`.

-----------------------------------------------------------------------------
THE TWIN'S AI-FRIENDLY HEADER, CARRIED ACROSS IN FULL. It is a troubleshooting
guide, not decoration: every ERROR string below is one this gate prints, and the
FIX under it is what a session is meant to run.
-----------------------------------------------------------------------------

PURPOSE: Validates that submodule branches match the console branch when
expected, ensures submodule PRs are properly linked, and verifies all review
comments on submodule PRs have been addressed.

WHEN THIS CHECK RUNS:
  - On every PR (pull_request event)
  - On pushes to main, and on the nightly, where it asserts the STRONGER rule
    that every gitlink is reachable from the submodule's own origin/main

WHAT IT CHECKS:
  1. For each submodule with pointer changes (different from origin/main):
     a. If the commit is an ancestor of origin/main (pointer bump to
        already-merged work), it passes automatically, no branch/PR needed.
     b. Otherwise (new code beyond main), it requires:
        - A matching branch in the submodule repo
        - An open PR for that branch
        - The PR linked in the console PR description
        - All review comments on the submodule PR addressed
  2. For submodules without pointer changes:
     - Confirms they are on 'main' (expected behavior)

AI TROUBLESHOOTING GUIDE:
-------------------------
ERROR: "Submodule private/renet expected on branch 0203-1 but is on main"
  CAUSE: Submodule has pointer changes but no matching branch was created
  FIX:
    cd private/renet
    git checkout -b 0203-1
    git push -u origin 0203-1

ERROR: "Branch 0203-1 does not exist in private/renet remote"
  CAUSE: Branch exists locally but wasn't pushed to remote
  FIX:
    cd private/renet
    git push -u origin 0203-1

ERROR: "Submodule pointer changed but no matching branch"
  CAUSE: Console tracks a different commit than origin/main, but developer
         didn't create a branch in the submodule for coordinated testing
  FIX: Either:
    1. Create the branch: cd private/<submodule> && git checkout -b <branch>
    2. Or reset pointer: git checkout origin/main -- private/<submodule>

ERROR: "No open PR found for branch 0203-1 in rediacc/renet"
  CAUSE: Branch exists but no PR was created for it
  FIX:
    cd private/renet
    gh pr create --title "feat: your changes" --body "Description"

ERROR: "PR not linked in console PR description"
  CAUSE: Submodule PR exists but is not mentioned in console PR
  FIX: Edit console PR description to include the submodule PR URL:
    ## Related PRs
    - https://github.com/rediacc/renet/pull/123

ERROR: "Submodule PR has N unreplied review comments"
  CAUSE: Review comments on the submodule PR haven't been addressed
  FIX: Go to the submodule PR and reply to all review comments with
       substantive responses (not just "ok", "done", "fixed", etc.)

SKIP CONDITIONS:
  - is_bot == 'true': Skip for bot-generated PRs
  - Submodule not initialized: Skip with warning
  - Not a PR context: PR linking check skipped

EXIT CODES:
  0 - All submodule branches are valid
  1 - Branch mismatch, PR linking, or review comments error detected
  2 - Configuration error (missing env vars, etc.)

-----------------------------------------------------------------------------
THE THREE INCIDENTS THE TWIN'S INLINE COMMENTS RECORD.
-----------------------------------------------------------------------------

THE MAIN-BRANCH HOLE, hit for real on 2026-07-28. console#541 merged while
rediacc/account#69 was still open, so main's gitlink pointed at b0ea51f, a
commit that existed ONLY on that PR's branch. Had the branch been deleted
(which merging normally does), every `submodule update` on main would have
failed with "reference is not a tree", and nothing would have warned. The
PR-side rules cannot catch this: they legitimately ALLOW a pointer at an
unmerged branch commit, because submodule-first means the submodule PR is still
open while the console PR runs. So on main, assert the thing that must be true
once everything has landed: every gitlink is reachable from the submodule's own
origin/main.

THE REPORT HOLE, hit live on 2026-08-09 while landing console#561:
rediacc/account#78's automated review posted a top-level REPORT (no inline
threads), and nothing console-side checked it. The thread check sees only
pulls/comments, and the report landed AFTER the last console run, so no
per-commit check ever re-evaluated. Only the local block-admin-merge hook caught
it, which a web-UI merge would bypass. Rule (same oracle as
check-review-report-replies.sh): the NEWEST "**Claude finished" report on the
sub-PR must have a LATER comment by someone other than the bot that posted it.

THE DETACHED-HEAD TRAP, twice. `rev-parse --abbrev-ref HEAD` SUCCEEDS on a
detached checkout and prints the literal string "HEAD", so a `|| echo "main"` or
`|| echo "detached"` fallback never fires for that case, since git did not fail.
Downstream the console value is compared against a submodule's own (possibly
ALSO detached) branch name; two coincidentally-detached checkouts would both
read "HEAD" and compare EQUAL, reporting a branch match that is not real. Both
functions catch the literal string explicitly rather than leaning on the
fallback.

TWO FAIL-CLOSED REPAIRS, also from the twin's comments. `check_pr_review_comments`
used to end its fetch with `|| echo "[]"`, so a gh failure produced the same
value as a PR with no review comments and the function echoed "0" unreplied,
which the caller reads as "this submodule PR is clean"; it now returns non-zero
so the caller can tell a real zero from an unanswered question. And
`branch_has_merged_pr`'s failed probe used to become "0", i.e. "no merged PR":
the direction is safe (the caller reports the branch as unmerged, which is the
louder answer), but it is still a guess presented as a fact, so it says so.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

`_gh_probe` IS COPIED HERE RATHER THAN IMPORTED, and that is a deliberate choice
against `rediacc_ci.core.ghx`, which is the typed counterpart of the same idea.
The reason is fidelity: `ghx.gh()` classifies failures, raises typed errors and
does not retry three times with a `log_warn` between attempts, so a port built on
it would produce different output on the paths a differential cannot reach
(nothing in a fixture repo can make a real `gh` call). The twin's `_gh_probe`
lives in `common.sh`, which this port does not source, so its 3-attempt loop, its
`sleep $((attempt * 3))` backoff, its JSON validation and both of its message
strings are transliterated below. When `ghx` grows a `_gh_probe`-compatible
entry point, this copy is the first thing that should go.

jq IS REPLACED BY `json`, and every jq expression is quoted above the code that
replaces it so the two can be diffed by eye. The one behavioural note: `jq -r`
prints a number as its decimal text, so a comment id compared as a dictionary key
must be `str(id)` here, not `id`. Comparing ints would work until the day GitHub
returns one as a float in a paginated body.

`git ls-tree HEAD -- <path> | awk '{print $3}'` IS FIELD 3, THE OBJECT NAME, and
`awk` on empty input prints nothing rather than an empty field. A missing gitlink
therefore yields "" on both sides, which the caller tests for explicitly.

`branch_exists_in_remote` USES `grep -q "$branch"` ON THE WHOLE ls-remote LINE,
which is a SUBSTRING test against `<sha>\\trefs/heads/<branch>`, not an equality
test. A branch named `x` therefore "exists" whenever any ref contains `x`
anywhere, including inside the sha. That is over-permissive and it is the twin's
behaviour; it is carried, not narrowed, because narrowing it would turn some
currently-passing PR red for a reason nobody changed.

`for ptr in ${enf//,/ }` -- WORD SPLITTING IS THE PARSER in the sibling trap
gate, and the same shape appears here in `${pr_info%%|*}` / `${pr_info##*|}`:
`get_pr_for_branch` returns `number|url` and the two halves are taken by prefix
and suffix removal. A URL containing a `|` would break it. It cannot, so the
spelling is kept.

STREAMS. Every message goes through `common.sh`'s loggers, which
`rediacc_ci.log` reproduces byte for byte. Note the doubled glyphs: the twin
writes `log_info "✓ $sm_path: ..."` and `log_error "✗ $sm_path: ..."`, so the
logger's own glyph is prepended to a typed one and the line really does read
`✓ ✓ private/renet: ...`. That is not a transcription error here; it is the
twin's output and changing it would change the bytes a reader greps for.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# Submodule to repo mapping. The four submodules this repository carries.
SUBMODULE_REPOS = {
    "private/renet": "rediacc/renet",
    "private/homebrew-tap": "rediacc/homebrew-tap",
    "private/account": "rediacc/account",
    "private/elite": "rediacc/elite",
}

# The iteration ORDER the twin uses in both of its loops, written out rather
# than taken from the mapping above. Bash's associative-array order is a hash
# order and is NOT this list; the two loops both hard-code this sequence, so a
# port that iterated the mapping would print its findings in a different order.
SUBMODULE_ORDER = (
    "private/renet",
    "private/homebrew-tap",
    "private/account",
    "private/elite",
)

# Patterns for low-effort replies that don't count as real responses.
# These are case-insensitive and match the entire reply (with optional
# punctuation).
LOW_EFFORT_PATTERNS = (
    "acknowledged",
    "ack",
    "ok",
    "okay",
    "understood",
    "noted",
    "done",
    "fixed",
    "will do",
    "will fix",
    "got it",
    "thanks",
    "thank you",
    "ty",
    "thx",
    "yes",
    "no",
    "sure",
    "agreed",
    "makes sense",
    "good point",
    "right",
    "correct",
    "i see",
    "see above",
    "addressed",
    "updated",
    "changed",
    "applied",
)

# Anything shorter than this, after normalisation, is low-effort whatever it
# says. The twin's number, kept as a name so the two uses of it agree.
MIN_SUBSTANTIVE_LENGTH = 10

# The prefix the automated reviewer's top-level report starts with.
REPORT_PREFIX = "**Claude finished"


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """`subprocess.run` with text output and no exception on a non-zero exit.

    A missing binary comes back as returncode 127 with empty output, because
    that is what a shell reports and every caller here was written against a
    shell. See `rediacc_ci.quality.subscription_schema` for the same point.
    """
    try:
        return subprocess.run(
            args,
            stdout=kwargs.pop("stdout", subprocess.PIPE),
            stderr=kwargs.pop("stderr", subprocess.DEVNULL),
            text=True,
            check=False,
            **kwargs,
        )
    except OSError:
        return subprocess.CompletedProcess(args, 127, "", "")


def have_gh() -> bool:
    """`command -v gh &>/dev/null`."""
    return shutil.which("gh") is not None


def gh_probe(require_json: bool, what: str, args: list[str]) -> tuple[bool, str]:
    """`common.sh`'s `_gh_probe`, transliterated. (ok, stdout).

    Three attempts, a `log_warn` between them, a 3/6 second backoff, and an
    optional JSON validity check because "`gh api graphql` can exit 0 while
    returning a truncated or malformed body, so an exit-code check alone misses
    it". The failing branch prints the last exit code and the captured stderr,
    indented four spaces, exactly as the twin's `sed 's/^/    /'` does.
    """
    attempt = 1
    rc = 0
    err = ""
    out = ""
    while attempt <= 3:
        proc = _run(["gh", *args], stderr=subprocess.PIPE)
        rc = proc.returncode
        out = proc.stdout or ""
        err = proc.stderr or ""
        if rc == 0:
            if not require_json:
                return True, out
            if out:
                try:
                    json.loads(out)
                except ValueError:
                    pass
                else:
                    return True, out
        if attempt < 3:
            log.warn(
                "%s: gh call failed or returned unusable output (attempt %d/3), retrying..."
                % (what, attempt)
            )
            time.sleep(attempt * 3)
        attempt += 1
    log.error("%s: gh failed after 3 attempts (last exit %d)." % (what, rc))
    if err:
        for line in err.rstrip("\n").split("\n"):
            print("    %s" % line, file=sys.stderr)
    return False, ""


def is_low_effort_reply(reply: str) -> bool:
    """True when the reply is not a real response.

    The normalisation is the twin's four-stage pipeline and it runs PER LINE,
    because `sed` does: `echo "$reply" | tr '[:upper:]' '[:lower:]' |
    sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed 's/[.!?]*$//'`. A multi-line
    reply therefore has every line trimmed and every line's trailing punctuation
    removed, and the LENGTH test below is applied to the joined result.
    `$(...)` strips the trailing newline `echo` added, which is why the join
    drops a trailing empty line.
    """
    lowered = reply.lower()
    lines = []
    for line in lowered.split("\n"):
        stripped = re.sub(r"^[ \t]*", "", line)
        stripped = re.sub(r"[ \t]*$", "", stripped)
        stripped = re.sub(r"[.!?]*$", "", stripped)
        lines.append(stripped)
    normalized = "\n".join(lines)
    # `$(...)` strips trailing newlines, and `echo` added exactly one.
    normalized = normalized.rstrip("\n")

    for pattern in LOW_EFFORT_PATTERNS:
        if normalized == pattern:
            return True
    # Also reject very short replies.
    return len(normalized) < MIN_SUBSTANTIVE_LENGTH


def current_branch(root: pathlib.Path, env: dict[str, str] | None = None) -> str:
    """The console branch, from the CI context or from git. Never "HEAD".

    See the detached-head trap in the module docstring for why the literal
    string is caught rather than left to the `|| echo "main"` fallback.
    """
    environ = os.environ if env is None else env
    if environ.get("GITHUB_HEAD_REF"):
        return environ["GITHUB_HEAD_REF"]
    if environ.get("GITHUB_REF_NAME"):
        return environ["GITHUB_REF_NAME"]
    proc = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(root))
    name = proc.stdout.strip() if proc.returncode == 0 else ""
    if name in ("", "HEAD"):
        return "main"
    return name


def gitlink_at(root: pathlib.Path, ref: str, sm_path: str) -> str:
    """`git ls-tree <ref> -- <path> | awk '{print $3}'`, or "".

    Field 3 of a tree entry is the object name. Empty input means the ref does
    not record that path at all, and `awk` prints nothing for it.
    """
    proc = _run(["git", "ls-tree", ref, "--", sm_path], cwd=str(root))
    if proc.returncode != 0:
        return ""
    for line in proc.stdout.split("\n"):
        fields = line.split()
        if len(fields) >= 3:
            return fields[2]
    return ""


def submodule_has_pointer_changes(root: pathlib.Path, sm_path: str) -> bool:
    """Does HEAD's gitlink differ from origin/main's?

    Both must be present AND different. A missing origin/main -- a fresh clone
    with no fetch, or a fixture -- therefore reads as "no pointer changes",
    which is the permissive direction and is the twin's.
    """
    head_commit = gitlink_at(root, "HEAD", sm_path)
    origin_commit = gitlink_at(root, "origin/main", sm_path)
    return bool(head_commit) and bool(origin_commit) and head_commit != origin_commit


def submodule_branch(root: pathlib.Path, sm_path: str) -> str:
    """The submodule's own branch, or the sentinel "detached"."""
    proc = _run(["git", "-C", sm_path, "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(root))
    name = proc.stdout.strip() if proc.returncode == 0 else ""
    if name in ("", "HEAD"):
        return "detached"
    return name


def branch_exists_in_remote(root: pathlib.Path, sm_path: str, branch: str) -> bool:
    """`git ls-remote --heads origin <branch> | grep -q "<branch>"`.

    A SUBSTRING test on the whole line, not an equality test on the ref name.
    See the port notes: over-permissive, and carried unchanged.
    """
    proc = _run(["git", "-C", sm_path, "ls-remote", "--heads", "origin", branch], cwd=str(root))
    if proc.returncode != 0:
        return False
    return branch in proc.stdout


def get_pr_for_branch(repo: str, branch: str) -> str:
    """ "number|url" for the open PR on this branch, or "".

    jq: `.[0] // empty | "\\(.number)|\\(.url)"`. A missing `gh`, a failed call
    and a branch with no open PR all produce "", which is the twin's behaviour
    and the one place it does NOT fail closed: the caller's next move is to ask
    whether a MERGED PR exists, which is the louder question anyway.
    """
    if not have_gh():
        return ""
    proc = _run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "number,url",
        ]
    )
    if proc.returncode != 0:
        return ""
    try:
        rows = json.loads(proc.stdout or "[]")
    except ValueError:
        return ""
    if not rows:
        return ""
    first = rows[0]
    return "%s|%s" % (first.get("number"), first.get("url"))


def branch_has_merged_pr(repo: str, branch: str) -> bool:
    """Is there a MERGED PR for this branch? Fail-closed, and it says so."""
    if not have_gh():
        return False
    ok, out = gh_probe(
        False,
        "merged-PR lookup for %s#%s" % (repo, branch),
        ["pr", "list", "--repo", repo, "--head", branch, "--state", "merged", "--json", "number"],
    )
    if not ok:
        log.warn(
            "%s: could not determine whether %s has a merged PR; treating it as NOT merged"
            % (repo, branch)
        )
        return False
    # jq 'length' over the array. A non-numeric answer is not trusted.
    try:
        rows = json.loads(out or "[]")
    except ValueError:
        return False
    if not isinstance(rows, list):
        return False
    return len(rows) > 0


def console_pr_body(env: dict[str, str] | None = None) -> str:
    """The console PR description, or "" when there is no PR context."""
    environ = os.environ if env is None else env
    pr_number = environ.get("PR_NUMBER", "")
    if not pr_number:
        return ""
    if not have_gh():
        return ""
    proc = _run(["gh", "pr", "view", pr_number, "--json", "body"])
    if proc.returncode != 0:
        return ""
    try:
        return str(json.loads(proc.stdout or "{}").get("body") or "")
    except ValueError:
        return ""


def pr_is_linked(pr_url: str, text: str) -> bool:
    """Is this PR mentioned in that text, by URL or by `org/repo#123`?

    Both shapes, because a human writes the second and a template writes the
    first. The twin uses a here-string rather than a pipe into `grep -q`
    specifically "to avoid SIGPIPE with grep -q under pipefail", which is a bash
    hazard with no Python counterpart and is recorded here rather than obeyed.
    """
    if not pr_url or not text:
        return False
    number_match = re.search(r"[0-9]+$", pr_url)
    pr_number = number_match.group(0) if number_match else ""
    if pr_url in text:
        return True
    repo_match = re.search(r"github\.com/[^/]+/[^/]+", pr_url)
    repo = repo_match.group(0).replace("github.com/", "") if repo_match else ""
    if repo and pr_number:
        pattern = re.compile(
            r"%s#%s|%s/pull/%s"
            % (re.escape(repo), re.escape(pr_number), re.escape(repo), re.escape(pr_number))
        )
        if pattern.search(text):
            return True
    return False


def judge_report(comments: list[dict]) -> str:
    """ "none" | "answered" | "unanswered" for a list of issue comments.

    SPLIT FROM THE FETCH ON PURPOSE. The `gh` call cannot run in a test and the
    JUDGEMENT is the part that decides a merge, so the judgement is a pure
    function the selftest drives directly and `report_answered` is a thin
    wrapper over a fetch. There is exactly one implementation; a second copy
    written "for the test" is a copy that drifts and then tests nothing.
    """
    reports = [c for c in comments if str(c.get("body") or "").startswith(REPORT_PREFIX)]
    if not reports:
        return "none"
    newest = max(reports, key=lambda c: str(c.get("created_at") or ""))
    newest_at = str(newest.get("created_at") or "")
    newest_login = str((newest.get("user") or {}).get("login") or "")
    for comment in comments:
        later = str(comment.get("created_at") or "") > newest_at
        other = str((comment.get("user") or {}).get("login") or "") != newest_login
        if later and other:
            return "answered"
    return "unanswered"


def count_unreplied(comments: list[dict]) -> int:
    """Original comments with no SUBSTANTIVE reply. Pure; see `judge_report`.

    jq: `[.[] | select(.in_reply_to_id != null)]` are the replies and
    `[.[] | select(.in_reply_to_id == null)]` the originals. Keys are the TEXT
    of the id; see the port notes on `jq -r` and numbers.
    """
    replies = [c for c in comments if c.get("in_reply_to_id") is not None]
    originals = [c for c in comments if c.get("in_reply_to_id") is None]
    if not originals:
        return 0
    answered = {
        str(r.get("in_reply_to_id"))
        for r in replies
        if not is_low_effort_reply(str(r.get("body") or ""))
    }
    return sum(1 for c in originals if str(c.get("id")) not in answered)


def unreplied_review_comments(repo: str, pr_number: str) -> tuple[bool, int]:
    """(could-read, count of original comments with no substantive reply).

    FAIL CLOSED. `(False, 0)` means the comments could not be read, and the
    caller must treat that as a finding rather than as a clean PR. Returning a
    tuple rather than an int-through-stdout is the one shape change in this
    function; the twin encodes the same two facts as an exit status plus an
    echoed number, which is the shell's only way to return two things.
    """
    if not have_gh():
        return True, 0
    ok, body = gh_probe(
        True,
        "review comments for %s#%s" % (repo, pr_number),
        ["api", "repos/%s/pulls/%s/comments" % (repo, pr_number), "--paginate"],
    )
    if not ok:
        log.error(
            "%s#%s: could not fetch review comments; refusing to report zero unreplied"
            % (repo, pr_number)
        )
        return False, 0
    if body.strip() == "[]":
        return True, 0
    try:
        comments = json.loads(body)
    except ValueError:
        return False, 0

    return True, count_unreplied(comments)


def report_answered(repo: str, pr_number: str) -> tuple[bool, str]:
    """(could-read, "none" | "answered" | "unanswered").

    The jq the twin uses does the whole judgement so bash never parses comment
    bodies: pick the newest report by created_at, then ask whether ANY comment
    from a different login was created after it.

        ([.[] | select(.body | startswith("**Claude finished"))]
           | sort_by(.created_at) | last) as $r
        | if $r == null then "none"
          elif ([.[] | select(.created_at > $r.created_at
                              and .user.login != $r.user.login)] | length) > 0
          then "answered"
          else "unanswered" end

    The comparison is on the ISO-8601 STRING, not on a parsed timestamp, which
    is correct for the `Z`-suffixed form GitHub returns and would be wrong for
    mixed offsets. Carried as a string comparison for that reason.
    """
    if not have_gh():
        return True, "none"
    ok, body = gh_probe(
        True,
        "issue comments for %s#%s" % (repo, pr_number),
        ["api", "repos/%s/issues/%s/comments" % (repo, pr_number), "--paginate"],
    )
    if not ok:
        return False, ""
    try:
        comments = json.loads(body)
    except ValueError:
        return False, ""
    return True, judge_report(comments)


def submodule_initialised(root: pathlib.Path, sm_path: str) -> bool:
    """`[[ -d "$p/.git" ]] || [[ -f "$p/.git" ]]`.

    A directory for a plain clone, a FILE for a real submodule checkout whose
    `.git` is a `gitdir:` pointer. Both count.
    """
    marker = root / sm_path / ".git"
    return marker.is_dir() or marker.is_file()


def check_on_main(root: pathlib.Path) -> int:
    """The stronger rule that only applies on main. Returns the exit code.

    Every gitlink must be reachable from the submodule's own origin/main. See
    the 2026-07-28 incident in the module docstring for what this closes.
    """
    log.step("On main: asserting every submodule pointer is on the submodule's main")
    main_errors = 0
    for sm_path in SUBMODULE_ORDER:
        if not submodule_initialised(root, sm_path):
            log.warn("Submodule %s not initialized - cannot verify its pointer" % sm_path)
            continue
        sm_commit = gitlink_at(root, "HEAD", sm_path)
        if not sm_commit:
            log.warn("%s: no gitlink recorded at HEAD - skipping" % sm_path)
            continue
        _run(["git", "-C", sm_path, "fetch", "origin", "main", "--quiet"], cwd=str(root))
        ancestor = _run(
            ["git", "-C", sm_path, "merge-base", "--is-ancestor", sm_commit, "origin/main"],
            cwd=str(root),
        )
        if ancestor.returncode == 0:
            log.info(
                "✓ %s: pointer %s is on %s/main"
                % (sm_path, sm_commit, SUBMODULE_REPOS.get(sm_path, "origin"))
            )
        else:
            log.error("✗ %s: pointer %s is NOT reachable from origin/main" % (sm_path, sm_commit))
            log.error("  main must never depend on a commit that lives only on a branch:")
            log.error("  delete that branch and the superproject stops resolving.")
            log.error("  Fix: merge the submodule PR, then bump this pointer to the merge commit.")
            main_errors += 1
    if main_errors > 0:
        log.error("%d submodule pointer(s) on main are not on the submodule's main" % main_errors)
        return 1
    log.info("All submodule pointers on main are reachable from their own main")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Validate every submodule against the console branch. 0 valid, 1 not.

    The branching here is the twin's, arm for arm. It is long because the
    subject is: four submodules crossed with pointer-changed or not, branch
    present or not, PR open or merged or missing, linked or not, comments
    readable or not, report answered or not. Collapsing arms would lose the
    distinct message each one prints, and those messages are the gate's whole
    value (see the AI TROUBLESHOOTING GUIDE above).
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    branch = current_branch(root)
    errors = 0
    warnings = 0
    pr_body = ""

    log.step("Validating submodule branches (console branch: %s)" % branch)

    if branch == "main":
        return check_on_main(root)

    # Fetch origin/main for comparison. Failure is ignored: an offline run still
    # has something to compare against, and the pointer test below treats a
    # missing origin/main as "no pointer changes".
    _run(["git", "fetch", "origin", "main", "--quiet"], cwd=str(root))

    pr_number = os.environ.get("PR_NUMBER", "")
    if pr_number and have_gh():
        pr_body = console_pr_body()

    for sm_path in SUBMODULE_ORDER:
        if not submodule_initialised(root, sm_path):
            log.warn("Submodule %s not initialized - skipping" % sm_path)
            warnings += 1
            continue

        repo = SUBMODULE_REPOS.get(sm_path, "")

        if not submodule_has_pointer_changes(root, sm_path):
            # No changes: it should be on main.
            sm_branch = submodule_branch(root, sm_path)
            if sm_branch in ("main", "detached", "HEAD"):
                log.info("✓ %s: no pointer changes, on '%s' (expected)" % (sm_path, sm_branch))
            else:
                log.warn(
                    "⚠ %s: no pointer changes but on branch '%s' (expected main)"
                    % (sm_path, sm_branch)
                )
                warnings += 1
            continue

        # Pointer changed. An ancestor of origin/main is a bump to already-merged
        # work and needs no coordinated branch or PR.
        sm_commit = gitlink_at(root, "HEAD", sm_path)
        ancestor = _run(
            ["git", "-C", sm_path, "merge-base", "--is-ancestor", sm_commit, "origin/main"],
            cwd=str(root),
        )
        if ancestor.returncode == 0:
            log.info("✓ %s: pointer changed but commit is on main (pointer bump only)" % sm_path)
            continue

        sm_branch = submodule_branch(root, sm_path)
        if sm_branch != branch and not branch_exists_in_remote(root, sm_path, branch):
            log.error("✗ %s: has pointer changes but branch '%s' not found" % (sm_path, branch))
            log.error(
                "  AI FIX: cd %s && git checkout -b %s && git push -u origin %s"
                % (sm_path, branch, branch)
            )
            errors += 1
            continue

        log.info("✓ %s: branch '%s' exists (has pointer changes)" % (sm_path, branch))

        if not (repo and pr_number and have_gh()):
            continue

        pr_info = get_pr_for_branch(repo, branch)
        if not pr_info:
            # No open PR: an already-merged one is fine.
            if branch_has_merged_pr(repo, branch):
                log.info("✓ %s: PR for branch '%s' was already merged" % (sm_path, branch))
            else:
                log.error("✗ %s: no open PR found for branch '%s' in %s" % (sm_path, branch, repo))
                log.error(
                    "  AI FIX: cd %s && gh pr create --title 'Your PR title' "
                    "--body 'Description'" % sm_path
                )
                errors += 1
            continue

        sub_pr_number = pr_info.split("|", 1)[0]
        sub_pr_url = pr_info.rsplit("|", 1)[-1]

        if pr_body and not pr_is_linked(sub_pr_url, pr_body):
            log.error("✗ %s: PR %s not linked in console PR description" % (sm_path, sub_pr_url))
            log.error("  AI FIX: Edit console PR description to include: %s" % sub_pr_url)
            errors += 1
        else:
            log.info("✓ %s: PR %s is linked" % (sm_path, sub_pr_url))

        readable, unreplied = unreplied_review_comments(repo, sub_pr_number)
        if not readable:
            log.error("✗ %s: could not read review comments for %s" % (sm_path, sub_pr_url))
            log.error("  This gate cannot certify the PR is clean, so it counts as an error.")
            errors += 1
        elif unreplied > 0:
            log.error("✗ %s: PR has %d unreplied review comment(s)" % (sm_path, unreplied))
            log.error("  AI FIX: Go to %s and reply to all review comments" % sub_pr_url)
            log.error("  NOTE: Low-effort replies like 'ok', 'done', 'fixed' don't count")
            errors += 1
        else:
            log.info("✓ %s: all review comments addressed" % sm_path)

        can_read, state = report_answered(repo, sub_pr_number)
        if not can_read:
            log.error("✗ %s: could not read issue comments for %s" % (sm_path, sub_pr_url))
            log.error("  This gate cannot certify the report state, so it counts as an error.")
            errors += 1
        elif state == "unanswered":
            log.error(
                "✗ %s: the newest automated review REPORT on %s has no reply"
                % (sm_path, sub_pr_url)
            )
            log.error(
                "  AI FIX: answer the report substantively (a top-level PR comment posted after it)"
            )
            errors += 1
        else:
            log.info("✓ %s: review report answered (%s)" % (sm_path, state))

    # A bare `echo ""` in the twin: one blank line before the verdict.
    print()

    if errors > 0:
        log.error("Submodule branch validation failed with %d error(s)" % errors)
        return 1
    if warnings > 0:
        log.warn("Submodule branch validation passed with %d warning(s)" % warnings)
        return 0
    log.info("All submodule branches validated successfully")
    return 0


def selftest() -> int:
    """Both directions on every decision this gate makes without the network.

    THE GH PATHS ARE COVERED BY PURE FUNCTIONS, not by mocks: `pr_is_linked`,
    `is_low_effort_reply` and the two jq translations are the parts that decide
    a verdict, and each is exercised against the shape GitHub actually returns.
    What no local suite can prove is the `gh` invocation itself, which is stated
    rather than faked.
    """
    ctl = Controls("submodule-branches", floor=39, verbose=True)
    # -- is_low_effort_reply ------------------------------------------------
    for word in ("ok", "Done", "  fixed.  ", "THANKS!!", "will do"):
        ctl.truthy("PLANT: %r is a low-effort reply" % word, is_low_effort_reply(word))
    ctl.truthy(
        "PLANT: anything under 10 characters is low-effort whatever it says",
        is_low_effort_reply("hm, sure"),
    )
    ctl.falsy(
        "MIRROR: a real answer is substantive",
        is_low_effort_reply("Fixed by moving the guard above the fetch, see line 42."),
    )
    ctl.falsy(
        "MIRROR: a long reply that merely CONTAINS a low-effort word is substantive",
        is_low_effort_reply("done, and here is why that was the wrong shape"),
    )
    ctl.truthy(
        "CONTROL: trailing punctuation does not rescue a low-effort reply",
        is_low_effort_reply("agreed."),
    )
    ctl.check(
        "CONTROL: normalisation is per LINE, as sed is",
        is_low_effort_reply("  ok  \n"),
        True,
    )

    # -- pr_is_linked -------------------------------------------------------
    url = "https://github.com/rediacc/renet/pull/123"
    ctl.truthy("CONTROL: the bare URL counts as a link", pr_is_linked(url, "see %s" % url))
    ctl.truthy(
        "CONTROL: the org/repo#number shorthand counts too",
        pr_is_linked(url, "depends on rediacc/renet#123"),
    )
    ctl.truthy(
        "CONTROL: the org/repo/pull/number form counts too",
        pr_is_linked(url, "rediacc/renet/pull/123"),
    )
    ctl.falsy("MIRROR: an unrelated body is not a link", pr_is_linked(url, "no mention here"))
    ctl.falsy(
        "MIRROR: a DIFFERENT PR number in the same repo is not this link",
        pr_is_linked(url, "rediacc/renet#124"),
    )
    ctl.falsy("VACUITY: an empty URL cannot be linked", pr_is_linked("", "rediacc/renet#123"))
    ctl.falsy("VACUITY: an empty body links nothing", pr_is_linked(url, ""))

    # -- current_branch, and the detached-head trap -------------------------
    ctl.check(
        "CONTROL: GITHUB_HEAD_REF wins when set",
        current_branch(pathlib.Path("."), env={"GITHUB_HEAD_REF": "0203-1"}),
        "0203-1",
    )
    ctl.check(
        "CONTROL: GITHUB_REF_NAME is the fallback",
        current_branch(pathlib.Path("."), env={"GITHUB_REF_NAME": "main"}),
        "main",
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        subprocess.run(["git", "init", "-q", "-b", "feature-x"], cwd=str(root), check=True)
        subprocess.run(
            ["git", "config", "user.email", "s@example.invalid"], cwd=str(root), check=True
        )
        subprocess.run(["git", "config", "user.name", "s"], cwd=str(root), check=True)
        (root / "f.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(root), check=True)
        subprocess.run(["git", "commit", "-qm", "c"], cwd=str(root), check=True)

        ctl.check(
            "CONTROL: with no CI context the branch comes from git",
            current_branch(root, env={}),
            "feature-x",
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(["git", "checkout", "-q", head], cwd=str(root), check=True)
        ctl.check(
            "PLANT: a DETACHED head reads as 'main', never as the literal HEAD",
            current_branch(root, env={}),
            "main",
        )

        # -- gitlink_at and submodule_has_pointer_changes -------------------
        ctl.check(
            "VACUITY: a path with no gitlink yields nothing, not a bogus sha",
            gitlink_at(root, "HEAD", "private/renet"),
            "",
        )
        ctl.falsy(
            "MIRROR: no gitlink on either side is NOT a pointer change",
            submodule_has_pointer_changes(root, "private/renet"),
        )
        ctl.check(
            "VACUITY: a ref that does not exist yields nothing",
            gitlink_at(root, "origin/main", "private/renet"),
            "",
        )

        # -- submodule_initialised, all three shapes -----------------------
        ctl.falsy(
            "MIRROR: an absent submodule is not initialised",
            submodule_initialised(root, "private/renet"),
        )
        (root / "private" / "renet").mkdir(parents=True)
        ctl.falsy(
            "MIRROR: a directory with no .git is not initialised",
            submodule_initialised(root, "private/renet"),
        )
        (root / "private" / "renet" / ".git").mkdir()
        ctl.truthy("CONTROL: a .git DIRECTORY counts", submodule_initialised(root, "private/renet"))
        (root / "private" / "renet" / ".git").rmdir()
        (root / "private" / "renet" / ".git").write_text(
            "gitdir: ../../.git/modules/renet\n", encoding="utf-8"
        )
        ctl.truthy(
            "CONTROL: a .git FILE (a real submodule checkout) counts too",
            submodule_initialised(root, "private/renet"),
        )

        # -- submodule_branch, including the detached sentinel --------------
        ctl.check(
            "VACUITY: a path that is not a repo reads as 'detached', never as a branch",
            submodule_branch(root, "private/renet"),
            "detached",
        )

    # -- the report oracle, over the shape the API returns ------------------
    bot = {"login": "claude[bot]"}
    human = {"login": "muhammed"}

    def issue(body: str, at: str, user: dict) -> dict:
        return {"body": body, "created_at": at, "user": user}

    ctl.check(
        "CONTROL: no report at all is 'none'",
        judge_report([issue("hello", "2026-09-01T00:00:00Z", human)]),
        "none",
    )
    ctl.check(
        "PLANT: a report with nothing after it is 'unanswered' (the 2026-08-09 hole)",
        judge_report([issue("**Claude finished the review", "2026-09-01T00:00:00Z", bot)]),
        "unanswered",
    )
    ctl.check(
        "CONTROL: a later comment by SOMEONE ELSE answers it",
        judge_report(
            [
                issue("**Claude finished the review", "2026-09-01T00:00:00Z", bot),
                issue("thanks, fixed in abc123", "2026-09-01T01:00:00Z", human),
            ]
        ),
        "answered",
    )
    ctl.check(
        "PLANT: a later comment by the SAME bot does not answer it",
        judge_report(
            [
                issue("**Claude finished the review", "2026-09-01T00:00:00Z", bot),
                issue("still working", "2026-09-01T01:00:00Z", bot),
            ]
        ),
        "unanswered",
    )
    ctl.check(
        "PLANT: only the NEWEST report counts, so an answered old one does not carry a new one",
        judge_report(
            [
                issue("**Claude finished one", "2026-09-01T00:00:00Z", bot),
                issue("replied", "2026-09-01T01:00:00Z", human),
                issue("**Claude finished two", "2026-09-01T02:00:00Z", bot),
            ]
        ),
        "unanswered",
    )

    # -- the unreplied-comment oracle --------------------------------------
    def review(cid: int, reply_to, body: str) -> dict:
        return {"id": cid, "in_reply_to_id": reply_to, "body": body}

    ctl.check(
        "CONTROL: an original with a substantive reply is answered",
        count_unreplied([review(1, None, "why?"), review(2, 1, "because the guard moved up")]),
        0,
    )
    ctl.check(
        "PLANT: an original with only a low-effort reply is UNreplied",
        count_unreplied([review(1, None, "why?"), review(2, 1, "done")]),
        1,
    )
    ctl.check(
        "PLANT: an original with no reply at all is unreplied",
        count_unreplied([review(1, None, "why?")]),
        1,
    )
    ctl.check(
        "MIRROR: a reply to a DIFFERENT comment does not answer this one",
        count_unreplied(
            [review(1, None, "a"), review(2, None, "b"), review(3, 2, "a real answer here")]
        ),
        1,
    )
    ctl.check("VACUITY: no comments at all means nothing unreplied", count_unreplied([]), 0)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
