#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/detect-pointer-bump.sh` (208 lines).

Detect a "pointer bump only" PR head: content provably identical to a commit
that already passed full CI, differing only in submodule gitlinks that moved to
tree-identical commits now on the submodules' main. When it fires, `ci.yml`
skips the expensive jobs and the run goes green in minutes, honestly, because
the proof is content identity rather than trust. Any doubt on any step degrades
to `pointer_bump_only=false`.

The twin's header owns the three-step proof and the D9 root cause; neither is
restated here.

LIVE CALLER, NOT REPOINTED. `initialize.sh` runs the bash twin after submodule
init, and `.ci/rediacc_ci/ci/initialize.py` invokes the same bash file. This
module is the twin's verified-equivalent alternative, and the cutover is a
separate, later, driver-only step.

NOT A REGISTERED GATE. It carries no `---- gate ----` header (checked with
`scripts/lib/gate-header.ts`'s own OPEN pattern, not by eye), so nothing in
`scripts/ci-runner` selects it; it is a workflow STEP that writes two outputs.
This port carries no header either, for the same reason.

Ledger: `.ci/shadow/w7p6-detect-pointer-bump.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-detect-pointer-bump --assert
--k 5`).

-----------------------------------------------------------------------------
`git`, `gh`, `jq` AND `sed` ARE CALLED, NOT REIMPLEMENTED
-----------------------------------------------------------------------------
Every fact this script rules on comes out of one of those four, and three of
them are doing something a Python library would do DIFFERENTLY rather than
identically:

  * `git` is the whole subject. `diff-tree -r --raw`'s exact field layout,
    `rev-parse --verify --quiet`'s silence, and `^`/`^2`/`^{commit}`'s
    resolution rules are the observations being compared.
  * `gh` carries the credential and the `--jq` program that reduces each
    response to one field.
  * `jq` reads the event payload. `command -v jq` is a real branch in the twin
    (no jq means the payload is not consulted at all), so a port that used
    Python's `json` would have to fake a dependency it does not have.
  * `sed -E 's#\\.git$##; s#.*[:/]([^/]+/[^/]+)$#\\1#'` turns a submodule URL into
    an `owner/repo` slug. Two substitutions, applied in order, the second
    depending on the first; a Python rewrite is a second dialect to keep in
    step.

TWO THINGS ARE REIMPLEMENTED, both pure text, both unit-tested against the
semantics they copy: `awk '{print $N}'` (Python's `str.split()` has awk's exact
default-FS behaviour) and the `grep -vE '^:160000 160000 ' | grep -q .`
predicate, which is a line test with no regex left in it once the anchor is
read as a prefix.

-----------------------------------------------------------------------------
DEFECT A -- THE `HEAD is not a pointer-only commit` GUARD IS UNREACHABLE ON THE
ONLY EVENT THIS SCRIPT RUNS FOR
-----------------------------------------------------------------------------
D9's fix resolves the walk's starting commit from the EVENT payload, because on
a `pull_request` event `git rev-parse HEAD` names the synthetic
`refs/pull/N/merge` commit rather than the branch tip. The fix was applied to
`current` (:90-112) and NOT to `head_sha` (:119), which is still
`git rev-parse HEAD`.

So on a real PR event `current` is the branch tip and `head_sha` is the merge
commit, and they are NEVER equal. The comparison at :138 therefore cannot be
true on the first iteration, and a PR whose tip is an ordinary commit -- the
common case, the one this guard was written for -- falls out of the loop with
`baseline` still empty and reports

    pointer_bump_only=false -- no baseline within 5 commits

instead of

    pointer_bump_only=false -- HEAD is not a pointer-only commit

Same verdict, wrong reason, and the wrong reason is the one an operator reads
when asking why the fast path did not fire. Driven in the differential
(`test_defect_a_...`) against both implementations.

-----------------------------------------------------------------------------
DEFECT B -- STEP 3 STILL COMPARES AGAINST `HEAD`, WHICH IS D9's OTHER HALF
-----------------------------------------------------------------------------
`net=$(git diff-tree -r --raw "$baseline" HEAD)` (:157) and the `${baseline}
..HEAD` reasoning around it use `HEAD`, not `$current`. On a `pull_request`
event `HEAD` is the merge of the branch tip WITH the target branch, so the net
diff carries every change that landed on main since the branch point. Unless
main has not moved at all, the net diff is not gitlink-only and the run reports

    pointer_bump_only=false -- net diff vs baseline is not gitlink-only

for a branch whose own commits are pointer-only. The walk was taught about the
merge commit; the proof it feeds was not. Driven in the differential
(`test_defect_b_...`).

-----------------------------------------------------------------------------
DEFECT C -- A `.gitmodules` WITH NO `submodule.*.path` AT ALL IS A HARD EXIT,
NOT A FAIL-SAFE
-----------------------------------------------------------------------------
Every other doubt in this script degrades to `pointer_bump_only=false` and exit
0. This one does not:

    sm_key=$(git config -f .gitmodules --get-regexp '^submodule\\..*\\.path$' |
        awk -v p="$sm_path" '$2 == p {print $1}')
    [[ -n "$sm_key" ]] || no_fast_path "no .gitmodules entry for $sm_path"

`git config --get-regexp` exits 1 when it matches nothing, `pipefail` promotes
that to the pipeline's status, the status becomes the ASSIGNMENT's, and `set -e`
ends the script -- with exit 1, no message of its own, and the guard on the very
next line never consulted. The guard can only ever fire when `.gitmodules`
contains at least one submodule path and none of them is this one.

The twin's own comment at :167-169 records fixing the neighbouring version of
this ("with `-r` an empty lookup exits 0, so the no-entry error could never
fire"). The remaining half is the case where the file is missing or empty, which
is exactly the state a removed-but-not-cleaned submodule leaves behind.
Reproduced here, not repaired.

-----------------------------------------------------------------------------
DEFECT D -- A NON-NUMERIC CHECK-RUNS ANSWER IS A HARD EXIT TOO
-----------------------------------------------------------------------------
`[[ "${green:-0}" -ge 1 ]]` (:154) is ARITHMETIC EVALUATION, so a BARE WORD in
that string is a VARIABLE REFERENCE. Under `set -u` an unset one ends the
script. Driven 2026-09-14 through the twin with a `gh` stub answering `null`:

    <twin>: line 154: null: unbound variable
    rc=1, stdout empty

Exit 1, nothing on stdout, and no message of the script's own -- against exit 0
with a reason, which is what every other doubt in this file produces. Not
reachable through today's `gh --jq '[...] | length'`, which answers with a
number or exits non-zero; one shape change in that jq program away, and the
same class as DEFECT C. A MALFORMED NUMBER is different and benign: `08` and
`1a` draw bash's `value too great for base` complaint, evaluate FALSE, and the
run carries on to the ordinary refusal. Both halves are reproduced.

-----------------------------------------------------------------------------
WHAT IS BYTE-IDENTICAL, AND THE TWO THINGS THAT ARE NOT
-----------------------------------------------------------------------------
Every `pointer_bump_only=` line, every `no_fast_path` reason, the proof string,
the three step-summary lines and both `key=value` pairs on stdout are this
script's own literal strings and are reproduced byte for byte on the same
stream.

TWO DIVERGENCES, both a bash DIAGNOSTIC carrying a bash line number: an
`--output` file that cannot be appended to, and DEFECT D's `unbound variable`.
Each prints the same words on the same stream with the same exit status, minus
the `<file>: line <n>:` prefix, and the differential normalises exactly that
prefix and nothing else. DEFECT C's `set -e` exit needs no divergence at all:
bash prints nothing there, and neither does this.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `WALK_CAP=5` (twin :44). The deepen asks for WALK_CAP + 1 because the walk
# needs each commit's PARENT as well as the commit.
WALK_CAP = 5

# The gitlink mode pair `git diff-tree -r --raw` prints for a submodule pointer that moved (twin :136, :158). `-r` is load-bearing in the twin's own words: without it a nested gitlink change reports as its parent TREE (`:040000 040000 ... private`) and never matches this prefix.
GITLINK_PREFIX = ":160000 160000 "

# `check_name='CI Complete'` and the reducing `--jq` (twin :149-152).
CHECK_NAME = "CI Complete"
GREEN_JQ = '[.check_runs[] | select(.conclusion == "success")] | length'
TREE_JQ = ".commit.tree.sha"
STATUS_JQ = ".status"

# `jq -r '.pull_request.head.sha // empty'` (twin :92). `// empty` is what makes an absent field print nothing rather than the string `null`.
HEAD_SHA_JQ = ".pull_request.head.sha // empty"

# `sed -E 's#\.git$##; s#.*[:/]([^/]+/[^/]+)$#\1#'` (twin :175). Two programs in
# one argument, applied in order.
REPO_SLUG_SED = r"s#\.git$##; s#.*[:/]([^/]+/[^/]+)$#\1#"

# The two output keys (twin :57-58, :207-208), in the order they are written.
KEY_POINTER = "pointer_bump_only"
KEY_BASELINE = "baseline_sha"

# `case "$status" in identical | ahead)` (twin :192-195). `compare BASE...HEAD` reports HEAD relative to BASE, so main being 'ahead' of (or 'identical' to) NEW means NEW is an ancestor of main. 'behind' and 'diverged' mean unmerged or drifted.
MERGED_STATUSES = ("identical", "ahead")

# The three `GITHUB_STEP_SUMMARY` lines (twin :202-204).
SUMMARY_HEADING = "### Pointer-bump fast path"

# A bash NAME, used to tell "this expression mentions an unset variable" from "this expression is malformed". The lookbehind keeps the `a` in `1a` out: that is a bad NUMBER, and bash treats the two cases differently.
BASH_NAME = re.compile(r"(?<![0-9A-Za-z_])[A-Za-z_][A-Za-z0-9_]*")

# A complete bash arithmetic literal: optional sign, then hex, octal or decimal.
BASH_NUMBER = re.compile(r"^[+-]?(?:0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*)$")

# The four defects in the module docstring, as constants a test can assert by name instead of restating the sentence.
THE_HEAD_GUARD_IS_UNREACHABLE_ON_A_PULL_REQUEST = True
STEP_THREE_STILL_COMPARES_AGAINST_THE_MERGE_COMMIT = True
AN_EMPTY_GITMODULES_IS_A_HARD_EXIT_NOT_A_FAIL_SAFE = True
A_NON_NUMERIC_CHECK_RUNS_ANSWER_IS_A_HARD_EXIT_TOO = True


class FastPathRefusedError(Exception):
    """`no_fast_path <reason>` (twin :55-60): a reason, two outputs, exit 0."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BashUnboundError(Exception):
    """`set -u` firing inside an arithmetic evaluation. FATAL, exit 1."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class BashExitError(Exception):
    """`set -e`, or the guarded `exit 0` at twin :123.

    `code` is the status the twin would leave with. DEFECT C is the only path
    that reaches this with a non-zero code and no message.
    """

    def __init__(self, code: int) -> None:
        super().__init__("exit %d" % code)
        self.code = code


def short(sha: str) -> str:
    """`${sha:0:7}`, which is a SUBSTRING and not `git rev-parse --short`.

    The difference matters for an empty or malformed value: bash slices whatever
    is there and produces a shorter string rather than failing.
    """
    return sha[:7]


def _flush() -> None:
    sys.stdout.flush()
    sys.stderr.flush()


def git(args: list[str], *, quiet_stderr: bool = False) -> tuple[int, str]:
    """One `git` call as `$(...)`: stdout captured, trailing newlines stripped.

    stderr is INHERITED unless the caller asked for `2>/dev/null`, because the
    twin lets git explain itself on every call that is not explicitly silenced.
    """
    _flush()
    proc = subprocess.run(
        ["git", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL if quiet_stderr else None,
        check=False,
    )
    return proc.returncode, proc.stdout.decode("utf-8", "surrogateescape").rstrip("\n")


def gh_api(args: list[str], token: str) -> tuple[int, str]:
    """`GH_TOKEN="${VAR:-}" gh api ... 2>/dev/null` (twin :149, :178, :189).

    THE ASSIGNMENT IS UNCONDITIONAL IN THE TWIN, so `GH_TOKEN` is exported as
    the EMPTY STRING when the source variable is unset, which is not the same as
    leaving it out: `gh` sees a set-but-empty token and refuses differently from
    how it refuses with no token at all. Reproduced.
    """
    _flush()
    env = dict(os.environ)
    env["GH_TOKEN"] = token
    proc = subprocess.run(
        ["gh", "api", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
        check=False,
    )
    return proc.returncode, proc.stdout.decode("utf-8", "surrogateescape").rstrip("\n")


def has_non_gitlink(raw: str) -> bool:
    """`grep -vE '^:160000 160000 ' <<<"$raw" | grep -q .` (twin :136, :158).

    THREE BASH FACTS, none of them regex:

      * A herestring appends a newline, so an EMPTY `raw` is one EMPTY line.
      * `grep -q .` needs a line with at least one character, so that empty line
        does not match and the predicate is False.
      * The pattern is anchored with no alternation, so it is a prefix test.
        (The house rule about `grep -E` returning silent false zeros applies to
        an anchor ALTERNATED with a negated class; there is no alternation
        here, and both sides run the same binary in the twin anyway.)
    """
    return any(line and not line.startswith(GITLINK_PREFIX) for line in raw.split("\n"))


def awk_field(text: str, index: int) -> str:
    """`awk '{print $N}'` on a single line, with awk's default FS.

    awk's default field splitting is on runs of blanks and tabs with leading and
    trailing runs ignored, which is exactly `str.split()`. A field past the end
    prints EMPTY rather than erroring, which is the behaviour the twin leans on
    when a `diff-tree` line is malformed.
    """
    fields = text.split()
    return fields[index - 1] if 0 < index <= len(fields) else ""


def read_tab_pair(line: str) -> tuple[str, str]:
    """`IFS=$'\\t' read -r meta sm_path` (twin :163).

    TAB IS IFS WHITESPACE, so bash strips leading and trailing runs of it and
    treats an interior run as ONE delimiter. The last variable takes the rest of
    the line, so a path containing a tab would arrive whole.
    """
    stripped = line.strip("\t")
    if not stripped:
        return "", ""
    meta, sep, rest = stripped.partition("\t")
    if not sep:
        return meta, ""
    return meta, rest.lstrip("\t")


def submodule_key(config_lines: str, sm_path: str) -> str:
    """`awk -v p="$sm_path" '$2 == p {print $1}'` over `--get-regexp` output.

    EVERY MATCHING LINE IS PRINTED, not just the first, so two `.gitmodules`
    entries pointing at one path would produce a two-line value. Reproduced,
    because the caller then does `${sm_key%.path}` on the whole thing.
    """
    keys = [
        awk_field(line, 1)
        for line in config_lines.split("\n")
        if line and awk_field(line, 2) == sm_path
    ]
    return "\n".join(keys)


def strip_path_suffix(sm_key: str) -> str:
    """`${sm_key%.path}`: remove the SHORTEST matching suffix, once, if present."""
    return sm_key.removesuffix(".path")


class Outputs:
    """`write_output` (twin :46-53): the pair goes to stdout ALWAYS, and to
    `$OUTPUT_FILE` as well when `--output` named one.

    THE FILE IS APPENDED TO, never truncated, because the caller's `$GITHUB_OUTPUT`
    already holds other steps' pairs.
    """

    def __init__(self, output_file: str) -> None:
        self.output_file = output_file

    def write(self, key: str, value: str) -> None:
        line = "%s=%s" % (key, value)
        if self.output_file:
            try:
                with open(self.output_file, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except OSError as exc:
                # bash prints `<script>: line 50: <file>: <reason>` and `set -e` ends the run. Same three facts, same stream, same status.
                print(
                    "detect-pointer-bump.sh: %s: %s" % (self.output_file, exc.strerror),
                    file=sys.stderr,
                    flush=True,
                )
                raise BashExitError(1) from exc
        print(line, flush=True)


def resolve_current(event_path: str, is_shallow: bool) -> str:
    """Twin :90-112: the branch tip out of the event payload, or "".

    THE WHOLE OF D9's FIX LIVES HERE. On a `pull_request` event
    `actions/checkout` hands over the synthetic two-parent `refs/pull/N/merge`
    commit, so `git rev-parse HEAD` names a MERGE commit, `${current}^2`
    resolves on the very first iteration and the walk aborts before it has
    looked at anything. `github.event.pull_request.head.sha` is the real branch
    tip.

    NO `--depth` ON A FULL CLONE, and the twin's comment measures why: one such
    line took a complete checkout from 2467 reachable commits to 114 and wrote a
    graft, which broke a topology gate several steps later in the same job.

    Every failure here yields "", which sends the caller back to
    `git rev-parse HEAD`: the OLD behaviour, which fails closed to
    `pointer_bump_only=false` rather than fast-pathing something unverified.
    """
    if not event_path or not os.access(event_path, os.R_OK):
        return ""
    if shutil.which("jq") is None:
        return ""

    _flush()
    proc = subprocess.run(
        ["jq", "-r", HEAD_SHA_JQ, event_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    current = proc.stdout.decode("utf-8", "surrogateescape").rstrip("\n")
    if not current:
        return ""

    if not commit_exists(current):
        if is_shallow:
            git(["fetch", "--quiet", "--depth=50", "origin", current], quiet_stderr=True)
        else:
            git(["fetch", "--quiet", "origin", current], quiet_stderr=True)
    if not commit_exists(current):
        return ""
    return current


def commit_exists(sha: str) -> bool:
    """`git rev-parse --verify --quiet "${sha}^{commit}" >/dev/null 2>&1`."""
    status, _ = git(["rev-parse", "--verify", "--quiet", "%s^{commit}" % sha], quiet_stderr=True)
    return status == 0


def is_shallow_clone() -> bool:
    """`[[ -f "$(git rev-parse --git-dir)/shallow" ]]` (twin :66).

    A FAILING `rev-parse` LEAVES AN EMPTY SUBSTITUTION, so the test becomes
    `-f /shallow`, which is false. The twin therefore treats "not a git
    repository" as "not shallow" and carries on to fail later; reproduced.
    """
    _, git_dir = git(["rev-parse", "--git-dir"])
    return os.path.isfile(os.path.join(git_dir, "shallow"))


def find_baseline(current: str, head_sha: str) -> tuple[str, str]:
    """Step 1, the walk (twin :126-146). Returns `(baseline, "")` or `("", reason)`.

    A reason is `no_fast_path`'s argument; the caller raises with it rather than
    this function exiting, so the walk stays testable without a subprocess.

    THE LOOP RUNS AT MOST `WALK_CAP` TIMES and the FIRST non-pointer commit ends
    it. `head_sha` is compared rather than re-read on every iteration, which the
    twin hoisted deliberately: an unguarded `$(git rev-parse HEAD)` inside the
    loop would yield "" on failure, read as "not HEAD", and let the walk
    continue past the commit it exists to stop at. DEFECT A is about WHICH
    commit `head_sha` names, not about the hoist.
    """
    baseline = ""
    for _ in range(WALK_CAP):
        status, _out = git(["rev-parse", "--verify", "--quiet", "%s^2" % current])
        if status == 0:
            return "", "merge commit %s in the walk" % short(current)

        status, parent = git(["rev-parse", "--verify", "--quiet", "%s^" % current])
        if status != 0:
            return "", "parent of %s unavailable" % short(current)

        rc, raw = git(["diff-tree", "-r", "--raw", parent, current])
        del rc  # unchecked in the twin: the emptiness test below is the guard
        if not raw:
            return "", "empty commit %s" % short(current)

        if has_non_gitlink(raw):
            # The first commit that touches anything beyond existing gitlinks.
            if current == head_sha:
                return "", "HEAD is not a pointer-only commit"
            break

        baseline = parent
        current = parent

    if not baseline:
        return "", "no baseline within %d commits" % WALK_CAP
    return baseline, ""


def repo_slug(sm_url: str) -> str:
    """`sed -E 's#\\.git$##; s#.*[:/]([^/]+/[^/]+)$#\\1#' <<<"$sm_url"` (twin :175)."""
    _flush()
    proc = subprocess.run(
        ["sed", "-E", REPO_SLUG_SED],
        input=(sm_url + "\n").encode("utf-8"),
        stdout=subprocess.PIPE,
        check=False,
    )
    return proc.stdout.decode("utf-8", "surrogateescape").rstrip("\n")


def verify_moves(net: str, pat_token: str) -> str:
    """Step 3's loop (twin :163-197). Returns the proof string.

    Raises `FastPathRefusedError` for every doubt, and `BashExitError` for the one
    that is not a doubt but a hard exit (DEFECT C).
    """
    proof = ""
    for line in net.split("\n"):
        meta, sm_path = read_tab_pair(line)
        if not meta:
            continue
        old_sha = awk_field(meta, 3)
        new_sha = awk_field(meta, 4)

        # DEFECT C: `git config --get-regexp` exits 1 on no match, `pipefail` promotes it to the assignment's status, and `set -e` ends the script before the guard on the next line can say anything.
        status, config_lines = git(
            ["config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$"]
        )
        if status != 0:
            raise BashExitError(status)
        sm_key = submodule_key(config_lines, sm_path)
        if not sm_key:
            raise FastPathRefusedError("no .gitmodules entry for %s" % sm_path)

        status, sm_url = git(
            ["config", "-f", ".gitmodules", "--get", "%s.url" % strip_path_suffix(sm_key)]
        )
        if status != 0:
            raise FastPathRefusedError("no url for %s in .gitmodules" % strip_path_suffix(sm_key))

        sm_repo = repo_slug(sm_url)
        if not sm_repo:
            raise FastPathRefusedError("cannot parse repo from %s" % sm_url)

        status, tree_old = gh_api(
            ["repos/%s/commits/%s" % (sm_repo, old_sha), "--jq", TREE_JQ], pat_token
        )
        if status != 0:
            raise FastPathRefusedError("cannot read %s@%s" % (sm_repo, short(old_sha)))
        status, tree_new = gh_api(
            ["repos/%s/commits/%s" % (sm_repo, new_sha), "--jq", TREE_JQ], pat_token
        )
        if status != 0:
            raise FastPathRefusedError("cannot read %s@%s" % (sm_repo, short(new_sha)))
        if tree_old != tree_new:
            raise FastPathRefusedError(
                "%s trees differ (%s vs %s -- submodule main moved?)"
                % (sm_path, short(old_sha), short(new_sha))
            )

        status, compare = gh_api(
            ["repos/%s/compare/%s...main" % (sm_repo, new_sha), "--jq", STATUS_JQ], pat_token
        )
        if status != 0:
            raise FastPathRefusedError("compare failed for %s" % sm_repo)
        if compare not in MERGED_STATUSES:
            raise FastPathRefusedError(
                "%s new commit not on %s main (status: %s)" % (sm_path, sm_repo, compare)
            )

        proof += "%s %s->%s (tree-identical, on %s main); " % (
            sm_path,
            short(old_sha),
            short(new_sha),
            sm_repo,
        )
    return proof


def write_summary(summary_file: str, baseline: str, proof: str) -> None:
    """The `GITHUB_STEP_SUMMARY` block (twin :200-206), appended, three lines."""
    if not summary_file:
        return
    try:
        with open(summary_file, "a", encoding="utf-8") as handle:
            handle.write(SUMMARY_HEADING + "\n")
            handle.write(
                "Content-identical to `%s` (successful CI Complete). Moves: %s\n"
                % (baseline, proof)
            )
            handle.write(
                "Expensive jobs are skipped; ci-complete accepts their skips via "
                "POINTER_BUMP_ONLY.\n"
            )
    except OSError as exc:
        print(
            "detect-pointer-bump.sh: %s: %s" % (summary_file, exc.strerror),
            file=sys.stderr,
            flush=True,
        )
        raise BashExitError(1) from exc


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        exc.report()
        return exc.code
    outputs = Outputs(args.get("ARG_OUTPUT", ""))

    root = str(common.repo_root())
    # `cd "$REPO_ROOT"` (twin :42) under `set -e`. bash names the file and a
    # line number; same three facts, same stream, same status.
    try:
        os.chdir(root)
    except OSError as exc:
        print(
            "detect-pointer-bump.sh: cd: %s: %s" % (root, exc.strerror),
            file=sys.stderr,
            flush=True,
        )
        return 1

    def refuse(reason: str) -> int:
        """`no_fast_path`: the reason on stderr, both keys, exit 0."""
        log.info("%s=false -- %s" % (KEY_POINTER, reason))
        outputs.write(KEY_POINTER, "false")
        outputs.write(KEY_BASELINE, "")
        return 0

    try:
        if os.environ.get("GITHUB_EVENT_NAME", "") != "pull_request":
            return refuse("not a pull_request event")

        shallow = is_shallow_clone()
        if shallow:
            status, _ = git(
                [
                    "fetch",
                    "--no-recurse-submodules",
                    "--quiet",
                    "--deepen=%d" % (WALK_CAP + 1),
                    "origin",
                ],
                quiet_stderr=True,
            )
            if status != 0:
                return refuse("could not deepen history")

        current = resolve_current(os.environ.get("GITHUB_EVENT_PATH", ""), shallow)
        if not current:
            # `[[ -n "$current" ]] || current=$(git rev-parse HEAD)`. The
            # assignment is the LAST member of the `||` list, so `set -e` does reach it: a failing rev-parse ends the run with git's status.
            status, current = git(["rev-parse", "HEAD"])
            if status != 0:
                raise BashExitError(status)

        # DEFECT A: this is `git rev-parse HEAD`, which on a pull_request event is the synthetic merge commit and therefore never equal to `current`.
        status, head_sha = git(["rev-parse", "HEAD"])
        if status != 0:
            log.info("git rev-parse HEAD failed; cannot verify the walk's own stopping point")
            outputs.write(KEY_POINTER, "false")
            outputs.write(KEY_BASELINE, "")
            return 0

        baseline, reason = find_baseline(current, head_sha)
        if reason:
            return refuse(reason)

        # --- Step 2: the baseline must have passed full CI -------------------
        status, green = gh_api(
            [
                "-X",
                "GET",
                "repos/%s/commits/%s/check-runs"
                % (os.environ.get("GITHUB_REPOSITORY", ""), baseline),
                "-f",
                "check_name=%s" % CHECK_NAME,
                "--jq",
                GREEN_JQ,
            ],
            os.environ.get("CHECKS_TOKEN", ""),
        )
        if status != 0:
            return refuse("check-runs lookup failed for baseline %s" % short(baseline))
        # `[[ "${green:-0}" -ge 1 ]]`: an empty answer is 0, and a non-numeric
        # one is an unset variable, which is also 0.
        try:
            enough = _at_least_one(green)
        except BashUnboundError as exc:
            # DEFECT D: bash prints `<script>: line 154: <name>: unbound variable` and stops, with no output pair written at all. Same three facts, same stream, same status.
            print(
                "detect-pointer-bump.sh: %s: unbound variable" % exc.name,
                file=sys.stderr,
                flush=True,
            )
            raise BashExitError(1) from exc
        if not enough:
            return refuse("baseline %s has no successful CI Complete" % short(baseline))

        # --- Step 3: every net gitlink move is tree-identical and merged ----- DEFECT B: `HEAD`, not `$current`.
        _, net = git(["diff-tree", "-r", "--raw", baseline, "HEAD"])
        if has_non_gitlink(net):
            return refuse("net diff vs baseline is not gitlink-only")

        proof = verify_moves(net, os.environ.get("GITHUB_PAT", ""))

        log.info(
            "%s=true -- baseline %s passed CI Complete; %s" % (KEY_POINTER, short(baseline), proof)
        )
        write_summary(os.environ.get("GITHUB_STEP_SUMMARY", ""), baseline, proof)
        outputs.write(KEY_POINTER, "true")
        outputs.write(KEY_BASELINE, baseline)
    except FastPathRefusedError as exc:
        # `no_fast_path` can itself fail, on an `--output` file it cannot append to. bash would exit with 1 there too, from inside the function.
        try:
            return refuse(exc.reason)
        except BashExitError as inner:
            return inner.code
    except BashExitError as exc:
        return exc.code
    return 0


def _at_least_one(green: str) -> bool:
    """`[[ "${green:-0}" -ge 1 ]]`, which is ARITHMETIC EVALUATION under `set -u`.

    Probed against real bash on 2026-09-14 rather than reasoned about:

        [$v]      exit  outcome
        [3]       0     TRUE
        [0]       0     FALSE
        []        0     FALSE          (the `:-0` default)
        [-2]      0     FALSE
        [010]     0     TRUE           (octal 8)
        [0x10]    0     TRUE           (hex 16)
        [08]      0     FALSE, after `[[: 08: value too great for base`
        [1a]      0     FALSE, after the same complaint
        [null]    1     `bash: line 154: null: unbound variable`   <- FATAL
        [a b]     1     `bash: line 154: a: unbound variable`      <- FATAL

    DEFECT D LIVES IN THE LAST TWO ROWS. A bare word is a VARIABLE REFERENCE,
    and an unset one under `set -u` ends the script with exit 1, NO
    `pointer_bump_only` pair on stdout at all, and no message of the script's
    own -- so the caller gets a failed step rather than the fail-safe `false`
    every other doubt in this file produces. `gh --jq '... | length'` answers
    with a number today, and `gh` exits non-zero when it cannot, so the row is
    not reachable through the current call; it is one shape change in the
    reducing jq program away, and it is the same class as DEFECT C.
    """
    stripped = green.strip()
    if stripped == "":
        return False
    if BASH_NUMBER.match(stripped):
        negative = stripped.startswith("-")
        digits = stripped.lstrip("+-")
        if digits[:2].lower() == "0x":
            value = int(digits, 16)
        elif digits.startswith("0") and digits != "0":
            value = int(digits, 8)
        else:
            value = int(digits)
        return (-value if negative else value) >= 1
    name = BASH_NAME.search(stripped)
    if name:
        raise BashUnboundError(name.group(0))
    if stripped[0].isdigit():
        # `[[: 08: value too great for base (error token is "08")`, verbatim apart from bash's own `<file>: line <n>:` prefix.
        print(
            '%s: [[: %s: value too great for base (error token is "%s")'
            % ("detect-pointer-bump.sh", stripped, stripped),
            file=sys.stderr,
            flush=True,
        )
    return False


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
