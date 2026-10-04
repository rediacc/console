#!/usr/bin/env python3
"""The PR-level Claude review gate: decide whether a review pass runs, then post its report, its inline findings and its marker.

THE INVARIANT, operator ruling 2026-07-22: a review fires ONLY for an open, non-draft, same-repo PR whose CURRENT head SHA has green CI at decision time, that is not already marked reviewed, and whose delta since the last reviewed SHA is not submodule pointer bumps only. A red push after a review gets no re-review until a later push completes green.

SAME-REPO IS ENFORCED ONE LEVEL UP. The workflow's job condition compares the head repository with `github.repository`, so a fork PR never reaches this module; nothing here can see the head repository.

ADVISORY BY DESIGN (agent/plans/PLAN-github-pr-review-restore.md, Design 6). Review Complete is never a required check: the blocking review is the per-commit one (`wl_review.py --check`), and this pass looks at the whole PR on top of it. Labels are NOT decided here; `rediacc_ci.review.pr_labels` owns the bump decision and its `<!-- claude-labels:` ledger, and no arm of this module writes that prefix.

FOUR ARMS, selected by the first argument (`ARMS`):

    (none)           decide go/no-go and assemble the prompt into $GITHUB_OUTPUT
    --post-report    post the model's final report as a PR comment under `REPORT_HEADER`
    --post-findings  turn the report's `json:review-findings` fence into inline comments
    --mark           upsert the reviewed-SHA marker, or record a spent attempt

THE GATE'S OUTPUTS, appended to `$GITHUB_OUTPUT`: `go`, `pr_number`, `head_sha`, `last_reviewed_sha` on every decision, plus `review_turns` and the multi-line `prompt` (delimited by `PROMPT_DELIMITER`) when `go=true`. The prompt is `prompts/initial.md` when no marker exists and `prompts/followup.md` otherwise, read from the directory beside this file, so the copy checked out from main as `.review-scripts`
reads main's prompts.

THE COMMENTS THIS MODULE WRITES, and the reason their prefixes differ:

  * `<!-- claude-reviewed: <sha40> -->` (`MARKER_PREFIX`), one per PR, PATCHed forward to each reviewed head. The LAST sha found in any marker body is the last reviewed head.
  * `<!-- claude-review-attempt: <sha40> -->` (`ATTEMPT_PREFIX`), one per head that ran and produced no report, with `attempts:` and `class:` lines (`core.review_budget`). It must never satisfy the marker read: a pass that read nothing would otherwise suppress a later real review.
  * `**Claude finished the automated review of <sha7>**` (`REPORT_HEADER`), the report. `core.review_budget.report_count` counts reports by this prefix alone.

UNREADABLE STATE STOPS THE PASS. Every read whose failure could make a reviewed head look unreviewed (the report count, the attempt ledger, the marker) goes through `gh_retry` and, when it still fails, ends the decision with `go=false` or a nonzero exit, never with `go=true`. The marker read once swallowed its failure and answered "never reviewed", which re-reviewed an already-reviewed head at full price;
that is the regression `test_review_claude_review_gate.py` plants.

THE REVIEW BUILDS ON THE PER-COMMIT RECORDS. Both prompts point the model at `agent/reviews/<branch-slug>/` (`{{HEAD_REF_SLUG}}`, from `pr_labels.branch_slug`), where every commit already carries its own findings and resolutions, so the budget goes to what a single-commit diff cannot show.

    PYTHONPATH=.ci python3 -m rediacc_ci.review.claude_review_gate [--post-report|--post-findings|--mark]
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import re
import subprocess
import sys
import time
from typing import NoReturn

from rediacc_ci import log
from rediacc_ci.core import common, review_budget
from rediacc_ci.review import pr_labels

# --- the frozen API: review_status, the workflow and wl_prreview read these --------------------
MARKER_PREFIX = "<!-- claude-reviewed:"
ATTEMPT_PREFIX = "<!-- claude-review-attempt:"
REPORT_HEADER = review_budget.REPORT_NEEDLE
FINDINGS_FENCE = "json:review-findings"
PROMPT_DELIMITER = "CLAUDE_REVIEW_PROMPT_EOF"
ARMS = ("--post-report", "--post-findings", "--mark")

PROMPTS_DIR = pathlib.Path(__file__).resolve().parent / "prompts"
PLACEHOLDERS = (
    "{{REPO}}",
    "{{PR_NUMBER}}",
    "{{HEAD_SHA}}",
    "{{LAST_REVIEWED_SHA}}",
    "{{HEAD_REF_SLUG}}",
)
_UNRENDERED = re.compile(r"\{\{[A-Z_]+\}\}")

# Turn budget, scaled to diff size by DENSITY: measured the same day by the same reviewer, PR #552 completed at 22.0 turns/KLOC and PR #553 died at 17.8, while file count did not discriminate. TURNS_PER_KLOC sits above the measured survivor because one survival is not a floor.
TURNS_PER_KLOC = 25
# Breadth needs turns of its own: PR #594 (2026-10-04, run 37175939967) died at the 50-turn floor on 1,050 lines spread over 49 files, about 1 turn per file before the review was written. A file costs at least a read and a look at its context, so the budget is the larger of the density figure and TURNS_PER_FILE per changed file.
TURNS_PER_FILE = 2
MAX_TURNS = 140
MIN_TURNS = 50

# GitHub rejects a comment body over 65,536 characters. The middle is dropped rather than the tail, because the tail carries the findings fence `--post-findings` parses.
REPORT_LIMIT = 60000
REPORT_HEAD = 30000
REPORT_TAIL = 25000

INLINE_COMMENT_CAP = 20
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2}

MARKER_SHA_RE = re.compile(r".*claude-reviewed: ([0-9a-f]{40}).*")
# Every SHA and PR number from the environment or a gh answer is held to these before it reaches a jq filter or a REST path, so a quote cannot rewrite the filter and a slash cannot walk the path.
SHA40_RE = re.compile(r"[0-9a-f]{40}")
PR_NUMBER_RE = re.compile(r"[0-9]+")
_WS_CLASS = r"[ \t\r\f\v]*"
_FENCE_OPENER = re.compile(r"^%s```%s%s$" % (_WS_CLASS, re.escape(FINDINGS_FENCE), _WS_CLASS))
_FENCE_CLOSER = re.compile(r"^%s```%s$" % (_WS_CLASS, _WS_CLASS))


class Done(Exception):  # noqa: N818 -- a control-flow signal, not an error
    """End the arm with this exit code."""

    def __init__(self, code: int) -> None:
        super().__init__("exit %d" % code)
        self.code = code


# --------------------------------------------------------------------------- The gh seam. Tests replace `_gh_call` and `_sleep`. ---------------------------------------------------------------------------


def _gh_call(args: list[str]) -> tuple[int, str, str]:
    """Run `gh <args>` with stdin closed; (exit code, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["gh", *args],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return 127, "", ""
    return (
        proc.returncode,
        (proc.stdout or b"").decode("utf-8", "replace"),
        (proc.stderr or b"").decode("utf-8", "replace"),
    )


_sleep = time.sleep


def _gh(args: list[str], *, quiet: bool = False) -> tuple[int, str]:
    """One gh call; (exit code, stdout without trailing newlines). gh's stderr is replayed unless `quiet`."""
    rc, out, err = _gh_call(args)
    if err and not quiet:
        sys.stderr.write(err if err.endswith("\n") else err + "\n")
        sys.stderr.flush()
    return rc, out.rstrip("\n")


def gh_retry(what: str, args: list[str]) -> tuple[int, str]:
    """Up to three attempts, `attempt*3` seconds apart; on total failure a named error, gh's stderr indented, and a nonzero code."""
    rc = 0
    err = ""
    for attempt in (1, 2, 3):
        rc, out, err = _gh_call(args)
        if rc == 0:
            return 0, out.rstrip("\n")
        if attempt < 3:
            log.warn("%s: gh call failed (attempt %d/3), retrying..." % (what, attempt))
            _sleep(attempt * 3)
    log.error("%s: gh failed after 3 attempts (last exit %d)." % (what, rc))
    for line in err.rstrip("\n").split("\n") if err else []:
        sys.stderr.write("    %s\n" % line)
    sys.stderr.flush()
    return rc if rc != 0 else 1, ""


def _checked_sha(name: str, value: str) -> str:
    """`value` when it is a 40-hex lowercase commit SHA; otherwise a refusal (exit 1) naming `name`."""
    if not SHA40_RE.fullmatch(value):
        raise common.RefusalError("%s must be a 40-hex commit SHA, got %r" % (name, value[:80]))
    return value


def _require_pr() -> str:
    """`$PR_NUMBER`, refused (exit 1) unless it is ASCII digits."""
    pr = common.require_var("PR_NUMBER")
    if not PR_NUMBER_RE.fullmatch(pr):
        raise common.RefusalError("PR_NUMBER must be a number, got %r" % pr[:80])
    return pr


def _require_head() -> str:
    """`$HEAD_SHA`, refused (exit 1) unless it is a 40-hex commit SHA."""
    return _checked_sha("HEAD_SHA", common.require_var("HEAD_SHA"))


def _repo() -> str:
    """`$GITHUB_REPOSITORY`, read lazily so the event refusals come first."""
    return common.require_var("GITHUB_REPOSITORY")


# --------------------------------------------------------------------------- Pure helpers ---------------------------------------------------------------------------


def extract_findings_fence(text: str) -> str:
    """The body of the LAST `json:review-findings` fence in `text`, up to its FIRST closing fence; "" when there is none.

    The first closer is safe because a JSON string cannot hold a raw newline, so a fence quoted inside a finding's `body` never lands on a line of its own. Taking the last closer instead ran past the array into any later fence and dropped every inline comment.
    """
    capturing = False
    buf: list[str] = []
    found: list[str] | None = None
    for line in text.split("\n"):
        if _FENCE_OPENER.match(line):
            capturing = True
            buf = []
            continue
        if capturing:
            if _FENCE_CLOSER.match(line):
                capturing = False
                found = buf
                continue
            buf.append(line)
    return "\n".join(found) if found is not None else ""


def marker_sha_from_bodies(text: str) -> str:
    """The last `claude-reviewed: <sha40>` on any line of the marker bodies.

    Matched per line because the body is multi-line: taking the last line first once grabbed the cost line, matched nothing and disabled the dedup for every push.
    """
    found = ""
    for line in text.split("\n"):
        match = MARKER_SHA_RE.match(line)
        if match:
            found = match.group(1)
    return found


def last_line(text: str) -> str:
    return text.rsplit("\n", 1)[-1] if text else ""


def turns_for(changed_lines: int, changed_files: int = 0) -> int:
    """Turn budget for a diff: the larger of `TURNS_PER_KLOC` per started thousand lines and `TURNS_PER_FILE` per changed file, clamped to [MIN_TURNS, MAX_TURNS]."""
    kloc = (max(changed_lines, 0) + 999) // 1000
    breadth = max(changed_files, 0) * TURNS_PER_FILE
    return min(max(kloc * TURNS_PER_KLOC, breadth, MIN_TURNS), MAX_TURNS)


def render_prompt(template: pathlib.Path, fields: dict[str, str]) -> str:
    """The template with every placeholder replaced; raises `ValueError` on a missing file, an unrendered placeholder, or a body carrying the output delimiter."""
    try:
        text = template.read_text(encoding="utf-8")
    except OSError as err:
        raise ValueError("cannot read the prompt template %s: %s" % (template, err)) from err
    for placeholder in PLACEHOLDERS:
        text = text.replace(placeholder, fields[placeholder])
    left = _UNRENDERED.search(text)
    if left:
        raise ValueError("prompt template %s left %s unrendered" % (template.name, left.group(0)))
    if PROMPT_DELIMITER in text:
        raise ValueError("rendered prompt contains the output delimiter %s" % PROMPT_DELIMITER)
    return text.rstrip("\n")


def submodule_paths() -> list[str]:
    """Submodule paths from `.gitmodules` in the current directory (the PR checkout); [] when there are none."""
    try:
        proc = subprocess.run(
            ["git", "config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.path$"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    out = []
    for line in (proc.stdout or b"").decode("utf-8", "replace").split("\n"):
        fields = line.split()
        if len(fields) >= 2:
            out.append(fields[1])
    return out


def _result_record(execution_file: str) -> dict:
    """The last `type == "result"` object of the action's execution file (or the file itself when it is one object); {} when absent or unparseable."""
    if not execution_file or not os.path.isfile(execution_file):
        return {}
    try:
        with open(execution_file, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if isinstance(data, list):
        results = [item for item in data if isinstance(item, dict) and item.get("type") == "result"]
        return results[-1] if results else {}
    return data if isinstance(data, dict) else {}


def _num(value: object) -> str:
    """A number the way jq prints it: integral values without a fraction."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "0"
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))


def cost_line(record: dict) -> str:
    """Two lines of cost transparency for the marker (operator request); "" when there is no result record.

    Every model is listed, ordered by output tokens: a single name once read "(claude-haiku-4-5)" for a run invoked with a different `--model`, because the action uses a small model for its own sub-steps (issue #539).
    """
    if not record:
        return ""
    cost = record.get("total_cost_usd") or 0
    cost = math.floor(cost * 10000 + 0.5) / 10000 if isinstance(cost, (int, float)) else 0
    models = record.get("modelUsage") or {}
    if not isinstance(models, dict) or not models:
        model_text = "model n/a"
    else:
        rows = []
        for name, entry in models.items():
            per_model = entry if isinstance(entry, dict) else {}
            out = per_model.get("outputTokens") or per_model.get("output_tokens") or 0
            rows.append((name, out if isinstance(out, (int, float)) else 0))
        rows.sort(key=lambda row: -row[1])
        model_text = ", ".join(
            name + (" %sout" % _num(out) if out > 0 else "") for name, out in rows
        )
    turns = record.get("num_turns")
    duration = record.get("duration_ms") or 0
    duration = duration if isinstance(duration, (int, float)) else 0
    usage = record.get("usage") or {}
    usage = usage if isinstance(usage, dict) else {}
    return (
        "Cost: $%s (%s) | %s turns | %dm%ds\nTokens: %s in / %s out / %s cache-read / %s cache-write"
        % (
            _num(cost),
            model_text,
            _num(turns) if turns is not None else "?",
            int(duration // 60000),
            int(duration // 1000) % 60,
            _num(usage.get("input_tokens") or 0),
            _num(usage.get("output_tokens") or 0),
            _num(usage.get("cache_read_input_tokens") or 0),
            _num(usage.get("cache_creation_input_tokens") or 0),
        )
    )


# --------------------------------------------------------------------------- Reads ---------------------------------------------------------------------------


def last_marker_sha(repo: str, pr: str) -> tuple[str, bool]:
    """(last reviewed sha or "", readable). An unreadable marker is NOT "never reviewed"."""
    rc, out = gh_retry(
        "last_marker_sha",
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.body | startswith("%s")) | .body' % MARKER_PREFIX,
        ],
    )
    if rc != 0:
        return "", False
    return marker_sha_from_bodies(out), True


def last_marker_id(repo: str, pr: str) -> str:
    """Id of the newest marker comment, or "" (a failed read then POSTs a second marker, which is harmless: the last sha wins)."""
    rc, out = gh_retry(
        "last_marker_id",
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.body | startswith("%s")) | .id' % MARKER_PREFIX,
        ],
    )
    return last_line(out) if rc == 0 else ""


def review_report_count(repo: str, pr: str) -> tuple[int, int]:
    """(finished reports on the PR, exit code). Keyed on `REPORT_HEADER` and the github-actions author alone."""
    rc, out = gh_retry(
        "review_report_count",
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.user.login | contains("%s")) | select(.body | startswith("%s")) | .id'
            % (review_budget.REPORT_AUTHOR_SUBSTRING, REPORT_HEADER),
        ],
    )
    if rc != 0:
        return 0, rc
    return (len(out.split("\n")) if out else 0), 0


def review_attempt_states(repo: str, pr: str) -> tuple[list[review_budget.AttemptState], int]:
    """(the attempt ledger, exit code). Bodies are streamed with the ledger's EOF sentinel between them."""
    rc, out = gh_retry(
        "review_attempt_states",
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.body | startswith("%s")) | .body, "%s"'
            % (ATTEMPT_PREFIX, review_budget.ATTEMPT_EOF),
        ],
    )
    if rc != 0:
        return [], rc
    return review_budget.parse_attempt_states(out), 0


def pr_diff_size(repo: str, pr: str) -> tuple[int, int]:
    """(additions plus deletions, changed files), or (0, 0) -- the smallest cap tier and the smallest turn budget -- when unreadable or non-numeric."""
    rc, out = _gh(
        [
            "pr",
            "view",
            pr,
            "--repo",
            repo,
            "--json",
            "additions,deletions,changedFiles",
            "--jq",
            '"\\(.additions + .deletions) \\(.changedFiles)"',
        ],
        quiet=True,
    )
    found = re.fullmatch(r"([0-9]+) ([0-9]+)", out.strip())
    if rc != 0 or found is None:
        return review_budget.DIFF_LOC_FAILS_TO_ZERO, 0
    return int(found.group(1)), int(found.group(2))


# --------------------------------------------------------------------------- GATE MODE ---------------------------------------------------------------------------


def emit(output_path: str, go: str, pr: str, head_sha: str, last_sha: str, reason: str) -> NoReturn:
    """Write the four decision keys, log the reason, and end the arm with 0."""
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


def _write_prompt(output_path: str, turns: int, prompt: str) -> None:
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write("review_turns=%d\n" % turns)
        handle.write("prompt<<%s\n%s\n%s\n" % (PROMPT_DELIMITER, prompt, PROMPT_DELIMITER))


def _resolve_workflow_run(output_path: str) -> tuple[str, str, str]:
    """(pr, head sha, head ref) for a Console CI `workflow_run`, or a go=false decision."""
    if os.environ.get("WR_EVENT", "") != "pull_request":
        emit(output_path, "false", "", "", "", "CI run was not a PR run")
    if os.environ.get("WR_CONCLUSION", "") != "success":
        emit(output_path, "false", "", "", "", "CI run not green")
    # PINNED TO THE RUN'S SHA: `headRefOid == WR_HEAD_SHA` is the "current head is green RIGHT NOW" invariant, so a late green run for a superseded commit never reviews stale code. `workflow_run.pull_requests[]` is unreliable, so the PR is resolved through the branch.
    wr_head_sha = _checked_sha("WR_HEAD_SHA", os.environ.get("WR_HEAD_SHA", ""))
    head_ref = os.environ.get("WR_HEAD_BRANCH", "")
    rc, pr_json = _gh(
        [
            "pr",
            "list",
            "--repo",
            _repo(),
            "--head",
            head_ref,
            "--state",
            "open",
            "--json",
            "number,headRefOid,isDraft",
            "--jq",
            '[.[] | select(.headRefOid == "%s")] | first // empty' % wr_head_sha,
        ]
    )
    if rc != 0:
        raise Done(rc)
    if not pr_json:
        emit(output_path, "false", "", "", "", "no open PR currently at this head SHA")
    try:
        data = json.loads(pr_json)
    except ValueError:
        emit(output_path, "false", "", "", "", "unparseable PR lookup")
    pr = str(data.get("number", "")) if isinstance(data, dict) else ""
    if not isinstance(data, dict) or data.get("isDraft") is not False:
        emit(output_path, "false", pr, "", "", "PR is a draft")
    return pr, wr_head_sha, head_ref


def _resolve_pull_request(output_path: str) -> tuple[str, str, str]:
    """(pr, head sha, head ref) for `pull_request: ready_for_review` or `workflow_dispatch`, or a go=false decision."""
    pr = _require_pr()
    rc, view = _gh(
        [
            "pr",
            "view",
            pr,
            "--repo",
            _repo(),
            "--json",
            "headRefOid,headRefName,isDraft",
        ],
        quiet=True,
    )
    try:
        data = json.loads(view) if rc == 0 else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        emit(output_path, "false", pr, "", "", "cannot resolve PR head")
    head_sha = _checked_sha(
        "the PR head SHA", os.environ.get("PR_HEAD_SHA", "") or str(data.get("headRefOid") or "")
    )
    head_ref = str(data.get("headRefName") or "")
    if data.get("isDraft") is not False:
        emit(output_path, "false", pr, head_sha, "", "PR is a draft")
    required_check = os.environ.get("REQUIRED_CHECK", "")
    if required_check:
        rc, green = _gh(
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
        if not re.fullmatch(r"[0-9]+", green.strip()) or int(green.strip()) < 1:
            emit(
                output_path,
                "false",
                pr,
                head_sha,
                "",
                "%s is not green on the current head" % required_check,
            )
    else:
        log.info("no required check configured; green gate skipped")
    return pr, head_sha, head_ref


def run_gate() -> int:
    """The default arm: decide, then assemble the prompt."""
    output_path = common.require_var("GITHUB_OUTPUT")
    event = os.environ.get("EVENT_NAME", "")
    log.step("Deciding whether a Claude review should run (event: %s)" % (event or "unset"))

    if event == "workflow_run":
        pr, head_sha, head_ref = _resolve_workflow_run(output_path)
    elif event in ("pull_request", "workflow_dispatch"):
        pr, head_sha, head_ref = _resolve_pull_request(output_path)
    else:
        log.error("Unsupported EVENT_NAME: %s" % (event or "unset"))
        raise Done(1)

    slug = pr_labels.branch_slug(head_ref)
    if not slug:
        emit(output_path, "false", pr, head_sha, "", "cannot resolve the PR's head branch")

    repo = _repo()
    reports_posted, rc = review_report_count(repo, pr)
    if rc != 0:
        raise Done(rc)
    # Fetched ONCE: the cap needs the chargeable total and the per-head ceiling needs this head's row.
    states, rc = review_attempt_states(repo, pr)
    if rc != 0:
        raise Done(rc)
    attempts_spent = review_budget.chargeable_attempts(states)

    # The per-head ceiling is checked BEFORE the cap so the message names the real reason: free infra re-attempts are not charged, so without it one head could be retried forever.
    head_attempts, head_class = review_budget.head_attempt_state(states, head_sha)
    if review_budget.head_is_exhausted(states, head_sha):
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

    review_count = review_budget.spend_total(reports_posted, attempts_spent)
    loc, diff_files = pr_diff_size(repo, pr)
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

    last_sha, readable = last_marker_sha(repo, pr)
    if not readable:
        emit(
            output_path,
            "false",
            pr,
            head_sha,
            "",
            "the reviewed-SHA marker could not be read; not reviewing a head that may "
            "already be reviewed",
        )
    fields = {
        "{{REPO}}": repo,
        "{{PR_NUMBER}}": pr,
        "{{HEAD_SHA}}": head_sha,
        "{{LAST_REVIEWED_SHA}}": last_sha,
        "{{HEAD_REF_SLUG}}": slug,
    }
    template = PROMPTS_DIR / "initial.md"
    reason = "initial review: full PR diff"
    if last_sha:
        if last_sha == head_sha:
            emit(output_path, "false", pr, head_sha, last_sha, "head already reviewed")
        # Delta since the last ACTUALLY reviewed SHA (markers never advance on skips). A failed compare fails OPEN into an incremental review. `files[]` caps at 300 entries, which cannot mask an all-gitlink diff.
        rc, files_json = _gh(
            [
                "api",
                "repos/%s/compare/%s...%s" % (repo, last_sha, head_sha),
                "--jq",
                "[.files[]?.filename]",
            ],
            quiet=True,
        )
        try:
            files = json.loads(files_json) if rc == 0 and files_json else None
        except ValueError:
            files = None
        if isinstance(files, list):
            if not files:
                emit(
                    output_path,
                    "false",
                    pr,
                    head_sha,
                    last_sha,
                    "empty diff since last reviewed SHA",
                )
            subs = set(submodule_paths())
            if all(name in subs for name in files):
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
        template = PROMPTS_DIR / "followup.md"
        reason = "follow-up review: delta since %s" % last_sha[:7]

    try:
        prompt = render_prompt(template, fields)
    except ValueError as err:
        log.error("%s; $GITHUB_OUTPUT left without a prompt" % err)
        raise Done(1) from err
    turns = turns_for(loc, diff_files)
    log.info("diff size %d lines in %d files -> review_turns=%d" % (loc, diff_files, turns))
    _write_prompt(output_path, turns, prompt)
    emit(output_path, "true", pr, head_sha, last_sha, reason)
    return 0


# --------------------------------------------------------------------------- --post-report ---------------------------------------------------------------------------


def run_post_report() -> int:
    """Post the model's final report as a PR comment headed `REPORT_HEADER`.

    On the `workflow_run` entry point the action runs in agent mode and posts no tracking comment, so the report exists only as the final text in the execution file; posting it here gives both entry points one shape of report. No report text is a warning and exit 0: `--mark` then refuses to stamp the head, so it stays retryable.
    """
    pr = _require_pr()
    head_sha = _require_head()
    execution_file = os.environ.get("EXECUTION_FILE", "")
    result = _result_record(execution_file).get("result")
    report = result if isinstance(result, str) else ""
    if not report:
        log.warn("no final report text in %s; nothing to post" % (execution_file or "<unset>"))
        return 0
    if len(report) > REPORT_LIMIT:
        log.warn("report is %d chars; truncating the middle to fit the comment limit" % len(report))
        report = (
            report[:REPORT_HEAD]
            + "\n\n_[report truncated: middle omitted to fit GitHub's comment size limit]_\n\n"
            + report[-REPORT_TAIL:]
        )
    body = "%s the automated review of %s**\n\n---\n\n%s" % (REPORT_HEADER, head_sha[:7], report)
    rc, _ = _gh(
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
        raise Done(rc)
    log.info("Posted review report for %s (%d chars)" % (head_sha[:7], len(report)))
    return 0


# --------------------------------------------------------------------------- --post-findings ---------------------------------------------------------------------------


def sorted_findings(findings: list) -> list[dict]:
    """Object entries by severity (critical, high, medium, then anything else; missing reads medium), stable, first `INLINE_COMMENT_CAP`."""

    def rank(item: dict) -> int:
        sev = item.get("severity")
        sev = sev.lower() if isinstance(sev, str) else "medium"
        return SEVERITY_RANK.get(sev, 3)

    objects = [item for item in findings if isinstance(item, dict)]
    return sorted(objects, key=rank)[:INLINE_COMMENT_CAP]


def run_post_findings() -> int:
    """Line-anchored review comments with severity badges, from the newest report's findings fence.

    ADVISORY: a comment GitHub rejects (a line outside the diff, a stale position) is logged and skipped, and the arm always exits 0, because a failure here would skip the `--mark` that follows.
    """
    pr = _require_pr()
    head_sha = _require_head()
    repo = _repo()
    rc, bodies = _gh(
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.user.login | contains("github-actions")) | select(.body | contains("%s")) | .body'
            % FINDINGS_FENCE,
        ],
        quiet=True,
    )
    fence = extract_findings_fence(bodies) if rc == 0 else ""
    try:
        findings = json.loads(fence) if fence else None
    except ValueError:
        findings = None
    if not isinstance(findings, list):
        log.info("no parseable review-findings block; skipping inline comments")
        return 0

    posted = 0
    skipped = 0
    for finding in sorted_findings(findings):
        path = finding.get("path")
        line = finding.get("line")
        if not isinstance(path, str) or not path or line in (None, False, ""):
            skipped += 1
            continue
        sev = finding.get("severity")
        sev = sev.upper() if isinstance(sev, str) else "MEDIUM"
        title = finding.get("title") or "finding"
        body = finding.get("body") or ""
        rc, _ = _gh(
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
                "line=%s" % line,
                "-f",
                "side=RIGHT",
                "-f",
                "body=**[%s]** - %s\n\n%s" % (sev, title, body),
            ],
            quiet=True,
        )
        if rc == 0:
            posted += 1
        else:
            skipped += 1
            log.warn("inline comment rejected (line not in diff?): %s:%s" % (path, line))
    log.info(
        "inline findings: %d posted, %d skipped (cap %d)" % (posted, skipped, INLINE_COMMENT_CAP)
    )
    return 0


# --------------------------------------------------------------------------- --mark ---------------------------------------------------------------------------


def attempt_body(head_sha: str, attempts: int, why: str, pr: str) -> str:
    """The spent-attempt comment for one head."""
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
    return (
        "%s %s -->\nattempts: %d\nclass: %s\n"
        "A review pass was attempted on `%s` and produced no report (`%s`).\n%s"
        % (ATTEMPT_PREFIX, head_sha, attempts, why, head_sha[:7], why, verdict_line)
    )


def marker_body(head_sha: str, cost: str) -> str:
    """The reviewed-SHA marker for one head, with the optional cost lines."""
    return "%s %s -->\nAutomated Claude review completed for commit %s.%s" % (
        MARKER_PREFIX,
        head_sha,
        head_sha[:7],
        ("\n%s" % cost) if cost else "",
    )


def _upsert(repo: str, pr: str, comment_id: str, body: str) -> int:
    if comment_id:
        args = ["api", "-X", "PATCH", "repos/%s/issues/comments/%s" % (repo, comment_id)]
    else:
        args = ["api", "-X", "POST", "repos/%s/issues/%s/comments" % (repo, pr)]
    rc, _ = _gh([*args, "-f", "body=%s" % body], quiet=True)
    return rc


def _record_attempt(repo: str, pr: str, head_sha: str, execution_file: str) -> int:
    """Record a pass that produced no report as a SPENT ATTEMPT, one comment per head.

    A pass that burned its budget still cost money; before 2026-07-30 it cost it for free, the cap never advanced and the same head was re-reviewed at full price on every green push. The attempt prefix keeps it invisible to the marker read while the budget counts it. An unreadable ledger writes NOTHING and exits 1: recording `attempts: 1` over an unknown count would reset the per-head ceiling.
    """
    record = _result_record(execution_file)
    subtype = record.get("subtype")
    status = record.get("api_error_status")
    if record.get("is_error") and isinstance(status, (int, str)) and str(status).isdigit():
        # An API failure is recorded by its HTTP status, `api_error_<status>`: review_status.OUTAGE_CLASSES excuses exactly the outage statuses (operator ruling 2026-10-03: an LLM outage is the one review failure that does not block the merge). The SDK's subtypes never say the service was down.
        why = "api_error_%s" % status
    else:
        why = subtype if isinstance(subtype, str) and subtype else "review step did not succeed"
    rc, attempt_ids = gh_retry(
        "attempt_comment_id",
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.body | startswith("%s")) | select(.body | contains("%s")) | .id'
            % (ATTEMPT_PREFIX, head_sha),
        ],
    )
    states, rc_states = review_attempt_states(repo, pr)
    if rc != 0 or rc_states != 0:
        log.error(
            "the attempt ledger for %s could not be read; not recording an attempt over an "
            "unknown count" % head_sha[:7]
        )
        return 1
    prior, _cls = review_budget.head_attempt_state(states, head_sha)
    attempts = prior + 1
    if _upsert(repo, pr, last_line(attempt_ids), attempt_body(head_sha, attempts, why, pr)) != 0:
        log.warn("could not record the spent attempt for %s" % head_sha[:7])
    log.info(
        "recorded SPENT ATTEMPT %d/%d for %s (%s); it does not mark the SHA reviewed"
        % (attempts, review_budget.REVIEW_MAX_ATTEMPTS_PER_HEAD, head_sha[:7], why)
    )
    return 0


def run_mark() -> int:
    """Upsert the reviewed-SHA marker when `REVIEW_OUTCOME` is `success`, else record a spent attempt.

    A marker is a CLAIM that a review happened, and step success alone once proved false: the reviewer "succeeded" with 36 permission denials and posted nothing, and the marker then suppressed the retry. So the marker needs github-actions output from the last hour: a non-bookkeeping issue comment (any body starting `<!--` is bookkeeping, this module's and `pr_labels`'s alike) or an inline comment.
    """
    pr = _require_pr()
    head_sha = _require_head()
    execution_file = os.environ.get("EXECUTION_FILE", "")
    repo = _repo()

    if os.environ.get("REVIEW_OUTCOME", "") != "success":
        return _record_attempt(repo, pr, head_sha, execution_file)

    recent = 0
    for endpoint, extra in (
        ("issues", '.[] | select(.body | startswith("<!--") | not) | '),
        ("pulls", ".[] | "),
    ):
        rc, ids = _gh(
            [
                "api",
                "repos/%s/%s/%s/comments" % (repo, endpoint, pr),
                "--paginate",
                "--jq",
                extra + 'select(.user.login | contains("github-actions")) | '
                "select(.created_at > (now - 3600 | todate)) | .id",
            ],
            quiet=True,
        )
        if rc == 0 and ids:
            recent += len(ids.split("\n"))
    if recent == 0:
        log.error(
            "review step reported success but posted NOTHING in the last hour (or the "
            "comments could not be read); refusing to mark %s, so it stays retryable" % head_sha[:7]
        )
        raise Done(1)

    body = marker_body(head_sha, cost_line(_result_record(execution_file)))
    comment_id = last_marker_id(repo, pr)
    rc = _upsert(repo, pr, comment_id, body)
    if rc != 0:
        raise Done(rc)
    if comment_id:
        log.info("Updated marker comment %s -> %s" % (comment_id, head_sha[:7]))
    else:
        log.info("Created marker comment for %s" % head_sha[:7])
    return 0


# --------------------------------------------------------------------------- Entry point ---------------------------------------------------------------------------

MODES = {
    "--post-report": run_post_report,
    "--post-findings": run_post_findings,
    "--mark": run_mark,
}


def main(argv: list[str]) -> int:
    """No argument runs the gate; one of `ARMS` runs that arm; anything else is a usage error (exit 2)."""
    if argv and argv[0] not in MODES:
        log.error("unknown arm %r; expected none or one of %s" % (argv[0], ", ".join(ARMS)))
        return 2
    try:
        common.require_cmd("gh")
        mode = MODES.get(argv[0]) if argv else None
        return mode() if mode is not None else run_gate()
    except common.RefusalError as refusal:
        refusal.report()
        return refusal.code
    except Done as done:
        return done.code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
