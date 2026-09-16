"""How many Claude review passes a PR may spend, from `.ci/scripts/lib/common.sh`.

THE SECOND HALF OF THE TWIN. `.ci/scripts/lib/common.sh` is two libraries in one
file: lines 1-514 are the refuse-early base library every script sources
(ported next door in `core.common`), and lines 516-772 are this -- the review
budget, thirteen functions and four constants that decide whether the review
workflow may spend money on another pass.

    common.sh:534      REVIEW_CAP_TIERS
    common.sh:537-550  review_cap_for
    common.sh:589-596  review_report_count
    common.sh:603-617  review_epic_ids
    common.sh:661-663  REVIEW_ATTEMPT_INFRA_CLASSES / _FREE_REATTEMPTS / _MAX
    common.sh:666-672  review_attempt_class_is_infra
    common.sh:681-703  review_attempt_states
    common.sh:708-720  review_chargeable_attempts
    common.sh:723-729  review_head_attempt_state
    common.sh:736-743  review_head_is_exhausted
    common.sh:746-748  review_spent_attempt_count
    common.sh:756-761  review_spend_total
    common.sh:766-772  pr_diff_loc

IT IS LIVE. `.ci/scripts/review/review-status.sh:343-347` and
`.ci/scripts/review/claude-review-gate.sh:831-860` are the two callers, both
wired into workflows: `.github/workflows/review-status.yml:115` (which creates
the required "Review Complete" check run) and
`.github/workflows/claude-review-reusable.yml:277`.

THE FILE'S OWN COMMENT SAYS WHY IT IS ONE FILE, and it is worth quoting because
it is also why this port keeps them together (common.sh:530-533): "THIS LIVES IN
THE SHARED LIB ON PURPOSE. claude-review-gate.sh decides whether to run a review
and review-status.sh reports whether the cap is reached; the two disagreeing
about the cap resurrects exactly the deadlock review-status.sh was written to
prevent. One table, one function, both callers."

==========================================================================
DEFECT 1 -- WAS THE HEADLINE, FIXED 2026-09-10 IN THE TWIN AND HERE IN LOCKSTEP
==========================================================================
`review_spend_total` -- the CAP NUMERATOR -- used to RETURN 0 WITH EXIT 0 WHEN
`gh` FAILED. Driven against the live twin with a `gh` on PATH that writes
"HTTP 403: API rate limit exceeded" to stderr and exits 1, BEFORE the fix:

    review_report_count 553      -> count=[0]     rc=0
    review_attempt_states 553 P  -> states=[]     rc=0
    pr_diff_loc 553              -> loc=[0]       rc=0
    review_spend_total 553 P     -> total=[0]     rc=0

Each was `gh ... 2>/dev/null | ... || true`. `pipefail` is on (common.sh:11), so
the pipeline did fail -- and `|| true` threw that away AFTER `wc -l` had
already printed `0`.

WHY THIS WAS NOT MERELY A BUG BUT A CONTRADICTION. One hundred and sixty lines
above, in the same file, `_gh_probe`'s own header (common.sh:424-429) condemns
exactly this spelling:

    "Nine call sites across the review, attribution and submodule-branch gates
     were spelled `X=$(gh api ... 2>/dev/null || echo "[]")`. A rate limit, an
     expired token or a network blip produced the same value as 'this PR has no
     review comments', so the gate printed its success message and exited 0."

BLAST RADIUS, MEASURED RATHER THAN ESTIMATED. Four live call sites, all
behind a workflow:

  review-status.sh:343     review_count="$(review_spend_total ...)"
  review-status.sh:346     pr_loc="$(pr_diff_loc "$pr")"
  review-status.sh:364     review_head_is_exhausted "$(review_attempt_states ...)"
  claude-review-gate.sh:831 reports_posted=$(review_report_count ...)
  claude-review-gate.sh:835 attempt_states=$(review_attempt_states ...)
  claude-review-gate.sh:858 review_count=$(review_spend_total ...)
  claude-review-gate.sh:859 pr_loc=$(pr_diff_loc "$pr")

Two consequences the bug used to have, and the second is the one that would
have cost a human:

  1. In `claude-review-gate.sh`, a numerator of 0 meant the cap was never
     reached, so a rate-limited run dispatched ANOTHER full review. The file
     itself prices a review at "$4.66" (common.sh:566).
  2. In `review-status.sh`, the DEADLOCK GUARD is the thing that keeps a capped
     PR mergeable, and it only fires when the cap is seen as reached. common.sh
     :623-632 records what happened the last time the numerator was wrong:
     "On PR #553 (2026-08-07) that read as 3/3 in the gate and 0/3 in
     review-status simultaneously ... The PR was green, ready and thread-clean,
     and permanently unmergeable through no fault of its author: exactly the
     outcome that guard exists to prevent." A transient rate limit reproduced
     that state, and `pr_diff_loc` failing to 0 at the same moment ALSO dropped
     the denominator to the smallest tier, which made the disagreement worse
     rather than cancelling it. `pr_diff_loc` itself was left unchanged (see
     below); only the three functions whose swallow moved the NUMERATOR were
     fixed, which is the direction that mattered.

THE SWALLOW WAS NOT ONLY ABOUT `gh`. Driven the same day, with `gh` working
but `GITHUB_REPOSITORY` unset:

    review_spend_total 553 P "" 4
    common.sh: line 592: GITHUB_REPOSITORY: unbound variable
    4

The numerator's fetch used to abort inside a command substitution, `posted`
stayed empty, `$(( + 4))` was 4, and the function returned 4 with EXIT 0 -- an
undercount produced by a hard abort. There was no `gh` in that path at all, so
the `gh_retry` fix alone would not have closed it; it closed anyway, as a side
effect of the new `|| return 1` on every assignment that captures one of these
functions' output, which now propagates ANY failure of the command
substitution, unbound-variable aborts included, not just a nonzero `gh` exit.

FIXED 2026-09-10, IN THE TWIN, IN LOCKSTEP WITH THIS PORT AND ITS TESTS.
`review_report_count`, `review_attempt_states`, `review_spent_attempt_count`
and `review_spend_total` now route their `gh` calls through `gh_retry` (the
exact pattern `_gh_probe`'s own header already argued for) and propagate a
failure as a real nonzero return via `|| return 1` on the capturing
assignment, instead of `... || true`. Verified live, both before and after:
the same four failing-`gh` drives above now exit nonzero with the retry/error
text `_gh_probe` already produces, and a genuinely empty (not failed) result
still answers `0`/empty correctly -- checked separately, because a naive fix
piping through a here-string (`wc -l <<<"$out"`) would count an empty result
as ONE line, not zero, the same trap `blocker-validator.sh`'s anti-vacuity
check fell into elsewhere in this file family. `report_count`, `attempt_
states`, `spent_attempt_count` and `spend_total` here already raised
`core.ghx.GhError` rather than answering 0 -- the PORT was ahead of the twin,
not behind it -- so this fix makes the two sides AGREE rather than requiring
any change here. `test_core_review_budget.py` pins the agreement on both
sides now, in place of the divergence it used to pin.

`pr_diff_loc` is UNCHANGED, DELIBERATELY, because common.sh:764-765 states its
0 as a decision: "Failing to 0 puts an unreadable PR in the SMALLEST bucket,
which is the conservative direction: it spends fewer review passes, never
more." That reasoning holds on its own terms once the numerator (the three
functions above) is trustworthy again, which it now is.
`DIFF_LOC_FAILS_TO_ZERO` below records the twin's rule by name, and
`diff_loc(..., on_error=0)` is available for a caller that wants it explicitly.

==========================================================================
DEFECT 2 -- A NON-NUMERIC ATTEMPT COUNT ABORTS UNDER `set -u`
==========================================================================
`review_chargeable_attempts` computes `$((n - REVIEW_FREE_REATTEMPTS_PER_HEAD))`
(common.sh:714). Under `nounset`, bash arithmetic treats a non-numeric word as a
VARIABLE NAME, so a states row of `a<TAB>zz<TAB>unknown` dies:

    common.sh: line 717: zz: unbound variable

LATENT, and the reason it is latent is worth recording so nobody "fixes" the awk
by accident: the producer is `review_attempt_states`, whose awk guards the
capture with `/^attempts:[[:space:]]*[0-9]+/` and then forces `n = line + 0`, so
a marker carrying `attempts: zz` yields `n=1` rather than `zz` (driven). Only a
hand-built states string reaches the crash. Reproduced as a `ValueError` here
rather than as an abort.

==========================================================================
WHAT ELSE WAS DRIVEN AND IS REPRODUCED VERBATIM
==========================================================================
  * `review_cap_for` coerces ANY non-`^[0-9]+$` input to 0, so `abc`, the empty
    string and `-5` all get the SMALLEST budget, 3. Its trailing `echo 3`
    (common.sh:549) is unreachable, because the last tier's bound is empty and
    the empty bound is the catch-all.
  * `review_chargeable_attempts` on empty input answers 0 rather than dying,
    because a bash here-string appends a newline and the loop's
    `[[ -n "$sha" ]] || continue` absorbs the one blank line it produces. Same
    here-string property that made `blocker-validator.sh`'s anti-vacuity check
    dead code; here it happens to be load-bearing in the right direction.
  * The infra underflow CLAMPS: a head with 1 attempt of an infra class charges
    `max(0, 1 - 2) = 0`, not -1 (driven: a 1-infra plus a 5-unknown head totals
    5).
  * `review_head_attempt_state` returns the LAST matching row, not the first
    (driven), and defaults to the two characters `"0 "` -- so `review_head_is_
    exhausted` splits an empty class out of it and correctly answers "not
    exhausted".
  * `review_head_is_exhausted` can only ever be true for an INFRA class.
    common.sh:733-735 says why: "a non-infra reportless attempt was never
    per-head blocked, and making it one here would be a NEW restriction wearing
    the costume of a relaxation."
  * `REVIEW_ATTEMPT_INFRA_CLASSES` is a SPACE-SEPARATED STRING iterated
    unquoted, so a multi-word class could never match (common.sh:655-660 says so
    on purpose). `INFRA_CLASSES` here is a tuple and a test pins that no member
    contains a space, which is the same rule made checkable.
  * `review_epic_ids` anchors its grep at `^`, so an INDENTED `PR-TASK:` line is
    invisible (driven: `  PR-TASK: 112233` yields nothing), and it accepts
    lowercase hex only (`PR-TASK: ABCDEF` yields nothing). Both reproduced.
  * `review_epic_ids` maps `/` to `-` in the branch name before building the
    snapshot path, so `feat/x` reads `agent/pr/feat-x.md` (driven).
  * `review_spend_total` strips ALL whitespace from both operands before adding
    (`${posted//[[:space:]]/}`), which is what makes `wc -l`'s leading spaces on
    macOS harmless. Reproduced.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

from rediacc_ci import paths
from rediacc_ci.core import ghx

# `REVIEW_CAP_TIERS='10000:3 50000:5 :7'` (common.sh:534), as (bound, cap).
# `None` is the empty bound: the catch-all top tier. Order is the contract --
# the twin iterates and takes the first tier whose bound the value fits.
CAP_TIERS: tuple[tuple[int | None, int], ...] = ((10000, 3), (50000, 5), (None, 7))

# common.sh:549. Unreachable while the last tier's bound is empty, kept because
# removing it would silently change what happens if someone edits CAP_TIERS.
CAP_FALLBACK = 3

# `REVIEW_ATTEMPT_INFRA_CLASSES` (common.sh:661). A tuple, not a space-separated
# string, so the single-token rule the twin can only state in a comment is
# checkable: `test_core_review_budget.py` asserts no member contains a space.
INFRA_CLASSES = ("error_max_turns", "error_during_execution")

REVIEW_FREE_REATTEMPTS_PER_HEAD = 2  # common.sh:662
REVIEW_MAX_ATTEMPTS_PER_HEAD = 3  # common.sh:663

# `needle="**Claude finished"` (common.sh:590). The PRODUCER CONSTANT, written
# verbatim by claude-review-gate.sh. common.sh:560-573 records at length why
# this must never gain a content qualifier: the old one undercounted every
# measured PR (#551 counted 0 of 1, #550 5 of 7, #546 3 of 7, #543 1 of 9).
REPORT_NEEDLE = "**Claude finished"
REPORT_EPIC_NEEDLE = "**Claude finished (epic %s)"

# `select(.user.login | contains("github-actions"))` (common.sh:593).
REPORT_AUTHOR_SUBSTRING = "github-actions"

# The marker key and sentinel `review_attempt_states`' awk keys on
# (common.sh:688, :687).
ATTEMPT_KEY = "claude-review-attempt:"
ATTEMPT_EOF = "---REVIEW-ATTEMPT-EOF---"

# `grep -oE '^`?PR-TASK:[[:space:]]*[0-9a-f]{6,32}`?$'` (common.sh:615).
# ANCHORED at both ends, lowercase hex only. Both properties are driven.
EPIC_LINE = re.compile(r"^`?PR-TASK:[ \t]*([0-9a-f]{6,32})`?$")

# The override `review_epic_ids` honours (common.sh:610-611), so a test can point
# at a fixture without writing into the real tree.
PUBLISH_ROOT_ENV = "WORKLIST_PUBLISH_ROOT"

# common.sh:764-765's stated rule, named so a caller opts into it visibly rather
# than inheriting it. See DEFECT 1 for why "conservative" does not survive
# contact with a numerator that also fails to zero.
DIFF_LOC_FAILS_TO_ZERO = 0

_UNSIGNED = re.compile(r"[0-9]+")


class AttemptState:
    """One `<sha>\\t<attempts>\\t<class>` row from `review_attempt_states`."""

    __slots__ = ("attempts", "cls", "sha")

    def __init__(self, sha: str, attempts: int, cls: str) -> None:
        self.sha = sha
        self.attempts = attempts
        self.cls = cls

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AttemptState):
            return NotImplemented
        return (self.sha, self.attempts, self.cls) == (other.sha, other.attempts, other.cls)

    def __hash__(self) -> int:
        return hash((self.sha, self.attempts, self.cls))

    def __repr__(self) -> str:
        return "AttemptState(%r, %r, %r)" % (self.sha, self.attempts, self.cls)

    def tsv(self) -> str:
        """The twin's wire format, so a caller can round-trip through it."""
        return "%s\t%d\t%s" % (self.sha, self.attempts, self.cls)


# ---------------------------------------------------------------------------
# THE DENOMINATOR (common.sh:534-550)
# ---------------------------------------------------------------------------


def cap_for(changed_lines: str | int | None) -> int:
    """`review_cap_for` (common.sh:537-550). Review passes allowed for a diff.

    `[[ "$loc" =~ ^[0-9]+$ ]] || loc=0`, so anything that is not a run of digits
    becomes 0 and lands in the SMALLEST tier. `abc`, `""`, `-5` and `1e3` all
    answer 3 (driven). That is the conservative direction for this number and it
    is the twin's, so it is reproduced without comment beyond this one.

    The bands are inclusive at the top: 10000 -> 3, 10001 -> 5, 50000 -> 5,
    50001 -> 7 (driven at every boundary). common.sh:526-528 records that the
    50k-100k band lands in the TOP bucket deliberately, "a 60,000-line diff is
    not meaningfully easier to review than a 100,000-line one".
    """
    text = "" if changed_lines is None else str(changed_lines)
    loc = int(text) if _UNSIGNED.fullmatch(text) else 0
    for bound, cap in CAP_TIERS:
        if bound is None or loc <= bound:
            return cap
    return CAP_FALLBACK


# ---------------------------------------------------------------------------
# THE ATTEMPT LEDGER, pure (common.sh:666-743)
# ---------------------------------------------------------------------------


def class_is_infra(cls: str) -> bool:
    """`review_attempt_class_is_infra` (common.sh:666-672).

    An INFRA-CLASS failure is not a verdict on the code (common.sh:642-648): the
    harness ran out of turns or fell over, so the same head earns
    REVIEW_FREE_REATTEMPTS_PER_HEAD retries. Anything else, INCLUDING an empty
    class from a legacy marker, is not infra -- "we do not know why it died" is
    the case where retrying forever is most expensive.
    """
    return cls in INFRA_CLASSES


def parse_attempt_states(raw: str) -> list[AttemptState]:
    """The awk in `review_attempt_states` (common.sh:684-702), as a function.

    SEPARATED FROM THE FETCH ON PURPOSE. The awk is pure and the `gh` call is
    not, and it is the awk that carries every surprising rule below. Every one
    was driven by piping fixtures through the twin's own awk program on
    2026-09-10.

      * Records are separated by a line that is EXACTLY `---REVIEW-ATTEMPT-EOF---`.
        `END { flush() }` also emits a trailing partial record, so input with no
        final sentinel still yields its last marker.
      * The sha is taken from the FIRST line containing `claude-review-attempt:`
        in each record, and `&& sha == ""` means later ones in the same record
        are ignored. The match is UNANCHORED, so `<!-- claude-review-attempt: x
        -->` matches and the sha is the next whitespace-delimited word (`x`).
      * `attempts:` is anchored and requires DIGITS. A marker carrying
        `attempts: zz` therefore leaves the default of 1 rather than storing
        `zz`, which is what makes DEFECT 2 latent.
      * `class:` is anchored, matches with ZERO characters after the colon
        (`[[:space:]]*`), and may appear BEFORE the sha in the same record.
      * A record with no sha emits nothing: `flush()` tests `sha != ""`.
      * Defaults per record are `n = 1`, `cls = ""` -- a legacy marker written
        before the count existed "reads as one attempt of unknown class, which is
        the old behaviour exactly" (common.sh:679-680).
    """
    states: list[AttemptState] = []
    sha = ""
    attempts = 1
    cls = ""

    def flush() -> None:
        nonlocal sha, attempts, cls
        if sha != "":
            states.append(AttemptState(sha, attempts, cls))
        sha, attempts, cls = "", 1, ""

    for line in raw.split("\n"):
        if line == ATTEMPT_EOF:
            flush()
            continue
        if ATTEMPT_KEY in line and sha == "":
            # `sub(/.*claude-review-attempt:[[:space:]]*/, "", line)` is GREEDY,
            # so a line carrying the key twice keeps the text after the LAST one.
            tail = line.rsplit(ATTEMPT_KEY, 1)[1].lstrip(" \t")
            # `sub(/[[:space:]].*$/, "", line)` -- up to the first whitespace.
            sha = re.split(r"[ \t]", tail, maxsplit=1)[0]
        if re.match(r"^attempts:[ \t]*[0-9]+", line):
            attempts = int(re.match(r"^attempts:[ \t]*([0-9]+)", line).group(1))
        if re.match(r"^class:[ \t]*", line):
            cls = re.sub(r"^class:[ \t]*", "", line).rstrip(" \t")
    flush()
    return states


def chargeable_attempts(states: list[AttemptState]) -> int:
    """`review_chargeable_attempts` (common.sh:708-720). What the cap counts.

    An infra head is charged `attempts - REVIEW_FREE_REATTEMPTS_PER_HEAD`,
    CLAMPED at 0 (common.sh:714-715). common.sh:650-654 prices that: "Three
    attempts cost three attempts' money, and only one of them is charged -- a
    deliberate under-charge that keeps the loop moving. What stops that being
    unbounded is the per-head ceiling".

    Empty input answers 0 in both implementations, for different reasons: the
    twin because a here-string's trailing newline gives it one blank line its
    `[[ -n "$sha" ]] || continue` skips, this one because the list is empty.

    DEFECT 2 lives here in the twin. `attempts` is an `int` on this side, so a
    non-numeric count cannot reach the arithmetic at all; `attempts_from_tsv`
    below is where it is rejected, with a message instead of `zz: unbound
    variable`.
    """
    total = 0
    for state in states:
        charge = state.attempts
        if class_is_infra(state.cls):
            charge = max(0, state.attempts - REVIEW_FREE_REATTEMPTS_PER_HEAD)
        total += charge
    return total


def attempts_from_tsv(raw: str) -> list[AttemptState]:
    """Read the twin's `<sha>\\t<n>\\t<class>` wire format back into states.

    The seam DEFECT 2 lives on. The twin does `$((n - 2))` on whatever word sat
    in column two and, under `set -u`, dies with `zz: unbound variable` naming a
    line in a library the caller never opened. This raises a `ValueError` that
    names the row.
    """
    states: list[AttemptState] = []
    for line in raw.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        sha = parts[0]
        if not sha:
            continue
        count = parts[1] if len(parts) > 1 else "1"
        cls = parts[2] if len(parts) > 2 else ""
        if not _UNSIGNED.fullmatch(count):
            raise ValueError(
                "review_budget: attempt count %r is not a number, in row %r. The twin "
                "reaches `$((%s - 2))` with this and aborts with `%s: unbound variable` "
                "under `set -u` (common.sh:714)." % (count, line, count, count)
            )
        states.append(AttemptState(sha, int(count), cls))
    return states


def head_attempt_state(states: list[AttemptState], sha: str) -> tuple[int, str]:
    """`review_head_attempt_state` (common.sh:723-729). LAST match wins.

    The twin overwrites `out` on every match without breaking, so two rows for
    one sha give the second (driven). Its default is the literal two characters
    `"0 "`, which the caller then splits into `0` and the empty class; the tuple
    here says the same thing without the split.
    """
    found = (0, "")
    for state in states:
        if state.sha == sha:
            found = (state.attempts, state.cls)
    return found


def head_is_exhausted(states: list[AttemptState], sha: str) -> bool:
    """`review_head_is_exhausted` (common.sh:736-743). Infra classes only.

    `review_attempt_class_is_infra "$cls" || return 1` comes FIRST, so a
    non-infra head is never exhausted no matter how many attempts it has. See
    the quote at common.sh:733-735 in the module docstring for why.
    """
    attempts, cls = head_attempt_state(states, sha)
    if not class_is_infra(cls):
        return False
    return attempts >= REVIEW_MAX_ATTEMPTS_PER_HEAD


def spend_total(posted: str | int, spent: str | int) -> int:
    """`review_spend_total`'s arithmetic (common.sh:756-761), pre-fetched form.

    `echo $((${posted//[[:space:]]/} + ${spent//[[:space:]]/}))`. Both operands
    have ALL whitespace deleted before the addition, which is what makes `wc -l`'s
    leading spaces harmless on macOS. Reproduced.

    THE FETCHING FORM IS DELIBERATELY NOT HERE. The twin's `review_spend_total`
    calls `review_report_count` and `review_spent_attempt_count` when its
    optional third and fourth arguments are missing; both now propagate a `gh`
    failure loudly since the DEFECT 1 fix, but a caller here still composes
    `report_count()` and `spent_attempt_count()` explicitly, so the two network
    calls stay visible at the call site rather than folded into one sum.
    """
    return _strip_ws_int(posted) + _strip_ws_int(spent)


def _strip_ws_int(value: str | int) -> int:
    text = re.sub(r"\s", "", str(value))
    if text == "":
        # `$(( + 3))` is unary plus in bash, so an empty operand contributes 0.
        return 0
    return int(text)


# ---------------------------------------------------------------------------
# THE SNAPSHOT (common.sh:603-617)
# ---------------------------------------------------------------------------


def epic_ids(branch: str, env: dict[str, str] | None = None) -> list[str]:
    """`review_epic_ids` (common.sh:603-617). Every epic the snapshot declares.

    The snapshot is the CONTRACT (common.sh:600-602): `agent/pr/<branch>.md` is
    in the repo, the worklist store is in TMPDIR and unreadable from CI. No
    snapshot means no epics, which the caller treats as the flat, pre-epic
    review rather than as an error -- so a missing file returns `[]` and does
    not raise.

    Three properties driven 2026-09-10, all reproduced:
      * `/` maps to `-` in the branch name, so `feat/x` reads `feat-x.md`.
      * The grep is anchored at BOTH ends, so an indented `PR-TASK:` line is
        invisible.
      * Hex is lowercase only, so `PR-TASK: ABCDEF` yields nothing.

    ANCHORED TO THE REPO ROOT, not to the cwd, and common.sh:606-611 records why:
    "It used to be a bare relative path, so the answer depended on the caller's
    CWD: a gate invoked from a subdirectory saw no epics and silently took the
    flat path, which looks exactly like a PR that declares none."
    """
    if not branch:
        return []
    environ = dict(os.environ) if env is None else env
    override = environ.get(PUBLISH_ROOT_ENV, "")
    root = pathlib.Path(override) if override else paths.repo_root()
    snap = root / "agent" / "pr" / ("%s.md" % branch.replace("/", "-"))
    if not snap.is_file():
        return []
    found: list[str] = []
    for line in snap.read_text(encoding="utf-8", errors="replace").split("\n"):
        match = EPIC_LINE.match(line.rstrip("\r"))
        if match:
            found.append(match.group(1))
    return found


# ---------------------------------------------------------------------------
# THE NETWORK HALF -- raises rather than swallows, agreeing with the twin
# since the DEFECT 1 fix (previously the port refused what the twin swallowed)
# ---------------------------------------------------------------------------


def report_count(
    pr: str | int, epic: str = "", *, repo: str | None = None, env: dict | None = None
) -> int:
    """`review_report_count` (common.sh:589-596).

    The twin USED TO BE `gh api ... 2>/dev/null | wc -l || true`, which
    answered 0 on a rate limit (DEFECT 1, fixed 2026-09-10). It now routes
    through `gh_retry`, matching this port, which has raised
    `core.ghx.GhError` on failure from the start -- the same decision
    `gh_json` made a hundred lines above it in the same file. `attempts=3`
    matches `_gh_probe`'s retry count exactly.

    Everything else is the twin: the needle is the PRODUCER CONSTANT
    `**Claude finished`, matched with `startswith`, with `(epic <id>)` appended
    when an epic is named; the author filter is `contains("github-actions")`;
    an empty epic counts every report, which is the pre-epic behaviour.
    """
    needle = REPORT_EPIC_NEEDLE % epic if epic else REPORT_NEEDLE
    slug = _repo_slug(repo, env)
    comments = ghx.gh(
        ["api", "repos/%s/issues/%s/comments" % (slug, pr), "--paginate"],
        env=env,
        attempts=3,
    ).json_list()
    count = 0
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        login = ((comment.get("user") or {}).get("login")) or ""
        body = comment.get("body") or ""
        if REPORT_AUTHOR_SUBSTRING in login and body.startswith(needle):
            count += 1
    return count


def attempt_states(
    pr: str | int, prefix: str, *, repo: str | None = None, env: dict | None = None
) -> list[AttemptState]:
    """`review_attempt_states` (common.sh:681-703), WITHOUT the swallow.

    Same shape as `report_count`: the fetch raises, and the parsing is
    `parse_attempt_states` above, which is the twin's awk exactly. The twin joins
    the bodies with the `---REVIEW-ATTEMPT-EOF---` sentinel because a marker body
    is multi-line and jq cannot express "the count and class are lines within
    it"; this rebuilds the same stream so the two parsers see identical input.
    """
    slug = _repo_slug(repo, env)
    comments = ghx.gh(
        ["api", "repos/%s/issues/%s/comments" % (slug, pr), "--paginate"],
        env=env,
        attempts=3,
    ).json_list()
    chunks: list[str] = []
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        body = comment.get("body") or ""
        if body.startswith(prefix):
            chunks.append(body)
            chunks.append(ATTEMPT_EOF)
    return parse_attempt_states("\n".join(chunks))


def spent_attempt_count(
    pr: str | int, prefix: str, *, repo: str | None = None, env: dict | None = None
) -> int:
    """`review_spent_attempt_count` (common.sh:746-748)."""
    return chargeable_attempts(attempt_states(pr, prefix, repo=repo, env=env))


def diff_loc(
    pr: str | int,
    *,
    repo: str | None = None,
    env: dict | None = None,
    on_error: int | None = None,
) -> int:
    """`pr_diff_loc` (common.sh:766-772). additions + deletions.

    `on_error` IS THE ONE ARGUMENT IN THIS MODULE, and it exists because this is
    the one place the twin's swallow is a stated decision rather than an
    oversight (common.sh:764-765). Default `None` raises. Passing
    `on_error=DIFF_LOC_FAILS_TO_ZERO` reproduces the twin, VISIBLY, at the call
    site -- which is the difference between a caller who chose the smallest
    bucket and a caller who never learned there was a choice.

    The twin also validates: `[[ "$n" =~ ^[0-9]+$ ]] || n=0`, so a non-numeric
    answer becomes 0 too. That arm is folded into the same `on_error`.
    """
    slug = _repo_slug(repo, env)
    try:
        raw = ghx.gh(
            [
                "pr",
                "view",
                str(pr),
                "--repo",
                slug,
                "--json",
                "additions,deletions",
                "--jq",
                ".additions + .deletions",
            ],
            env=env,
            attempts=3,
        ).value("PR diff size")
    except ghx.GhError:
        if on_error is None:
            raise
        return on_error
    if not _UNSIGNED.fullmatch(raw.strip()):
        if on_error is None:
            raise ValueError("pr_diff_loc: unparseable diff size %r for PR %s" % (raw, pr))
        return on_error
    return int(raw.strip())


def _repo_slug(repo: str | None, env: dict | None) -> str:
    """`$GITHUB_REPOSITORY`, or the explicit argument.

    The twin reads `${GITHUB_REPOSITORY}` UNBRACED-DEFAULT, so with `set -u` and
    the variable unset it dies with `common.sh: line 592: GITHUB_REPOSITORY:
    unbound variable` (driven). Reproduced as a refusal with the same cause named
    in words, because "unbound variable" naming a library line is not a message a
    caller can act on.
    """
    if repo:
        return repo
    environ = dict(os.environ) if env is None else env
    slug = environ.get("GITHUB_REPOSITORY", "")
    if not slug:
        raise ValueError(
            "review_budget: GITHUB_REPOSITORY is not set and no repo= was passed. "
            "The twin aborts here with `GITHUB_REPOSITORY: unbound variable` "
            "(common.sh:592)."
        )
    return slug


# ---------------------------------------------------------------------------
# CLI -- the surface the shadow differential drives
# ---------------------------------------------------------------------------

USAGE = """review_budget -- the review-cap half of .ci/scripts/lib/common.sh.

  cap-for <changed-lines>         review passes allowed for a diff that size
  class-is-infra <class>          exit 0 when the class earns free re-attempts
  parse-states                    stdin: raw marker bodies -> <sha>\\t<n>\\t<class>
  chargeable < states.tsv         what the cap counts
  head-state <sha> < states.tsv   "<attempts> <class>" for that head
  head-exhausted <sha> < states.tsv   exit 0 when the head may not be retried
  spend-total <posted> <spent>    the pre-fetched sum
  epic-ids <branch>               every epic id the published snapshot declares
"""


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE, file=sys.stderr)
        return 2
    verb, rest = argv[0], argv[1:]
    try:
        return _dispatch(verb, rest)
    except ValueError as err:
        print(str(err), file=sys.stderr)
        return 1


def _dispatch(verb: str, rest: list[str]) -> int:
    if verb == "cap-for":
        print(cap_for(rest[0] if rest else ""))
        return 0
    if verb == "class-is-infra":
        return 0 if class_is_infra(rest[0] if rest else "") else 1
    if verb == "parse-states":
        for state in parse_attempt_states(sys.stdin.read().rstrip("\n")):
            print(state.tsv())
        return 0
    if verb == "chargeable":
        print(chargeable_attempts(attempts_from_tsv(sys.stdin.read())))
        return 0
    if verb == "head-state":
        attempts, cls = head_attempt_state(attempts_from_tsv(sys.stdin.read()), rest[0])
        print("%d %s" % (attempts, cls))
        return 0
    if verb == "head-exhausted":
        states = attempts_from_tsv(sys.stdin.read())
        return 0 if head_is_exhausted(states, rest[0]) else 1
    if verb == "spend-total":
        print(spend_total(rest[0], rest[1]))
        return 0
    if verb == "epic-ids":
        for eid in epic_ids(rest[0] if rest else ""):
            print(eid)
        return 0
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
