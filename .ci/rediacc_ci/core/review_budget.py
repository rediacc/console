"""How many Claude review passes a PR may spend: the cap tiers, the attempt ledger, and the reads that feed them.

ONE TABLE, TWO CALLERS. `rediacc_ci.review.claude_review_gate` decides whether to spend money on another pass, and `rediacc_ci.review.review_status` reports whether the cap is reached so a capped PR still gets a passing Review Complete. The two disagreeing about the cap is a known deadlock: on PR #553 (2026-08-07) the gate read 3/3 while the reporter read 0/3, and a green, ready, thread-clean PR
became unmergeable through no fault of its author. So every rule lives here once and both callers import it.

THE NUMBERS, pinned as numbers by `test_core_review_budget.py`:

  * cap tiers: up to 10,000 changed lines earns 3 passes, up to 50,000 earns 5, anything larger earns 7. The bands are inclusive at the top, and the 50k-100k band lands in the top bucket on purpose: a 60,000-line diff is not meaningfully easier to review than a 100,000-line one.
  * an unreadable or non-numeric line count is 0, the smallest bucket. That is the conservative direction for the DENOMINATOR: it spends fewer passes, never more.
  * a head may be attempted at most 3 times; an infrastructure-class death (`error_max_turns`, `error_during_execution`) earns 2 free re-attempts before it is charged.

THE NUMERATOR NEVER FAILS TO ZERO. A rate-limited read of the posted reports or the attempt ledger that answered 0 would mean "the cap was never reached", and the gate would dispatch another full review at full price. `report_count`, `attempt_states` and `spent_attempt_count` therefore raise `core.ghx.GhError` after three attempts; only `diff_loc` offers a fallback, and only when the
caller passes `on_error=DIFF_LOC_FAILS_TO_ZERO` visibly at its call site.

THE ATTEMPT LEDGER. A review pass that produced no report still spent turns and tokens, so `--mark` records it as an attempt comment on the PR: `<!-- claude-review-attempt: <sha40> -->`, then `attempts: <n>` and `class: <subtype>` lines. One comment per head, upserted with its count. `parse_attempt_states` reads the bodies back:

  * records are separated by a line that is exactly `---REVIEW-ATTEMPT-EOF---`, and a trailing record with no sentinel still counts;
  * the sha is the first word after the first `claude-review-attempt:` in a record;
  * `attempts:` must be followed by digits, so a corrupted `attempts: zz` reads as the default 1 rather than as garbage;
  * a record with no sha yields nothing; a legacy marker with no count or class reads as one attempt of unknown class.

A NON-INFRA HEAD IS NEVER EXHAUSTED. Only an infra-class head hits the per-head ceiling: a reportless attempt of unknown cause was never per-head blocked, and making it one would be a new restriction presented as a relaxation. What bounds a non-infra head is the per-PR cap, which charges every one of its attempts.
"""

from __future__ import annotations

import os
import re

from rediacc_ci.core import ghx

# (upper bound inclusive, passes). `None` is the catch-all top tier. Order is the contract: the first tier whose bound the value fits wins.
CAP_TIERS: tuple[tuple[int | None, int], ...] = ((10000, 3), (50000, 5), (None, 7))

# Unreachable while the last tier's bound is `None`; kept so an edit to CAP_TIERS that drops the catch-all still answers the smallest budget.
CAP_FALLBACK = 3

# Single tokens by construction: a test asserts no member contains a space.
INFRA_CLASSES = ("error_max_turns", "error_during_execution")

REVIEW_FREE_REATTEMPTS_PER_HEAD = 2
REVIEW_MAX_ATTEMPTS_PER_HEAD = 3

# The header `claude_review_gate --post-report` writes. A report is counted by this prefix ALONE: a content qualifier once undercounted every measured PR (#551 counted 0 of 1, #550 5 of 7, #546 3 of 7, #543 1 of 9), so never add one.
REPORT_NEEDLE = "**Claude finished"

# Comments posted with the workflow's `github.token` carry this login.
REPORT_AUTHOR_SUBSTRING = "github-actions"

ATTEMPT_KEY = "claude-review-attempt:"
ATTEMPT_EOF = "---REVIEW-ATTEMPT-EOF---"

# The denominator's stated fallback, named so a caller opts into it visibly.
DIFF_LOC_FAILS_TO_ZERO = 0

_UNSIGNED = re.compile(r"[0-9]+")
_ATTEMPTS_LINE = re.compile(r"^attempts:[ \t]*([0-9]+)")
_CLASS_LINE = re.compile(r"^class:[ \t]*")


class AttemptState:
    """One recorded head: its sha, how many attempts it spent, and the class of the last death."""

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


# --------------------------------------------------------------------------- THE DENOMINATOR ---------------------------------------------------------------------------


def cap_for(changed_lines: str | int | None) -> int:
    """Review passes allowed for a diff of `changed_lines` (additions plus deletions).

    Anything that is not a run of digits counts as 0 and lands in the smallest tier: `abc`, `""`, `-5` and `1e3` all answer 3.
    """
    text = "" if changed_lines is None else str(changed_lines)
    loc = int(text) if _UNSIGNED.fullmatch(text) else 0
    for bound, cap in CAP_TIERS:
        if bound is None or loc <= bound:
            return cap
    return CAP_FALLBACK


# --------------------------------------------------------------------------- THE ATTEMPT LEDGER, pure ---------------------------------------------------------------------------


def class_is_infra(cls: str) -> bool:
    """Whether a death class is the harness's fault rather than a verdict on the code.

    An empty class, from a legacy marker, is not infra: "nobody knows why it died" is the case where free retries are most expensive.
    """
    return cls in INFRA_CLASSES


def parse_attempt_states(raw: str) -> list[AttemptState]:
    """Attempt bodies joined by `ATTEMPT_EOF` lines, as one state per recorded head (rules in the module docstring)."""
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
            tail = line.rsplit(ATTEMPT_KEY, 1)[1].lstrip(" \t")
            sha = re.split(r"[ \t]", tail, maxsplit=1)[0]
        count = _ATTEMPTS_LINE.match(line)
        if count:
            attempts = int(count.group(1))
        if _CLASS_LINE.match(line):
            cls = _CLASS_LINE.sub("", line).rstrip(" \t")
    flush()
    return states


def chargeable_attempts(states: list[AttemptState]) -> int:
    """What the per-PR cap counts from the ledger.

    An infra head is charged `attempts - REVIEW_FREE_REATTEMPTS_PER_HEAD`, clamped at 0, so three infra attempts cost three attempts' money and one charge: a deliberate under-charge that keeps the loop moving, bounded by the per-head ceiling. Every other head is charged in full.
    """
    total = 0
    for state in states:
        charge = state.attempts
        if class_is_infra(state.cls):
            charge = max(0, state.attempts - REVIEW_FREE_REATTEMPTS_PER_HEAD)
        total += charge
    return total


def head_attempt_state(states: list[AttemptState], sha: str) -> tuple[int, str]:
    """(attempts, class) for one head; the LAST matching row wins, and an unrecorded head is (0, "")."""
    found = (0, "")
    for state in states:
        if state.sha == sha:
            found = (state.attempts, state.cls)
    return found


def head_is_exhausted(states: list[AttemptState], sha: str) -> bool:
    """Whether this head may not be attempted again: an infra class at or past the per-head ceiling."""
    attempts, cls = head_attempt_state(states, sha)
    if not class_is_infra(cls):
        return False
    return attempts >= REVIEW_MAX_ATTEMPTS_PER_HEAD


def spend_total(posted: str | int, spent: str | int) -> int:
    """Posted reports plus chargeable attempts: what was SPENT, not what was delivered.

    Charging only for successes is what once let a failing head be re-reviewed forever. Whitespace inside either operand is ignored and an empty operand counts 0.
    """
    return _strip_ws_int(posted) + _strip_ws_int(spent)


def _strip_ws_int(value: str | int) -> int:
    text = re.sub(r"\s", "", str(value))
    if text == "":
        return 0
    return int(text)


# --------------------------------------------------------------------------- THE NETWORK HALF: raises rather than answering 0 ---------------------------------------------------------------------------


def report_count(pr: str | int, *, repo: str | None = None, env: dict | None = None) -> int:
    """Finished review reports on the PR: github-actions comments whose body starts with `REPORT_NEEDLE`. Raises `ghx.GhError` when the comments cannot be read."""
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
        if REPORT_AUTHOR_SUBSTRING in login and body.startswith(REPORT_NEEDLE):
            count += 1
    return count


def attempt_states(
    pr: str | int, prefix: str, *, repo: str | None = None, env: dict | None = None
) -> list[AttemptState]:
    """The attempt ledger: every comment whose body starts with `prefix`, parsed by `parse_attempt_states`. Raises `ghx.GhError` when unreadable."""
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
    """`chargeable_attempts` over the fetched ledger."""
    return chargeable_attempts(attempt_states(pr, prefix, repo=repo, env=env))


def diff_loc(
    pr: str | int,
    *,
    repo: str | None = None,
    env: dict | None = None,
    on_error: int | None = None,
) -> int:
    """Additions plus deletions for the PR.

    With `on_error=None` a failed read or a non-numeric answer raises; passing `on_error=DIFF_LOC_FAILS_TO_ZERO` takes the smallest cap tier instead, visibly at the call site.
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
            raise ValueError("diff_loc: unparseable diff size %r for PR %s" % (raw, pr))
        return on_error
    return int(raw.strip())


def _repo_slug(repo: str | None, env: dict | None) -> str:
    """The explicit `repo`, else `$GITHUB_REPOSITORY`; neither is a `ValueError` naming both."""
    if repo:
        return repo
    environ = dict(os.environ) if env is None else env
    slug = environ.get("GITHUB_REPOSITORY", "")
    if not slug:
        raise ValueError("review_budget: GITHUB_REPOSITORY is not set and no repo= was passed")
    return slug
