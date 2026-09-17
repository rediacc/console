#!/usr/bin/env python3
"""Port of `.ci/scripts/review/claude-review-gate.sh`, the automated-review gate.

THE INVARIANT FIRST, because every arm below exists to protect it. Operator ruling 2026-07-22, quoted from the twin's own header: "a review fires ONLY for an open, non-draft, same-repo PR whose CURRENT head SHA has green CI at decision time, that is not already marked reviewed, and whose delta since the last reviewed SHA is not submodule pointer bumps only. A red push after a
review gets no re-review until a later push completes green."

SAME-REPO IS NOT ENFORCED HERE, AND THAT IS NOT AN OMISSION. It is enforced one level up, in `.github/workflows/claude-review.yml:74` and `:77`
(`github.event.workflow_run.head_repository.full_name == github.repository` and
`github.event.pull_request.head.repo.full_name == github.repository`), so a fork
PR never reaches this script at all. Nothing in either implementation can see
the head repository, so a differential of this file cannot cover that clause;
`test_review_claude_review_gate.py` pins the workflow condition instead, which is where the clause actually lives.

FIVE ARMS, selected by `$1`:

    (default)        decide go/no-go and assemble the prompt
    --post-report    post the model's final report as a PR comment
    --post-findings  turn the report's findings fence into inline comments
    --apply-labels   label the PR from the same review pass
    --mark           upsert the reviewed-SHA marker, or record a spent attempt

===========================================================================
WHAT IS REUSED, AND WHAT IS DELIBERATELY NOT
===========================================================================
The review BUDGET (the cap tiers, the attempt ledger, what counts as chargeable, what exhausts a head) is already ported at `core.review_budget`, whose docstring names this script as one of its two live callers and quotes the reason the rules live in one place: "the two disagreeing about the cap resurrects exactly the deadlock review-status.sh was written to prevent. One table, one
function, both callers." So every PURE rule comes from there by import: `cap_for`, `parse_attempt_states`, `chargeable_attempts`, `head_attempt_state`, `head_is_exhausted`, `spend_total`, `class_is_infra`, the two per-head constants and the two report needles.

The NETWORK halves of that module (`report_count`, `attempt_states`, `diff_loc`) are NOT used, and the reason is fidelity rather than taste:

  * `review_budget.report_count` fetches the comment page and filters in Python,
    while the twin filters SERVER-SIDE with `gh api ... --jq`. Same answer,
    different argv. `review_status.py` accepts that difference and excludes two
    endpoints from its raw-argv comparison; this file instead passes the twin's
    own `--jq` programs, so the differential compares RAW ARGV on every single
    `gh` call with no exclusions at all.
  * `review_budget.diff_loc` retries three times (`attempts=3`). The twin's
    `pr_diff_loc` and `emit_review_turns` each make ONE call and fall back, so a
    failing lookup would log three calls here against the twin's one.

`gh_retry` (`common.sh:434-470`, `_gh_probe`) is reproduced in `gh_retry()` below, warning lines, backoff schedule, indented replay of gh's stderr and all, because the two budget reads go through it and its stderr is part of what a differential on the failure path compares.

===========================================================================
DEFECT 1 (REPORTED, NOT FIXED) -- `last_marker_sha` STILL SWALLOWS A gh FAILURE,
AND IT IS THE ONE THAT COSTS MONEY
===========================================================================
`common.sh` was fixed on 2026-09-10 so that `review_report_count`, `review_attempt_states` and `review_spend_total` route through `gh_retry` and propagate a failure, precisely because a rate-limited numerator of 0 "meant the cap was never reached, so a rate-limited run dispatched ANOTHER full review" (`core/review_budget.py`, DEFECT 1). The same spelling survives untouched in THIS
file, on the dedup guard rather than on the cap:

    last_marker_sha() {
        gh api ".../issues/${1}/comments" --paginate --jq '...' 2>/dev/null |
            sed -n 's/.*claude-reviewed: \\([0-9a-f]\\{40\\}\\).*/\\1/p' | tail -n 1 || true
    }

`pipefail` is on, so the pipeline DOES fail; `|| true` throws that away after
`sed` has already printed nothing. An empty `last_sha` is indistinguishable from "this head was never reviewed", so the gate skips the `head already reviewed`
check, skips the submodule-pointer-bump check, and emits `go=true` with the
INITIAL prompt for a PR that was fully reviewed minutes earlier. The call has no retry either, unlike the two budget reads immediately above it.

Driven, in the differential, by a fake `gh` that fails only its Nth call (`test_a_gh_failure_on_the_marker_read_re_reviews_an_already_reviewed_head`):
both implementations answer `go=true ... initial review: full PR diff` for a
head whose marker comment is present and current. Reproduced rather than repaired: repairing a twin is a cutover-box decision.

`last_marker_id` carries the same swallow with a smaller blast radius: a failed read makes `--mark` POST a second marker comment instead of PATCHing the one that exists.

===========================================================================
DEFECT 2 (REPORTED, NOT FIXED) -- `emit_review_turns` HAS NO NUMERIC GUARD
WHERE ITS TWIN CALL SITE HAS ONE
===========================================================================
`pr_diff_loc` (`common.sh:766-772`) makes exactly the same call and then
validates: `[[ "$n" =~ ^[0-9]+$ ]] || n=0`. `emit_review_turns` (:149-178) makes
it and feeds the answer straight into arithmetic:

    local kloc=$(((${changed:-0} + 999) / 1000))

Under `set -u` a non-numeric word in an arithmetic context is read as a VARIABLE NAME, so a `gh` that exits 0 with `null` on stdout kills the gate with `claude-review-gate.sh: line 172: null: unbound variable` and exit 1, AFTER the budget has been read and BEFORE anything is written to `$GITHUB_OUTPUT`. The step then fails with no `go` output at all rather than with a decision.
Reproduced here, byte for byte, by `_arith_or_die`, which raises the same message with the same exit code instead of letting Python compute something the twin could not.

===========================================================================
DEFECT 3 (REPORTED, NOT FIXED) -- `--mark` LOSES THE ATTEMPT COUNT ON A gh
FAILURE, THROUGH A NESTED COMMAND SUBSTITUTION
===========================================================================
    prior=$(review_head_attempt_state "$(review_attempt_states "$PR_NUMBER" "$ATTEMPT_PREFIX")" "$HEAD_SHA")

`set -e` looks at the status of the OUTER substitution, which is `review_head_attempt_state` and always 0. The inner `review_attempt_states` returning 1 after `gh_retry`'s three failed attempts is discarded, `prior` becomes the default `"0 "`, and `attempts` becomes 1. A head that has already spent 3 of 3 attempts is therefore recorded as spending its first, and the per-head
ceiling that `review_head_is_exhausted` exists to enforce is reset by a transient rate limit. Reproduced, with the twin's own stderr, because `gh_retry()` here is faithful to `_gh_probe`.

===========================================================================
DEFECT 4 (REPORTED, NOT FIXED) -- `--post-findings` DROPS EVERY INLINE COMMENT
ON A REPORT THAT FOLLOWS ITS OWN PROMPT
===========================================================================
The findings scanner (twin :333-340) never clears `capturing`, so it takes everything from the `json:review-findings` opener to the LAST closing fence ANYWHERE later in the report:

    /^[[:space:]]*```json:review-findings[[:space:]]*$/ { capturing = 1; ... }
    capturing { buf[++n] = $0; if ($0 ~ /^[[:space:]]*```[[:space:]]*$/) last = n }

`prompts/initial.md:67` instructs the model to close the report with a SECOND fence, `json:pr-labels`, after that section, and `--apply-labels` depends on it being there. So the extraction runs past the findings array, through the prose and into the labels block. Driven against the real awk and the real jq:

    $ awk '<the twin's program>' report.md | jq -e 'type == "array"'
    jq: parse error: Invalid numeric literal at line 3, column 0
    exit 5

`! jq -e ...` is then true, and the arm prints `no parseable review-findings
block; skipping inline comments` and exits 0. Every line-anchored comment is
silently dropped, on the shape the prompt asks for, and the arm reports success.

The last-closer rule was added to survive a fence NESTED inside a finding's `body`, and that case is not reachable through valid JSON: a JSON string cannot contain a raw newline, so an embedded fence never lands on a line of its own and never matches the closer. The rule buys nothing and costs everything. `test_defect4_*` drives it, its control and the anti-vacuity check that the
prompt still asks for both fences in that order.

===========================================================================
SMALLER THINGS THAT ARE THE TWIN'S AND ARE REPRODUCED ON PURPOSE
===========================================================================
  * `--mark`'s honesty guard folds "gh failed" into "posted NOTHING in the last
    hour". It fails CLOSED (the SHA stays retryable), so it is the safe
    direction, but the sentence it prints is not true of a rate limit.
  * The `✗ prompt template did not render` line is `echo`, not `log_error`, so
    it carries no colour even on a tty. Written raw here for the same reason.
  * The inline-comment body contains a literal U+2014. It is spelled `\\u2014`
    in this file so `check:ci-em-dash-surfaces` (which scans `.ci/rediacc_ci`
    for the CHARACTER) stays green while the BYTES on the wire stay identical.
  * `${#report}` counts characters under a UTF-8 locale and bytes under
    `LC_ALL=C`; Python always counts characters. The differential runs under
    `LC_ALL=C` with ASCII fixtures, where the two agree, and the 60000-char
    truncation threshold is far enough from any real report boundary that the
    difference has never been reachable in CI.
  * `sed`, `jq` and `git` are still SUBPROCESSES here, with the twin's exact
    programs, wherever their output is the product rather than an intermediate:
    the six-expression prompt render, every extraction out of the execution
    file, the label-verdict validation and the findings sort. `review_status.py`
    makes the same call for the same reason ("jq builds the check-run payload,
    and that is not laziness"). The awk fence scanners and the sed/grep/tr/paste
    line filters ARE ported to Python, and each one is driven against the real
    program it replaces in the differential rather than argued to be equal.

Env seam: `CLAUDE_REVIEW_GATE_SCRIPT_DIR` overrides the twin's `SCRIPT_DIR`, which is the only thing this module needs it for (the `prompts/` directory). It defaults to the real `.ci/scripts/review`, so a plain run reads the real templates.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import time

from rediacc_ci import log, paths
from rediacc_ci.core import common, review_budget

# --- the three comment prefixes, byte for byte from the twin ---------------- Deliberately DIFFERENT strings. `ATTEMPT_PREFIX` must never satisfy `last_marker_sha` (a review that read nothing would suppress a later real one) and `LEDGER_PREFIX` must be invisible to all three counters (a bookkeeping comment would otherwise look like a review). The twin says so at :54-63.
MARKER_PREFIX = "<!-- claude-reviewed:"
ATTEMPT_PREFIX = "<!-- claude-review-attempt:"
LEDGER_PREFIX = "<!-- claude-labels:"

# THE HARD WHITELIST for `--apply-labels` (twin :65-76). This is the security boundary of that arm: adding a label the repo does not carry CREATES it, so an unfiltered hallucinated name would appear on the repo AND fail check:ci-label-inventory for everyone until someone deleted it by hand. `bump-major` is DELIBERATELY ABSENT (operator ruling): a wrong minor is cosmetic, a wrong
# major is a statement to every consumer of the version stream.
MANAGED_LABELS = ("bug", "enhancement", "documentation", "ci", "bump-minor", "bump-none")

# "<name>|<color>|<description>", one row per label, created on demand immediately before first use. Each row is asserted equal to `.github/labels.yml` by `test-review-labels.sh`, since neither implementation can read labels.yml: the post-review steps run from a staged copy of `.ci` alone.
CREATE_ON_DEMAND_LABELS = (
    "ci|FEF2C0|Build system, CI workflows, or .ci tooling (applied by the automated review)",
    (
        "bump-none|C5DEF5|No user-facing change: merging skips the release "
        "(review-applied; removed on release-worthy pushes)"
    ),
)

# Turn budget, scaled to diff size (twin :171). DENSITY, not rungs: measured the same day by the same reviewer, PR #552 completed at 22.0 turns/KLOC and PR #553 died at 17.8, while file count did not discriminate (39 files passed where 36 failed). TURNS_PER_KLOC sits above the measured survivor because one survival is not a floor.
TURNS_PER_KLOC = 25
MAX_TURNS = 140
MIN_TURNS = 50

# `${#report} -gt 60000`, then head 30000 + tail 25000 (twin :293-300). The
# middle is dropped rather than the tail because the tail carries the `json:review-findings` fence that `--post-findings` parses.
REPORT_LIMIT = 60000
REPORT_HEAD = 30000
REPORT_TAIL = 25000

# `.[0:20]` (twin :372).
INLINE_COMMENT_CAP = 20

PROMPT_DELIMITER = "CLAUDE_REVIEW_PROMPT_EOF"
FINDINGS_FENCE = "json:review-findings"
LABELS_FENCE = "json:pr-labels"

# The one env seam, see the module docstring.
SCRIPT_DIR_ENV = "CLAUDE_REVIEW_GATE_SCRIPT_DIR"

# `sed -n 's/.*claude-reviewed: \([0-9a-f]\{40\}\).*/\1/p'` (twin :123). Applied
# per LINE, and the LAST match wins: the marker body is multi-line and a `tail -n 1` before the sed grabbed the trailing cost line and matched nothing, "silently disabling the whole review-dedup (every green push re-reviewed). Found by review finding F4."
MARKER_SHA_RE = re.compile(r".*claude-reviewed: ([0-9a-f]{40}).*")

# `sed -n 's/^applied:[[:space:]]*//p'` (twin :546).
APPLIED_RE = re.compile(r"^applied:[ \t\n\r\f\v]*")

# `grep -qvE '(^docs/|^agent/|...)'` (twin :444) and its `.ci` sibling (:447). `^agent/` is named EXPLICITLY rather than left to the trailing `\.md$` alternative: while every file under that tree happened to end in .md the docs label landed by accident, and the first sidecar, fixture or script under agent/ would have silently turned a notes-only PR into an unlabelled one.
DOCS_ONLY_RE = re.compile(
    r"(^docs/|^agent/|^packages/www/src/content/docs/|^CLAUDE\.md$|^LICENSE$|\.md$)"
)
CI_ONLY_RE = re.compile(r"(^\.github/|^\.ci/|^scripts/ci-runner/)")

# awk's `[[:space:]]` on a single line, which never contains `\n`.
_WS = " \t\r\f\v"
_WS_CLASS = r"[ \t\r\f\v]*"

# --- the jq programs, verbatim from the twin -------------------------------- Copied character for character INCLUDING their indentation, and `test_every_jq_program_is_verbatim_from_the_twin` asserts each one is still a substring of the twin's source. A silently reworded program on one side is the failure that makes a differential pass while the two disagree in production.

RESULT_TEXT_JQ = """
            (if type == "array" then [.[] | select(.type == "result")][-1] else . end) as $r
            | select($r != null) | $r.result // empty
        """

RESULT_SUBTYPE_JQ = """
                (if type == "array" then [.[] | select(.type == "result")][-1] else . end) as $r
                | select($r != null) | $r.subtype // empty
            """

LABEL_VERDICT_VALID_JQ = """
        type == "object"
        and ((.bump // "patch") as $b | ["none", "patch", "minor", "major"] | index($b) != null)
        and ((.kind // []) | type == "array")
        and ((.kind // []) | length <= 2)
        and (((.kind // []) - ["bug", "feature", "docs", "ci"]) | length == 0)
    """

FINDINGS_SORT_JQ = """
        sort_by(.severity // "medium"
            | ascii_downcase
            | if . == "critical" then 0 elif . == "high" then 1 elif . == "medium" then 2 else 3 end)
        | .[0:20] | .[]"""

COST_JQ = """
            (if type == "array" then [.[] | select(.type == "result")][-1] else . end) as $r
            | select($r != null)
            | ($r.usage // {}) as $u
            | "Cost: $\\($r.total_cost_usd // 0 | . * 10000 | round / 10000)"
              + " (\\(
                  ($r.modelUsage // {}) as $m
                  | if ($m | length) == 0 then "model n/a"
                    else
                      # EVERY model, ordered by output-token share, not `keys|first`.
                      #
                      # `keys | first` reported ONE model chosen by arbitrary key
                      # order. Observed on PR #543: the line read
                      # "(claude-haiku-4-5-20251001)" while the action was invoked
                      # with `--model claude-sonnet-5`, which reads as "the flag was
                      # ignored" when it may only mean haiku sorted first among the
                      # models used. The action legitimately uses a small model for
                      # its own sub-steps, so a single name can never answer "which
                      # model reviewed my code?" -- it can only mislead. Issue #539.
                      [ $m | to_entries[]
                        | { k: .key,
                            out: (.value.outputTokens // .value.output_tokens // 0) } ]
                      | sort_by(-.out)
                      | map(.k + (if .out > 0 then " " + (.out|tostring) + "out" else "" end))
                      | join(", ")
                    end
                ))"
              + " | \\($r.num_turns // "?") turns"
              + " | \\((($r.duration_ms // 0) / 60000) | floor)m\\((($r.duration_ms // 0) / 1000 | floor) % 60)s"
              + "\\nTokens: \\($u.input_tokens // 0) in / \\($u.output_tokens // 0) out"
              + " / \\($u.cache_read_input_tokens // 0) cache-read / \\($u.cache_creation_input_tokens // 0) cache-write"
        """


class Done(Exception):  # noqa: N818 -- a control-flow signal, not an error
    """One `exit N` from the twin, thrown from wherever the twin exits."""

    def __init__(self, code: int) -> None:
        super().__init__("exit %d" % code)
        self.code = code


class Aborted(Exception):  # noqa: N818 -- see Done
    """A bash abort: a message already on stderr, and the twin's exit code.

    Distinct from `common.RefusalError`, which owns the `require_*` wording.
    """

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# --------------------------------------------------------------------------- Subprocess seams. Each one mirrors ONE bash redirection shape. ---------------------------------------------------------------------------


def script_dir() -> pathlib.Path:
    """The twin's `SCRIPT_DIR`, which is `.ci/scripts/review/`.

    This module lives in `.ci/rediacc_ci/review/`, where `$SCRIPT_DIR/prompts` would resolve to a directory that does not exist, so the twin's own directory is named explicitly rather than derived from `__file__`.
    """
    # THE NAME IS A LITERAL AT THE CALL SITE, not `os.environ.get(SCRIPT_DIR_ENV)`. `check:ci-python-env-registry` derives a module's inputs from the AST and records a non-literal as an OPAQUE `*<expr>` entry, which is a declared input nobody can grep for. `SCRIPT_DIR_ENV` stays as the constant the tests name.
    override = os.environ.get("CLAUDE_REVIEW_GATE_SCRIPT_DIR", "")
    if override:
        return pathlib.Path(override)
    return paths.repo_root() / ".ci" / "scripts" / "review"


def _gh(args: list[str], *, quiet: bool = False, stdin_null: bool = False) -> tuple[int, str]:
    """`gh <args>` with stdout captured; `quiet` is the twin's `2>/dev/null`.

    The returned text has its trailing newlines stripped, which is what `$(...)` does and what every caller here assumes.
    """
    try:
        proc = subprocess.run(
            ["gh", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if quiet else None,
            stdin=subprocess.DEVNULL if stdin_null else None,
            check=False,
        )
    except OSError:
        return 127, ""
    return proc.returncode, (proc.stdout or b"").decode("utf-8", "replace").rstrip("\n")


def _gh_raw(args: list[str], *, quiet: bool = False) -> tuple[int, str]:
    """As `_gh`, but WITHOUT stripping: the `| wc -l` call sites count newlines."""
    try:
        proc = subprocess.run(
            ["gh", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if quiet else None,
            check=False,
        )
    except OSError:
        return 127, ""
    return proc.returncode, (proc.stdout or b"").decode("utf-8", "replace")


def _gh_write(args: list[str], *, quiet: bool = False, stdin_null: bool = False) -> int:
    """A write whose stdout the twin sends to `/dev/null`. Returns the exit code.

    `quiet` is `2>&1` into the same place, which the advisory writes use and the two fatal ones (the report comment, the marker) deliberately do not.
    """
    try:
        proc = subprocess.run(
            ["gh", *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL if quiet else None,
            stdin=subprocess.DEVNULL if stdin_null else None,
            check=False,
        )
    except OSError:
        return 127
    return proc.returncode


def gh_retry(what: str, args: list[str], *, sleep=time.sleep) -> tuple[int, str]:
    """`gh_retry` / `_gh_probe false` (common.sh:434-470), stderr and all.

    Three attempts, `sleep attempt*3` between them, a `log_warn` per retry, and on total failure a `log_error` plus gh's own stderr replayed indented four spaces. That replay is the half `2>/dev/null` deletes at every unfixed call site, so it is reproduced rather than summarised.

    `sleep` is injectable so a test can assert the schedule without spending it. The DIFFERENTIAL does spend it, because the twin does.
    """
    rc = 0
    err = ""
    for attempt in (1, 2, 3):
        try:
            proc = subprocess.run(["gh", *args], capture_output=True, check=False)
        except OSError:
            rc, err = 127, ""
        else:
            rc = proc.returncode
            err = (proc.stderr or b"").decode("utf-8", "replace")
            if rc == 0:
                return 0, (proc.stdout or b"").decode("utf-8", "replace").rstrip("\n")
        if attempt < 3:
            log.warn(
                "%s: gh call failed or returned unusable output (attempt %d/3), retrying..."
                % (what, attempt)
            )
            sleep(attempt * 3)
    log.error("%s: gh failed after 3 attempts (last exit %d)." % (what, rc))
    if err:
        # `[[ -s "$err" ]] && sed 's/^/ /' "$err" >&2`.
        for line in err.split("\n")[:-1] if err.endswith("\n") else err.split("\n"):
            sys.stderr.write("    %s\n" % line)
        sys.stderr.flush()
    return rc if rc != 0 else 1, ""


def _jq(args: list[str], *, stdin: str | None = None, quiet: bool = False) -> tuple[int, str]:
    """`jq <args>` with stdout captured and trailing newlines stripped.

    `stdin` is the twin's here-string, which appends a newline; `quiet` is
    `2>/dev/null`, present on some call sites and pointedly absent from others.
    """
    proc = subprocess.run(
        ["jq", *args],
        input=(stdin + "\n").encode("utf-8") if stdin is not None else b"",
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL if quiet else None,
        check=False,
    )
    return proc.returncode, (proc.stdout or b"").decode("utf-8", "replace").rstrip("\n")


def _jq_test(args: list[str], *, stdin: str) -> bool:
    """`jq -e ... >/dev/null 2>&1`: the exit status only."""
    proc = subprocess.run(
        ["jq", *args],
        input=(stdin + "\n").encode("utf-8"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


# --------------------------------------------------------------------------- Pure text helpers. Each is driven against the program it replaces. ---------------------------------------------------------------------------


def sed_replacement(text: str) -> str:
    """`sed_replacement` (twin :198-204). Escape TEXT for the RHS of `s|...|...|`.

    THE BUG THIS CLOSES, from the first epic-scoped review of PR #583 (run 33445357414, job 99663191041): `sed: -e expression #6, char 77: unterminated
    's' command`. Expression #6 is `{{EPIC_SCOPE}}` and the scope paragraph is
    seven lines; a replacement may not contain a raw newline, so the whole review
    died before it began on prose this script authors itself.

    Four things are unsafe and all four are escaped: a backslash (starts an escape), the `|` delimiter (ends the command), `&` (expands to the whole match) and a newline (must be backslash-continued). Backslash goes FIRST or it re-escapes the escapes.
    """
    out = text.replace("\\", "\\\\")
    out = out.replace("|", "\\|")
    out = out.replace("&", "\\&")
    return out.replace("\n", "\\\n")


def extract_findings_fence(text: str) -> str:
    """The `--post-findings` awk (twin :333-340). LAST opener, LAST closer.

    A finding's own `body` may embed a ``` fence (a review bot suggesting a code fix), so stopping at the FIRST closing fence truncates the array and silently drops all of it. This anchors to the LAST `json:review-findings` opener and takes everything up to that block's LAST closing fence.

    A new opener resets the buffer, which is what makes "last opener" true.
    """
    opener = re.compile(r"^%s```%s%s$" % (_WS_CLASS, re.escape(FINDINGS_FENCE), _WS_CLASS))
    closer = re.compile(r"^%s```%s$" % (_WS_CLASS, _WS_CLASS))
    capturing = False
    buf: list[str] = []
    last = 0
    for line in text.split("\n"):
        if opener.match(line):
            capturing = True
            buf = []
            last = 0
            continue
        if capturing:
            buf.append(line)
            if closer.match(line):
                last = len(buf)
    if last <= 0:
        return ""
    return "\n".join(buf[: last - 1])


def extract_labels_fence(text: str) -> str:
    """The `--apply-labels` awk (twin :462-467 and :485-490). LAST opener, FIRST closer.

    Deliberately a DIFFERENT scanner from the findings one above: a verdict object cannot contain a nested fence, and "a report may quote the required format before emitting its real one" is the case that matters, so the LAST fence wins and its first closer ends it. `capturing` going false without clearing the buffer is what makes `END` print the last opened block.
    """
    opener = re.compile(r"^%s```%s%s$" % (_WS_CLASS, re.escape(LABELS_FENCE), _WS_CLASS))
    closer = re.compile(r"^%s```%s$" % (_WS_CLASS, _WS_CLASS))
    capturing = False
    buf: list[str] = []
    for line in text.split("\n"):
        if opener.match(line):
            capturing = True
            buf = []
            continue
        if capturing and closer.match(line):
            capturing = False
            continue
        if capturing:
            buf.append(line)
    return "\n".join(buf)


def marker_sha_from_bodies(text: str) -> str:
    """`sed -n 's/.*claude-reviewed: \\(...\\).*/\\1/p' | tail -n 1` (twin :123)."""
    found = ""
    for line in text.split("\n"):
        match = MARKER_SHA_RE.match(line)
        if match:
            found = match.group(1)
    return found


def last_line(text: str) -> str:
    """`tail -n 1` over a `$(...)`-stripped capture."""
    if not text:
        return ""
    return text.rsplit("\n", 1)[-1]


def awk_second_fields(text: str) -> str:
    """`awk '{print $2}'`: one output line per input line, empty when short."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    out = []
    for line in lines:
        fields = line.split()
        out.append(fields[1] if len(fields) >= 2 else "")
    return "\n".join(out)


def grep_fixed_inverse(names: list[str], patterns_blob: str) -> str:
    """`grep -Fxv -f <(printf '%s\\n' "$patterns")`: drop exact-line matches.

    `printf '%s\\n'` on an EMPTY blob writes a single empty line, and `-x` makes the empty pattern match only empty lines, so no submodules means nothing is dropped. That is the arm a hand-rolled `if patterns:` guard would get wrong.
    """
    patterns = set((patterns_blob + "\n").split("\n"))
    return "\n".join(name for name in names if name not in patterns)


def csv_of(labels: list[str]) -> str:
    """`printf '%s' "$desired" | sed '/^$/d' | paste -sd, -`."""
    return ",".join(label for label in labels if label != "")


def split_ledger_labels(prev: str) -> list[str]:
    """`tr ',' '\\n' <<<"$prev" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'`."""
    return [chunk.strip(_WS) for chunk in prev.replace(",", "\n").split("\n")]


def _arith_or_die(word: str, context: str) -> int:
    """Bash arithmetic on an untrusted word, with the twin's failure preserved.

    Under `set -u` a non-numeric word inside `$(( ))` is read as a VARIABLE NAME and the shell dies with `<word>: unbound variable`, exit 1. Python would happily raise a `ValueError` somewhere unrelated, or worse, coerce. See DEFECT 2 in the module docstring for why this arm is reachable at all.
    """
    text = word.strip()
    if re.fullmatch(r"[+-]?[0-9]+", text):
        return int(text)
    if text == "":
        return 0
    raise Aborted("claude-review-gate.sh: %s: %s: unbound variable" % (context, text), code=1)


# --------------------------------------------------------------------------- The two comment reads the gate does for itself. ---------------------------------------------------------------------------


def last_marker_sha(repo: str, pr: str) -> str:
    """`last_marker_sha` (twin :120-124). SEE DEFECT 1: a gh failure reads empty.

    `--paginate` runs `--jq` PER PAGE, so matching bodies stream out flat; the
    SHA is then extracted from EVERY line and the last taken, never `tail` first.
    """
    rc, out = _gh(
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.body | startswith("%s")) | .body' % MARKER_PREFIX,
        ],
        quiet=True,
    )
    if rc != 0:
        # `| sed | tail -n 1 || true`. The swallow, kept.
        return ""
    return marker_sha_from_bodies(out)


def last_marker_id(repo: str, pr: str) -> str:
    """`last_marker_id` (twin :126-130). Same swallow, smaller blast radius."""
    rc, out = _gh(
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.body | startswith("%s")) | .id' % MARKER_PREFIX,
        ],
        quiet=True,
    )
    if rc != 0:
        return ""
    return last_line(out)


# --------------------------------------------------------------------------- GATE MODE ---------------------------------------------------------------------------


def emit(output_path: str, go: str, pr: str, head_sha: str, last_sha: str, reason: str) -> None:
    """`emit` (twin :133-142). Terminal: writes four keys and exits 0."""
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write("go=%s\n" % go)
        handle.write("pr_number=%s\n" % pr)
        handle.write("head_sha=%s\n" % head_sha)
        handle.write("last_reviewed_sha=%s\n" % last_sha)
    log.info(
        "go=%s pr=%s head=%s last=%s -- %s"
        % (go, pr or "?", head_sha or "?", last_sha or "<none>", reason)
    )
    raise Done(0)


def emit_review_turns(output_path: str, repo: str, pr: str) -> None:
    """`emit_review_turns` (twin :149-178). SEE DEFECT 2 for the missing guard."""
    rc, changed = _gh(
        [
            "pr",
            "view",
            pr,
            "--repo",
            repo,
            "--json",
            "additions,deletions",
            "--jq",
            ".additions + .deletions",
        ],
        quiet=True,
    )
    if rc != 0:
        changed = "0"
    n = _arith_or_die(changed or "0", "line 172")
    kloc = (n + 999) // 1000
    turns = kloc * TURNS_PER_KLOC
    # `[[ "$turns" -lt "$min_turns" ]] && turns="$min_turns"`, then the same for
    # the ceiling. Spelled as clamps because ruff's PLR1730 requires it; the
    # order is the twin's, so a MIN above a MAX would still resolve to the MAX.
    turns = max(turns, MIN_TURNS)
    turns = min(turns, MAX_TURNS)
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write("review_turns=%d\n" % turns)
    log.info("diff size %s lines -> review_turns=%d" % (changed or "0", turns))


def emit_prompt(output_path: str, template: pathlib.Path, fields: dict[str, str]) -> int:
    """`emit_prompt` (twin :216-256). THE ONLY SUBSTITUTION POINT.

    RENDER FIRST, APPEND SECOND, and the ordering is the point rather than
    style. The block used to be `{ echo delim; sed ...; echo delim; } >> $GITHUB_
    OUTPUT` under `bash -e`, so when sed died the OPENING delimiter had already been written and the closing one never was, and GitHub then reported `Invalid value. Matching delimiter not found 'CLAUDE_REVIEW_PROMPT_EOF'` over the real error. A corrupted `$GITHUB_OUTPUT` also poisons every later step's outputs.

    REAL `sed` RUNS HERE, with the twin's six expressions in the twin's order, because its stdout is the product and its stderr is what a caller reads when a template goes missing.
    """
    argv = ["sed"]
    for placeholder in (
        "{{REPO}}",
        "{{PR_NUMBER}}",
        "{{HEAD_SHA}}",
        "{{LAST_REVIEWED_SHA}}",
        "{{EPIC_ID}}",
        "{{EPIC_SCOPE}}",
    ):
        argv += ["-e", "s|%s|%s|g" % (placeholder, sed_replacement(fields[placeholder]))]
    argv.append(str(template))
    proc = subprocess.run(argv, stdout=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        # `echo`, not `log_error`: no colour even on a tty. Kept.
        sys.stderr.write("✗ prompt template did not render; $GITHUB_OUTPUT left untouched\n")
        sys.stderr.flush()
        return 1
    rendered = (proc.stdout or b"").decode("utf-8", "replace").rstrip("\n")
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write("prompt<<%s\n" % PROMPT_DELIMITER)
        handle.write("%s\n" % rendered)
        handle.write("%s\n" % PROMPT_DELIMITER)
    return 0


def epic_scope_text(epic: str) -> str:
    """`{{EPIC_SCOPE}}` (twin :218-226): a real instruction, or nothing at all.

    Empty for a flat review, so the flat prompt stays byte-identical to what it was before epics existed.
    """
    if not epic:
        return ""
    return (
        "SCOPE: this pass reviews ONLY epic %s. Its commits are\n"
        "`git log --grep='^PR-TASK: %s'`, and its intent, its worklist items and\n"
        "their evidence are printed by\n"
        "`.review-scripts/.ci/scripts/review/epic-context.sh %s` -- read that\n"
        "FIRST, because it is the context you would otherwise spend turns rediscovering.\n"
        "Changes belonging to other epics are reviewed by their own pass; do not review\n"
        "them here, and do not report them as gaps." % (epic, epic, epic)
    )


def review_report_count(repo: str, pr: str, epic: str) -> tuple[int, int]:
    """`review_report_count` (common.sh:589-596). Returns (count, exit-code).

    KEYS ON THE HEADER ALONE, which is a PRODUCER CONSTANT this file writes verbatim rather than a description of one. common.sh:560-573 records what a content qualifier cost: it undercounted every measured PR, "#551 counted 0 of 1 (a completed, marked review costing $4.66 registering as never having happened), #550 5 of 7, #546 3 of 7, #543 1 of 9". Never re-add one.
    """
    needle = review_budget.REPORT_NEEDLE
    if epic:
        needle = review_budget.REPORT_EPIC_NEEDLE % epic
    rc, out = gh_retry(
        "review_report_count",
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.user.login | contains("%s"))\n'
            '                  | select(.body | startswith("%s"))\n'
            "                  | .id" % (review_budget.REPORT_AUTHOR_SUBSTRING, needle),
        ],
    )
    if rc != 0:
        return 0, rc
    if out == "":
        # `wc -l <<<""` reads as ONE line, not zero. Guarded explicitly, exactly as the twin guards it.
        return 0, 0
    return len(out.split("\n")), 0


def review_attempt_states(repo: str, pr: str, prefix: str) -> tuple[list, int]:
    """`review_attempt_states` (common.sh:686-703). Returns (states, exit-code).

    The bodies are streamed with a `---REVIEW-ATTEMPT-EOF---` sentinel between them because a marker body is multi-line and jq cannot express "the count and the class are lines within it". The parse is `review_budget.parse_attempt_ states`, which is the twin's awk exactly.
    """
    rc, out = gh_retry(
        "review_attempt_states",
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.body | startswith("%s")) | .body, "%s"'
            % (prefix, review_budget.ATTEMPT_EOF),
        ],
    )
    if rc != 0:
        return [], rc
    return review_budget.parse_attempt_states(out), 0


def pr_diff_loc(repo: str, pr: str) -> int:
    """`pr_diff_loc` (common.sh:766-772). additions + deletions, or 0.

    "Failing to 0 puts an unreadable PR in the SMALLEST bucket, which is the conservative direction: it spends fewer review passes, never more." Note the numeric guard here that `emit_review_turns` does not have (DEFECT 2).
    """
    rc, out = _gh(
        [
            "pr",
            "view",
            pr,
            "--repo",
            repo,
            "--json",
            "additions,deletions",
            "--jq",
            ".additions + .deletions",
        ],
        quiet=True,
    )
    if rc != 0:
        return review_budget.DIFF_LOC_FAILS_TO_ZERO
    if not re.fullmatch(r"[0-9]+", out):
        return review_budget.DIFF_LOC_FAILS_TO_ZERO
    return int(out)


def submodule_paths() -> str:
    """`git config -f .gitmodules --get-regexp '^submodule\\..*\\.path$' | awk '{print $2}'`.

    Reads `.gitmodules` in the CURRENT DIRECTORY, which is the twin's behaviour: a run from the wrong cwd sees no submodules and reads a pointer bump as a real change, which fails OPEN into a review rather than skipping one.
    """
    try:
        proc = subprocess.run(
            ["git", "config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return ""
    raw = (proc.stdout or b"").decode("utf-8", "replace")
    if proc.returncode != 0:
        # `|| true` after the pipe: awk still ran, on nothing.
        raw = ""
    return awk_second_fields(raw).rstrip("\n")


def run_gate() -> int:
    """The default arm: decide, then assemble the prompt."""
    output_path = common.require_var("GITHUB_OUTPUT")
    # `_repo()` IS CALLED LAZILY, at each point the twin first expands
    # `${GITHUB_REPOSITORY}`. Reading it here instead would abort before
    # `Unsupported EVENT_NAME` and before `require_var PR_NUMBER`, which are the two refusals the twin reaches first when both are unset.
    epic = os.environ.get("REVIEW_EPIC", "")
    event = os.environ.get("EVENT_NAME", "")
    log.step("Deciding whether a Claude review should run (event: %s)" % (event or "unset"))

    pr = ""
    head_sha = ""

    if event == "workflow_run":
        if os.environ.get("WR_EVENT", "") != "pull_request":
            emit(output_path, "false", "", "", "", "CI run was not a PR run")
        if os.environ.get("WR_CONCLUSION", "") != "success":
            emit(output_path, "false", "", "", "", "CI run not green")
        # `workflow_run.pull_requests[]` is unreliable; resolve via the branch and
        # PIN TO THE RUN'S SHA. `headRefOid == WR_HEAD_SHA` is the "current head
        # is green RIGHT NOW" invariant: a superseded push fails it, so a late-finishing green run for an old commit never reviews stale code.
        wr_head_sha = os.environ.get("WR_HEAD_SHA", "")
        repo = _repo()
        rc, pr_json = _gh(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--head",
                os.environ.get("WR_HEAD_BRANCH", ""),
                "--state",
                "open",
                "--json",
                "number,headRefOid,isDraft",
                "--jq",
                '[.[] | select(.headRefOid == "%s")] | first // empty' % wr_head_sha,
            ]
        )
        if rc != 0:
            # No `||` on this assignment: `set -e` takes gh's own status.
            raise Done(rc)
        if not pr_json:
            emit(output_path, "false", "", "", "", "no open PR currently at this head SHA")
        _, pr = _jq(["-r", ".number"], stdin=pr_json)
        _, is_draft = _jq(["-r", ".isDraft"], stdin=pr_json)
        if is_draft != "false":
            emit(output_path, "false", pr, "", "", "PR is a draft")
        head_sha = wr_head_sha
    elif event in ("pull_request", "workflow_dispatch"):
        # pull_request: ready_for_review (console) or opened (submodules).
        # workflow_dispatch: manual re-review; PR number arrives via input.
        pr = common.require_var("PR_NUMBER")
        head_sha = os.environ.get("PR_HEAD_SHA", "")
        if not head_sha:
            rc, head_sha = _gh(
                [
                    "pr",
                    "view",
                    pr,
                    "--repo",
                    _repo(),
                    "--json",
                    "headRefOid",
                    "--jq",
                    ".headRefOid",
                ],
                quiet=True,
            )
            if rc != 0:
                emit(output_path, "false", pr, "", "", "cannot resolve PR head")
        required_check = os.environ.get("REQUIRED_CHECK", "")
        if required_check:
            rc, conclusion = _gh(
                [
                    "api",
                    "-X",
                    "GET",
                    "repos/%s/commits/%s/check-runs" % (_repo(), head_sha),
                    "-f",
                    "check_name=%s" % required_check,
                    "--jq",
                    '[.check_runs[] | select(.conclusion == "success")] | length',
                ],
                quiet=True,
            )
            if rc != 0:
                emit(output_path, "false", pr, head_sha, "", "check-runs lookup failed")
            if _arith_or_die(conclusion or "0", "line 819") < 1:
                emit(
                    output_path,
                    "false",
                    pr,
                    head_sha,
                    "",
                    "%s is not green on the current head" % required_check,
                )
        else:
            # REQUIRED_CHECK empty = no green gate: the submodule repos have no
            # PR CI of their own (validation lives in console CI), so there is no
            # signal to wait for; marker dedup alone bounds re-review cost.
            log.info("no required check configured; green gate skipped")
    else:
        log.error("Unsupported EVENT_NAME: %s" % (event or "unset"))
        raise Done(1)

    repo = _repo()
    reports_posted, rc = review_report_count(repo, pr, epic)
    if rc != 0:
        raise Done(rc)
    # Fetched ONCE: the cap needs the chargeable total and the per-head ceiling needs this head's own row, and paying for the same paginated listing twice on every invocation is how a cheap guard becomes an expensive one.
    attempt_states, rc = review_attempt_states(repo, pr, ATTEMPT_PREFIX)
    if rc != 0:
        raise Done(rc)
    attempts_spent = review_budget.chargeable_attempts(attempt_states)

    # THE PER-HEAD CEILING, checked BEFORE the cap so the message names the real reason. Free re-attempts have to end somewhere and it cannot be the per-PR cap alone: the free ones are not charged, so without this a head that dies infra-class could be retried forever at no visible cost.
    head_attempts, head_class = review_budget.head_attempt_state(attempt_states, head_sha)
    if review_budget.head_is_exhausted(attempt_states, head_sha):
        emit(
            output_path,
            "false",
            pr,
            head_sha,
            "",
            "head %s has spent all %d attempts (%d recorded, class %s); "
            "push a change to earn another pass"
            % (
                head_sha[:7],
                review_budget.REVIEW_MAX_ATTEMPTS_PER_HEAD,
                head_attempts,
                head_class,
            ),
        )

    # Budget is what was SPENT, not what was delivered: a pass that burned its turns and posted nothing cost the same as one that posted a full report, and charging only for successes is what let a failing SHA be re-reviewed forever. PER-EPIC, because a flat count spends the whole cap on the first round and every epic reviewed later is refused forever.
    review_count = review_budget.spend_total(reports_posted, attempts_spent)
    loc = pr_diff_loc(repo, pr)
    max_reviews = review_budget.cap_for(loc)
    if review_count >= max_reviews:
        emit(
            output_path,
            "false",
            pr,
            head_sha,
            "",
            "review cap reached (%d/%d spent: %d report(s) posted, %d attempt(s) that "
            "produced none; cap is %d for a %d-line diff)"
            % (review_count, max_reviews, reports_posted, attempts_spent, max_reviews, loc),
        )
    log.info(
        "review budget: %d/%d spent (%d posted, %d produced nothing; %d changed lines)"
        % (review_count, max_reviews, reports_posted, attempts_spent, loc)
    )

    last_sha = last_marker_sha(repo, pr)
    fields = {
        "{{REPO}}": repo,
        "{{PR_NUMBER}}": pr,
        "{{HEAD_SHA}}": head_sha,
        "{{LAST_REVIEWED_SHA}}": last_sha,
        "{{EPIC_ID}}": epic,
        "{{EPIC_SCOPE}}": epic_scope_text(epic),
    }
    if last_sha:
        if last_sha == head_sha:
            emit(output_path, "false", pr, head_sha, last_sha, "head already reviewed")
        # Delta since the last ACTUALLY reviewed SHA (markers never advance on
        # skips). The compare API needs no local history; on failure we fail OPEN
        # into an incremental review rather than silently skipping. `files[]` caps at 300 entries, which cannot mask an all-gitlink diff.
        rc, files_json = _gh(
            [
                "api",
                "repos/%s/compare/%s...%s" % (repo, last_sha, head_sha),
                "--jq",
                "[.files[]?.filename]",
            ],
            quiet=True,
        )
        if rc != 0:
            files_json = ""
        if files_json:
            _, length = _jq(["length"], stdin=files_json)
            if _arith_or_die(length or "0", "line 879") == 0:
                emit(
                    output_path,
                    "false",
                    pr,
                    head_sha,
                    last_sha,
                    "empty diff since last reviewed SHA",
                )
            subs = submodule_paths()
            _, listed = _jq(["-r", ".[]"], stdin=files_json)
            non_gitlink = grep_fixed_inverse(listed.split("\n") if listed else [], subs)
            if not non_gitlink:
                emit(
                    output_path,
                    "false",
                    pr,
                    head_sha,
                    last_sha,
                    "only submodule pointer bumps since %s" % last_sha[:7],
                )
        else:
            log.warn(
                "compare %s...%s failed -- reviewing anyway (incremental)"
                % (last_sha[:7], head_sha[:7])
            )
        emit_review_turns(output_path, repo, pr)
        if emit_prompt(output_path, script_dir() / "prompts" / "followup.md", fields) != 0:
            raise Done(1)
        emit(
            output_path,
            "true",
            pr,
            head_sha,
            last_sha,
            "follow-up review: delta since %s" % last_sha[:7],
        )

    emit_review_turns(output_path, repo, pr)
    if emit_prompt(output_path, script_dir() / "prompts" / "initial.md", fields) != 0:
        raise Done(1)
    emit(output_path, "true", pr, head_sha, "", "initial review: full PR diff")
    return 0


# --------------------------------------------------------------------------- --post-report ---------------------------------------------------------------------------


def run_post_report() -> int:
    """Post the review report when the ACTION could not.

    `track_progress` (which makes the action post/update the report comment itself) is rejected by the action for any event outside
    pull_request/issues/issue_comment/pull_request_review{,_comment}, so on the
    workflow_run entry point the action runs in AGENT mode, creates no tracking comment at all, and leaves the report existing only as the model's final text inside the execution file. Posting it from here gives both entry points one shape of report, with the action's OWN header prefix ("**Claude finished ..."), which is the signature `review_report_count`,
    `check-review-report-replies.sh` and `--post-findings` all match on.
    """
    pr = common.require_var("PR_NUMBER")
    head_sha = common.require_var("HEAD_SHA")
    epic = os.environ.get("REVIEW_EPIC", "")

    report = ""
    execution_file = os.environ.get("EXECUTION_FILE", "")
    if execution_file and os.path.isfile(execution_file):
        rc, out = _jq(["-r", RESULT_TEXT_JQ, execution_file], quiet=True)
        report = out if rc == 0 else ""
    if not report:
        # Fail OPEN, not closed: `--mark` is the honesty guard and will refuse to stamp the SHA when nothing posted, so the SHA stays retryable.
        log.warn("no final report text in %s; nothing to post" % (execution_file or "<unset>"))
        return 0

    if len(report) > REPORT_LIMIT:
        # GitHub rejects issue-comment bodies over 65536 chars with a 422, which would fail this step and strand the SHA in a permanent retry loop. Keep the HEAD (verdict + findings prose) AND the TAIL (the findings fence `--post-findings` parses) rather than a plain truncation.
        log.warn("report is %d chars; truncating the middle to fit the comment limit" % len(report))
        report = (
            report[:REPORT_HEAD]
            + "\n\n_[report truncated: middle omitted to fit GitHub's comment size limit]_\n\n"
            + report[-REPORT_TAIL:]
        )

    body = "**Claude finished%s the automated review of %s**\n\n---\n\n%s" % (
        (" (epic %s)" % epic) if epic else "",
        head_sha[:7],
        report,
    )
    rc = _gh_write(
        [
            "api",
            "-X",
            "POST",
            "repos/%s/issues/%s/comments" % (_repo(), pr),
            "-f",
            "body=%s" % body,
        ]
    )
    if rc != 0:
        # No `||`: `set -e` ends the step with gh's status.
        raise Done(rc)
    log.info("Posted review report for %s (%d chars)" % (head_sha[:7], len(report)))
    return 0


# --------------------------------------------------------------------------- --post-findings ---------------------------------------------------------------------------


def run_post_findings() -> int:
    """Line-anchored review comments with severity badges, from the report fence.

    The model's final report text is the ONLY channel proven to escape the action sandbox, so inline posting is done HERE, deterministically, via github_token. ADVISORY BY DESIGN: per-comment failures (line not in diff, stale position) are logged and skipped, and this mode never fails the job -- the summary report already posted, and a failure here would skip the following
    `--mark`.
    """
    pr = common.require_var("PR_NUMBER")
    head_sha = common.require_var("HEAD_SHA")
    repo = _repo()

    rc, bodies = _gh(
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.user.login | contains("github-actions"))\n'
            '                  | select(.body | contains("%s")) | .body' % FINDINGS_FENCE,
        ],
        quiet=True,
    )
    # A mid-pagination gh failure degrades to empty -> advisory skip, never an abort that would fail this step and skip the following `--mark`.
    findings_json = extract_findings_fence(bodies) if rc == 0 else ""
    if not findings_json or not _jq_test(["-e", 'type == "array"'], stdin=findings_json):
        log.info("no parseable review-findings block; skipping inline comments")
        return 0

    posted = 0
    skipped = 0
    _, sorted_out = _jq(["-c", FINDINGS_SORT_JQ], stdin=findings_json, quiet=True)
    for finding in sorted_out.split("\n"):
        if not finding:
            continue
        _, path = _jq(["-r", ".path // empty"], stdin=finding)
        _, fline = _jq(["-r", ".line // empty"], stdin=finding)
        _, sev = _jq(["-r", '.severity // "medium" | ascii_upcase'], stdin=finding)
        _, title = _jq(["-r", '.title // "finding"'], stdin=finding)
        _, fbody = _jq(["-r", ".body // empty"], stdin=finding)
        if not path or not fline:
            skipped += 1
            continue
        rc = _gh_write(
            [
                "api",
                "-X",
                "POST",
                "repos/%s/pulls/%s/comments" % (repo, pr),
                "-f",
                "commit_id=%s" % head_sha,
                "-f",
                "path=%s" % path,
                "-F",
                "line=%s" % fline,
                "-f",
                "side=RIGHT",
                # U+2014 by escape, see the module docstring.
                "-f",
                "body=**[%s]** \u2014 %s\n\n%s" % (sev, title, fbody),
            ],
            quiet=True,
        )
        if rc == 0:
            posted += 1
        else:
            skipped += 1
            log.warn("inline comment rejected (line not in diff?): %s:%s" % (path, fline))
    log.info(
        "inline findings: %d posted, %d skipped (cap %d)" % (posted, skipped, INLINE_COMMENT_CAP)
    )
    return 0


# --------------------------------------------------------------------------- --apply-labels ---------------------------------------------------------------------------


def is_managed(name: str) -> bool:
    """`is_managed` (twin :398-406). The whitelist, and nothing else."""
    return name in MANAGED_LABELS


def run_apply_labels() -> int:
    """Label the PR from the review pass that just ran. ADVISORY END TO END.

    Two inputs, in this order of trust:

      1. A MECHANICAL FLOOR derived from the changed paths alone. It needs no
         model output, so it still lands when the review starved and posted
         nothing, which is why the workflow runs this step under `always()`.
      2. The model's verdict, carried in a `json:pr-labels` fence at the end of
         the same report `--post-report` posts. That text is the only channel
         proven to escape the action sandbox and it is already being produced:
         zero extra invocations, zero extra turns, nothing in `review_spend_total`.

    Every failure below logs and returns 0. A label is never worth failing the review job or blocking a merge over.
    """
    pr = common.require_var("PR_NUMBER")
    head_sha = common.require_var("HEAD_SHA")
    repo = _repo()

    desired: list[str] = []

    def add_desired(name: str) -> None:
        if not is_managed(name):
            log.warn("refusing to apply '%s': not in the managed label set" % name)
            return
        if name in desired:
            return
        desired.append(name)

    # --- 1. the mechanical floor -------------------------------------------
    rc, changed = _gh(
        [
            "api",
            "repos/%s/pulls/%s/files" % (repo, pr),
            "--paginate",
            "--jq",
            ".[].filename",
        ],
        quiet=True,
        stdin_null=True,
    )
    if rc != 0:
        changed = ""
    if not changed:
        log.warn(
            "could not read the changed-file list for PR %s; skipping the mechanical labels" % pr
        )
    else:
        # ALL-FILES rules, conservative by construction: one stray source file and the label does not apply. "This diff is entirely docs" and "this diff is entirely CI plumbing" are facts about the file list, so they need no model to see them and no model can talk them out of them.
        lines = changed.split("\n")
        if all(DOCS_ONLY_RE.search(line) for line in lines):
            add_desired("documentation")
        if all(CI_ONLY_RE.search(line) for line in lines):
            add_desired("ci")

    # --- 2. the model's verdict --------------------------------------------
    verdict = ""
    execution_file = os.environ.get("EXECUTION_FILE", "")
    if execution_file and os.path.isfile(execution_file):
        rc, report = _jq(["-r", RESULT_TEXT_JQ, execution_file], quiet=True)
        if rc != 0:
            report = ""
        verdict = extract_labels_fence(report)

    if not verdict:
        # FALLBACK: the fence may live only in the POSTED COMMENT. Observed on the feature's first live run (#559, run 31267699743): the model posted its summary itself via `gh pr comment` and put the fence THERE, while
        # its final result text did not repeat it. The result text stays primary;
        # the newest fence-bearing comment is the fallback. A forged fence cannot do more than a forged marker could: the whitelist hard-filters every label and bump-major is never applied automatically.
        rc, comment_report = _gh(
            [
                "api",
                "repos/%s/issues/%s/comments" % (repo, pr),
                "--paginate",
                "--jq",
                '.[] | select(.body | contains("```%s")) | .body' % LABELS_FENCE,
            ],
            quiet=True,
        )
        if rc != 0:
            comment_report = ""
        else:
            # `tail -c 65536`, which is BYTES, not characters.
            raw = comment_report.encode("utf-8")[-65536:]
            comment_report = raw.decode("utf-8", "replace")
        if comment_report:
            verdict = extract_labels_fence(comment_report)
            if verdict:
                log.info(
                    "json:pr-labels fence found in the posted report comment "
                    "(absent from the result text)"
                )

    if not verdict:
        log.info("no json:pr-labels block in the report; mechanical labels only")
    elif not _jq_test(["-e", LABEL_VERDICT_VALID_JQ], stdin=verdict):
        # STRICT, and malformed is treated as ABSENT rather than as a partial answer: a half-parsed verdict is how a hallucinated field would get a vote. The mechanical floor above still applies.
        log.warn("the json:pr-labels block did not validate; treating it as absent")
    else:
        _, bump = _jq(["-r", '.bump // "patch"'], stdin=verdict)
        _, why = _jq(["-r", '(.why // "") | .[0:200]'], stdin=verdict)
        _, kinds_compact = _jq(["-rc", ".kind // []"], stdin=verdict)
        log.info("review verdict: bump=%s kind=%s why=%s" % (bump, kinds_compact, why or "<none>"))
        if bump == "none":
            # The ONLY verdict that subtracts a release, and safe on the model's word in a way `major` is not: a wrong `none` costs a release the next release-worthy merge picks up anyway, while a wrong `major` is a permanent statement to every consumer of the version stream.
            add_desired("bump-none")
        elif bump == "minor":
            add_desired("bump-minor")
        elif bump == "major":
            log.warn(
                "the review RECOMMENDS a major bump (%s). bump-major is never applied "
                "automatically; apply it by hand if you agree." % (why or "no reason given")
            )
        _, kinds = _jq(["-r", "(.kind // [])[]"], stdin=verdict)
        for kind in kinds.split("\n"):
            if not kind:
                continue
            if kind == "bug":
                add_desired("bug")
            elif kind == "feature":
                add_desired("enhancement")
            elif kind == "docs":
                add_desired("documentation")
            elif kind == "ci":
                add_desired("ci")

    # --- 3. reconcile against the ledger, never a blind sync --------------- The ledger records what THIS arm applied last time. Removal is scoped to that record, so a hand-applied label -- full-ci, rollback, a human's bump-minor -- is never touched no matter what the model says. It is also re-filtered through the managed set on the way out: the ledger is a PR comment, and a
    # comment is editable by anyone with write access, so a tampered "applied:" line must not become a delete-arbitrary-label primitive.
    rc, ledger_bodies = _gh(
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.body | startswith("%s")) | .body' % LEDGER_PREFIX,
        ],
        quiet=True,
        stdin_null=True,
    )
    prev = ""
    if rc == 0:
        applied_lines = [
            APPLIED_RE.sub("", line) for line in ledger_bodies.split("\n") if APPLIED_RE.match(line)
        ]
        prev = applied_lines[-1] if applied_lines else ""
    if prev:
        for stale in split_ledger_labels(prev):
            if not stale:
                continue
            if stale in desired:
                continue
            if not is_managed(stale):
                log.warn(
                    "ledger names '%s', which is not in the managed set; refusing to remove it"
                    % stale
                )
                continue
            if (
                _gh_write(
                    ["api", "-X", "DELETE", "repos/%s/issues/%s/labels/%s" % (repo, pr, stale)],
                    quiet=True,
                    stdin_null=True,
                )
                == 0
            ):
                log.info("removed stale label '%s'" % stale)
            else:
                log.warn("could not remove the stale label '%s'" % stale)

    for label in desired:
        row = ""
        for candidate in CREATE_ON_DEMAND_LABELS:
            if candidate.split("|", 1)[0] == label:
                row = candidate
        if (
            row
            and _gh_write(
                ["api", "repos/%s/labels/%s" % (repo, label)], quiet=True, stdin_null=True
            )
            != 0
        ):
            rest = row.split("|", 1)[1]
            if (
                _gh_write(
                    [
                        "api",
                        "-X",
                        "POST",
                        "repos/%s/labels" % repo,
                        "-f",
                        "name=%s" % label,
                        "-f",
                        "color=%s" % rest.split("|", 1)[0],
                        "-f",
                        "description=%s" % rest.split("|", 1)[1],
                    ],
                    quiet=True,
                    stdin_null=True,
                )
                != 0
            ):
                log.warn("could not create the '%s' label" % label)
        if (
            _gh_write(
                [
                    "api",
                    "-X",
                    "POST",
                    "repos/%s/issues/%s/labels" % (repo, pr),
                    "-f",
                    "labels[]=%s" % label,
                ],
                quiet=True,
            )
            != 0
        ):
            log.warn("could not apply the label '%s'" % label)

    applied = csv_of(desired)
    body = "%s %s -->\napplied: %s" % (LEDGER_PREFIX, head_sha, applied)
    rc, ledger_ids = _gh(
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.body | startswith("%s")) | .id' % LEDGER_PREFIX,
        ],
        quiet=True,
        stdin_null=True,
    )
    ledger_id = last_line(ledger_ids) if rc == 0 else ""
    if ledger_id:
        if (
            _gh_write(
                [
                    "api",
                    "-X",
                    "PATCH",
                    "repos/%s/issues/comments/%s" % (repo, ledger_id),
                    "-f",
                    "body=%s" % body,
                ],
                quiet=True,
                stdin_null=True,
            )
            != 0
        ):
            log.warn("could not update the label ledger comment")
    elif (
        _gh_write(
            [
                "api",
                "-X",
                "POST",
                "repos/%s/issues/%s/comments" % (repo, pr),
                "-f",
                "body=%s" % body,
            ],
            quiet=True,
            stdin_null=True,
        )
        != 0
    ):
        log.warn("could not post the label ledger comment")
    log.info("labels for %s: %s" % (head_sha[:7], applied or "<none>"))
    return 0


# --------------------------------------------------------------------------- --mark ---------------------------------------------------------------------------


def run_mark() -> int:
    """Upsert the reviewed-SHA marker, or record a SPENT ATTEMPT.

    A review that burned its budget and produced nothing still COST money, and until 2026-07-30 it cost it for free: the step failed, every following step was skipped by implicit `success()`, no marker was written, and `review_report_count` (which counts POSTED reports) stayed at zero, so the cap never advanced and the same SHA was re-reviewed at full price on every subsequent
    green push, able to fail identically forever.

    An attempt marker is deliberately NOT a reviewed marker: its own prefix keeps it invisible to `last_marker_sha` (a spent attempt must never suppress a later genuine review of the same SHA by pretending the code was read) while `review_chargeable_attempts` does see it, so it consumes budget.
    """
    pr = common.require_var("PR_NUMBER")
    head_sha = common.require_var("HEAD_SHA")
    execution_file = os.environ.get("EXECUTION_FILE", "")

    if os.environ.get("REVIEW_OUTCOME", "") != "success":
        why = "review step did not succeed"
        if execution_file and os.path.isfile(execution_file):
            rc, subtype = _jq(["-r", RESULT_SUBTYPE_JQ, execution_file], quiet=True)
            if rc != 0:
                subtype = ""
            if subtype:
                why = subtype

        repo = _repo()
        rc, attempt_ids = _gh(
            [
                "api",
                "repos/%s/issues/%s/comments" % (repo, pr),
                "--paginate",
                "--jq",
                '.[] | select(.body | startswith("%s"))\n'
                '                      | select(.body | contains("%s")) | .id'
                % (ATTEMPT_PREFIX, head_sha),
            ],
            quiet=True,
            stdin_null=True,
        )
        attempt_id = last_line(attempt_ids) if rc == 0 else ""
        # SEE DEFECT 3: the twin nests this fetch inside another command substitution, so its failure is discarded and the count restarts at 1.
        states, _ = review_attempt_states(repo, pr, ATTEMPT_PREFIX)
        prior_attempts, _prior_class = review_budget.head_attempt_state(states, head_sha)
        attempts = prior_attempts + 1

        # ONE MARKER PER HEAD, upserted with its own attempt count (2026-08-09). The marker used to be POSTed fresh on every failure, so N deaths on one head meant N comments and N charged units. On PR #560 an `error_max_turns` told a fully-green, autopilot-driven PR to "push a change to earn another pass" when there was no legitimate change to push, and the loop stalled behind a
        # human.
        if (
            review_budget.class_is_infra(why)
            and attempts <= review_budget.REVIEW_FREE_REATTEMPTS_PER_HEAD
        ):
            verdict_line = (
                "That is an INFRASTRUCTURE-class failure, not a verdict on the code, so it "
                "does not\nclose this head's budget yet: attempt %d of %d.\n"
                "Re-run it on the same head, no push required:\n"
                "`gh workflow run claude-review.yml --ref <this PR's branch> -f pr_number=%s`"
                % (attempts, review_budget.REVIEW_MAX_ATTEMPTS_PER_HEAD, pr)
            )
        else:
            verdict_line = (
                "That is attempt %d of %d on this head, so it counts against this PR's\n"
                "review budget because it spent real turns and tokens.\n"
                "Push a change to earn another pass."
                % (attempts, review_budget.REVIEW_MAX_ATTEMPTS_PER_HEAD)
            )

        body = (
            "%s %s -->\nattempts: %d\nclass: %s\n"
            "A review pass was attempted on `%s` and produced no report (`%s`).\n%s"
            % (ATTEMPT_PREFIX, head_sha, attempts, why, head_sha[:7], why, verdict_line)
        )
        if attempt_id:
            if (
                _gh_write(
                    [
                        "api",
                        "-X",
                        "PATCH",
                        "repos/%s/issues/comments/%s" % (repo, attempt_id),
                        "-f",
                        "body=%s" % body,
                    ],
                    quiet=True,
                    stdin_null=True,
                )
                != 0
            ):
                log.warn("could not update the spent attempt for %s" % head_sha[:7])
        elif (
            # `-X POST` EXPLICITLY. gh infers it from `-f`, but leaving it implicit made this write indistinguishable from a read to anything parsing the argv, including this pipeline's own test harness, which served it a fixture instead of capturing it.
            _gh_write(
                [
                    "api",
                    "-X",
                    "POST",
                    "repos/%s/issues/%s/comments" % (repo, pr),
                    "-f",
                    "body=%s" % body,
                ],
                quiet=True,
                stdin_null=True,
            )
            != 0
        ):
            log.warn("could not record the spent attempt for %s" % head_sha[:7])
        log.info(
            "recorded SPENT ATTEMPT %d/%d for %s (%s); it does not mark the SHA reviewed"
            % (attempts, review_budget.REVIEW_MAX_ATTEMPTS_PER_HEAD, head_sha[:7], why)
        )
        return 0

    # A marker is a CLAIM that a review happened. Step success alone proved false once: the reviewer "succeeded" with 36 permission denials and posted nothing, and the marker then suppressed the retry.
    #
    # EVERY BOOKKEEPING PREFIX IS EXCLUDED, not just the marker. The guard asks "did this review produce OUTPUT", and only a report or an inline comment answers that. Counting the attempt marker or the label ledger would let the pipeline satisfy its own honesty guard with a comment it wrote seconds earlier about itself.
    repo = _repo()
    rc, recent_ids = _gh_raw(
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.body | startswith("%s") | not)\n'
            '                  | select(.body | startswith("%s") | not)\n'
            '                  | select(.body | startswith("%s") | not)\n'
            '                  | select(.user.login | contains("github-actions"))\n'
            "                  | select(.created_at > (now - 3600 | todate)) | .id"
            % (MARKER_PREFIX, ATTEMPT_PREFIX, LEDGER_PREFIX),
        ],
        quiet=True,
    )
    recent = recent_ids.count("\n") if rc == 0 else 0
    rc, inline_ids = _gh_raw(
        [
            "api",
            "repos/%s/pulls/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            (
                '.[] | select(.user.login | contains("github-actions"))\n'
                "                  | select(.created_at > (now - 3600 | todate)) | .id"
            ),
        ],
        quiet=True,
    )
    inline = inline_ids.count("\n") if rc == 0 else 0
    if recent == 0 and inline == 0:
        log.error(
            "review step reported success but posted NOTHING in the last hour; refusing to "
            "mark %s (SHA stays retryable)" % head_sha[:7]
        )
        raise Done(1)

    # Cost transparency (operator request). Best-effort: a missing or unparseable file never blocks marking.
    cost_line = ""
    if execution_file and os.path.isfile(execution_file):
        rc, cost_line = _jq(["-r", COST_JQ, execution_file], quiet=True)
        if rc != 0:
            cost_line = ""
    body = "%s %s -->\nAutomated Claude review completed for commit %s.%s" % (
        MARKER_PREFIX,
        head_sha,
        head_sha[:7],
        ("\n%s" % cost_line) if cost_line else "",
    )
    comment_id = last_marker_id(repo, pr)
    if comment_id:
        rc = _gh_write(
            [
                "api",
                "-X",
                "PATCH",
                "repos/%s/issues/comments/%s" % (repo, comment_id),
                "-f",
                "body=%s" % body,
            ]
        )
        if rc != 0:
            raise Done(rc)
        log.info("Updated marker comment %s -> %s" % (comment_id, head_sha[:7]))
    else:
        rc = _gh_write(
            [
                "api",
                "-X",
                "POST",
                "repos/%s/issues/%s/comments" % (repo, pr),
                "-f",
                "body=%s" % body,
            ]
        )
        if rc != 0:
            raise Done(rc)
        log.info("Created marker comment for %s" % head_sha[:7])
    return 0


# --------------------------------------------------------------------------- Entry point ---------------------------------------------------------------------------


def _repo() -> str:
    """`${GITHUB_REPOSITORY}`, unbraced-default in the twin.

    With `set -u` and the variable unset the twin dies with `GITHUB_REPOSITORY: unbound variable` and exit 1, which names a line rather than a cause. Same exit code here, with the cause in words.
    """
    slug = os.environ.get("GITHUB_REPOSITORY", "")
    if not slug:
        raise Aborted(
            "claude-review-gate.sh: GITHUB_REPOSITORY: unbound variable "
            "(the twin aborts here under `set -u`)",
            code=1,
        )
    return slug


MODES = {
    "--post-report": run_post_report,
    "--post-findings": run_post_findings,
    "--apply-labels": run_apply_labels,
    "--mark": run_mark,
}


def main(argv: list[str]) -> int:
    """`$1` selects the arm; anything unrecognised falls through to gate mode.

    `require_cmd gh` and `require_cmd jq` run BEFORE the dispatch, for every arm, exactly as the twin runs them at :46-47.
    """
    try:
        common.require_cmd("gh")
        common.require_cmd("jq")
        mode = MODES.get(argv[0] if argv else "")
        return mode() if mode is not None else run_gate()
    except common.RefusalError as refusal:
        refusal.report()
        return refusal.code
    except Aborted as aborted:
        sys.stderr.write("%s\n" % aborted.message)
        sys.stderr.flush()
        return aborted.code
    except Done as done:
        return done.code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
