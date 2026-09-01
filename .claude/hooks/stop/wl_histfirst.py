"""When CI goes red, put the commits that could have caused it in front of the session.

THE BLIND SPOT, and it is the operator's observation rather than a theory: an agent
debugging a failure reads the CODE and never the HISTORY. This repo writes unusually
substantial commit messages -- they carry measurements, rejected hypotheses and
corrections -- so the cheapest evidence available is the one thing systematically skipped.

MEASURED ON THE SESSION THAT PROMPTED THIS. `packages/www/scripts/
test-tutorial-player-release-gate.js` went red four times. Across 2,494 Bash calls in that
session's transcript there were ZERO `git log`/`blame`/`bisect` invocations naming it,
while eight lines of `git log --oneline -- <that file>` held both decisive facts: the
readiness matcher had changed minutes earlier (and was the regression), and the same gate
had failed before. The session guessed wrong twice and only got there via a downloaded
artifact, hours later.

WHY THIS IS MECHANICAL AND NOT A JUDGED RULE, which is structural and not a preference.
The red-CI path emits and EXITS before the judge is ever reached: `wl_checks` adds the
`ci-red` violation, the `if violations and not pause:` block calls `C.emit`, and
`wl_core.emit` ends with `sys.exit(0)` -- all of it upstream of `wl_judge.run_judge`. A
judged history rule could not fire on the stop that matters. And no model is needed: every
fact wanted here comes from `git log` plus the failing job name already in hand.

IT DEMANDS NOTHING, DELIBERATELY. It appends facts to a block that is already being
emitted. That is what keeps it from becoming a wall -- this repo has the scar of a rule
that fired on every stop -- and it cannot be faked, because there is no claim to make.
Enforcement (checking the session actually ran the command) is a later increment, and only
if the printed facts turn out to be skimmed.
"""

import re
import subprocess

# The literal string the block body carries. A later increment greps the transcript for it
# to confirm the demand was issued, so it is load-bearing rather than decorative.
HISTORY_MARKER = "READ THE HISTORY BEFORE YOU GUESS"

# How far back to look when no last-green head is banked.
FALLBACK_WINDOW = "HEAD~10"
# Commits and suspects shown. A block nobody finishes reading is a block that taught
# nothing, and the top few are where a regression from this session's own work will be.
MAX_COMMITS = 8
MAX_SUSPECTS = 5

# Tokens too generic to imply a connection between a job name and a path. Without this,
# "test" alone matches most of the tree and every commit looks like a suspect.
STOPWORDS = frozenset(
    (
        "test",
        "tests",
        "check",
        "checks",
        "main",
        "node",
        "src",
        "scripts",
        "script",
        "packages",
        "package",
        "build",
        "gate",
        "gates",
        "step",
        "steps",
        "job",
        "jobs",
        "quality",
        "release",
        "run",
        "npm",
        "lib",
    )
)
MIN_TOKEN = 4
# Two overlapping tokens, not one: one is coincidence at this vocabulary size.
MIN_OVERLAP = 2


def _git(root, *args):
    """Stdout, or "" on any failure. A diagnostic must never wedge a stop."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def tokens(text):
    """The words in a job or path that could tie the two together."""
    raw = re.split(r"[^A-Za-z0-9]+", (text or "").lower())
    return {t for t in raw if len(t) >= MIN_TOKEN and t not in STOPWORDS}


def suspects(root, window, job_tokens):
    """[(sha, subject, [paths])] for commits in `window` touching a matching path.

    THE JOB -> FILE BRIDGE IS A TOKEN MATCH, NOT A RESOLUTION CHAIN. An exact chain does
    exist -- workflow step name, to the `npm run` key, to the workspace script, to the file
    -- and it was rejected: it is three files of parsing across a workspace, and this repo
    already has `wl_reggate.gate_reachable` on record as a manifest-walking probe that
    returned False for EVERY gate, "the same defect as a check that cannot fail". A token
    match needs no parsing and degrades to silence rather than to a confident wrong answer.
    """
    if not job_tokens:
        return []
    out = []
    # AN EXPLICIT RECORD SEPARATOR, because `--name-only` puts a BLANK LINE between the
    # format line and the file list. Splitting on "\n\n" therefore cuts INSIDE a commit,
    # not between commits, and every block after the first begins with a path -- so the
    # separator test failed and every commit was skipped. Caught by running it against the
    # real failure and getting a confident "NONE" for a file two commits had just touched.
    log = _git(root, "log", "--format=%x1e%H%x1f%s", "--name-only", window)
    if not log:
        return []
    for block in log.split("\x1e"):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if not lines or "\x1f" not in lines[0]:
            continue
        sha, subject = lines[0].split("\x1f", 1)
        hits = [p for p in lines[1:] if len(tokens(p) & job_tokens) >= MIN_OVERLAP]
        if hits:
            out.append((sha[:9], subject, hits[:3]))
    return out[:MAX_SUSPECTS]


def render(root, rows, last_green):
    """The block text, or "" when there is nothing worth saying.

    RETURNING "" IS A REAL ANSWER in three of the four cases, which is what stops this
    becoming a deferral pile: no window, no commits, or no commit touching anything named
    like the failing job. That last one is affirmative evidence for a FLAKE, so it is
    printed rather than swallowed.
    """
    if not rows:
        return ""
    window = "%s..HEAD" % last_green if last_green else "%s..HEAD" % FALLBACK_WINDOW
    listing = _git(root, "log", "--oneline", "--no-decorate", window)
    if not listing.strip():
        return ""
    commits = [ln for ln in listing.strip().split("\n") if ln.strip()]

    job_tokens = set()
    for row in rows[:3]:
        job_tokens |= tokens(row.get("name"))
        job_tokens |= tokens(row.get("step"))
    found = suspects(root, window, job_tokens)

    head = "%s\n  %d commit(s) in the window %s%s." % (
        HISTORY_MARKER,
        len(commits),
        window,
        " (no last-green head banked yet, so this is a guess)" if not last_green else "",
    )
    if not found:
        # AFFIRMATIVE EVIDENCE, not silence. "Nothing you changed is named like the thing
        # that broke" is the correct read of a flake, and it is the read this session got
        # wrong three times before an agent measured the base rate.
        return (
            "%s\n  NONE of them touches a file named like the failing job. That is evidence\n"
            "  FOR a flake and against a regression -- check whether this job has failed\n"
            "  before on this branch rather than reading the code again." % head
        )
    body = [head, "  These DO touch files named like it:"]
    for sha, subject, paths in found:
        body.append("    %s  %s" % (sha, subject[:88]))
        body.extend("               %s" % p for p in paths)
    body.append("  Start here:  git log -p -1 %s -- %s" % (found[0][0], found[0][2][0]))
    return "\n".join(body)


def apply_verdict(root, rows, last_green):
    """(kind, text). kind is 'fire' when there is something to print, else 'silent'.

    Shaped like the judged rules' `apply_verdict` on purpose: `check_judged_rule_wiring`
    discovers a rule by a `*_MARKER` plus this function, so deleting the call site turns
    that gate red. A rule nothing calls does not run, and this one has no other symptom.

    FAIL SEMANTICS ARE wl_classsweep's: any git failure or unreadable window degrades to
    silent. It can only ADD to a block that is already happening, so degrading loses a
    hint and can never grant an exit that was otherwise refused.
    """
    try:
        text = render(root, rows, last_green)
    except Exception:  # noqa: BLE001 -- a diagnostic must never wedge a stop
        return "silent", ""
    return ("fire", text) if text else ("silent", "")
