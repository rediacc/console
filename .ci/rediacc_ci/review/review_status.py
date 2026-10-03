#!/usr/bin/env python3
"""The "Review Complete" check-run reporter: a required verdict on whether the PR's current head carries a whole-PR Claude review.

NOT A CI JOB. The review only starts once Console CI is green, so a CI job that waited on it would deadlock the pipeline that produces it. The verdict is posted as an independent check-run from a workflow no CI job references; never add a `needs:` or a `wait-for` on `Review Complete` inside Console CI.

REQUIRED AGAIN, operator ruling 2026-10-03: "Required check again, but the AI system should investigate and fix automatically if there is an error; the only exception is LLM outage." So an unreviewed head, a review run that failed for its own reasons, and unanswered findings all conclude `failure`, and the summary names what the loop must act on. The single excused failure is an LLM outage (`OUTAGE_CLASSES`). This supersedes the advisory mapping of agent/plans/PLAN-github-pr-review-restore.md, Design 6.

TWO ASSERTIONS:

    CURRENCY  the reviewed-SHA marker comment names the PR's CURRENT head, or the
              diff marker...head is empty or touches submodule gitlinks only.
    HYGIENE   `check_resolved_threads.py` and `check_review_comments.py` both pass.

THE TITLE TOKEN IS A FROZEN FORMAT. Every title is `<token>: <text>`, where the token is exactly one of `TITLE_TOKENS` and the text is for humans. `wl_prreview.py --wait` reads the token with `title.split(":", 1)[0]`. The tokens and their conclusions:

    draft       neutral   the PR is a draft; nothing ran and nothing is mergeable yet
    failed-run  failure   the head is unreviewed and the triggering Claude Review run failed for a non-outage reason
    stale       failure   the head is unreviewed and no excuse applies
    hygiene     failure   currency is satisfied (current, capped, exhausted or outage), a hygiene script failed
    capped      success   the PR spent its review cap, the marker is stale, hygiene is clean
    exhausted   success   the head spent its attempt ceiling, the marker is stale, hygiene is clean
    outage      success   the head's last attempt died of an LLM outage, the marker is stale, hygiene is clean
    current     success   the current head is reviewed and hygiene is clean

THE DECISION, in order: a draft is `draft`. Otherwise currency is satisfied when the head is reviewed, or when one of three excuses applies to a stale marker, checked in this order: the PR cap is reached (`capped`), the head's infra-class attempts hit their ceiling (`exhausted`), the head's last recorded attempt class is in `OUTAGE_CLASSES` (`outage`). With currency unsatisfied the token is `failed-run` when the triggering run concluded `failure` or `timed_out`, else `stale`. With currency satisfied a failing hygiene script gives `hygiene`, else the excuse's token or `current`.

A REVIEWED HEAD READS `current`, `capped`, `exhausted`, `outage` OR `hygiene`. `hygiene` is the usual state right after a review lands, because an unanswered summary or an open finding thread is exactly what the hygiene scripts flag; answering it is the loop's next step.

THE BUDGET ARMS ARE POLICY, NOT ERRORS. Once a PR reaches its review cap the gate refuses to review again, so the marker stops advancing; on PR #553 (2026-08-07) that left a green, ready, thread-clean PR unmergeable. The same happens one level down when a head exhausts its own attempt ceiling while the PR is under its cap. Both arms report `success` with a warning, and both read the budget from `core.review_budget`, the one table the gate also caps on.

THE OUTAGE EXCUSE IS NARROW ON PURPOSE. `claude_review_gate --mark` records a reportless pass as an attempt comment whose `class:` line is the class of its death. A class matches only by exact string against `OUTAGE_CLASSES`, which names the API answers that mean the model service itself was unavailable: an exhausted rate limit (429) and the server-side 5xx family including the overloaded 529. A 401 or 403 is absent: an expired or wrong credential is a fixable configuration error. The agent SDK's own result subtypes (`error_max_turns`, `error_during_execution`, `error_max_budget_usd`, `error_max_structured_output_retries`) are absent too, because none of them says the service was down.

THE CONSTANTS ARE IMPORTED. `MARKER_PREFIX` and `ATTEMPT_PREFIX` come from `rediacc_ci.review.claude_review_gate`, the module that writes those comments, so the two cannot disagree about either prefix.

THE EXIT CODE IS NOT THE VERDICT. A healthy run exits 0 whatever it posted, `failure` included. A non-zero exit means the reporter itself broke: a missing variable, an unreadable review budget, a missing hygiene script (which would otherwise shrink the check to currency alone), a review-target artifact present but unreadable, or a failed check-run write.

INPUTS, all from the workflow environment: `GITHUB_REPOSITORY`, `EVENT_NAME`, `PR_NUMBER` (every event but `workflow_run`), `WR_RUN_ID`, `WR_CONCLUSION` and `WR_HTML_URL` (the `workflow_run` event), and `CHECK_NAME` (defaults to `Review Complete`).

    PYTHONPATH=.ci python3 -m rediacc_ci.review.review_status
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import re
import subprocess
import sys
import zipfile

from rediacc_ci import log
from rediacc_ci.core import common, ghx, review_budget
from rediacc_ci.review.claude_review_gate import (
    ATTEMPT_PREFIX,
    MARKER_PREFIX,
    PR_NUMBER_RE,
    SHA40_RE,
)

DEFAULT_CHECK_NAME = "Review Complete"

# `.ci/scripts/quality/`, the directory of executable gate entry points; this file lives in `.ci/rediacc_ci/review/`.
DEFAULT_HYGIENE_DIR = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "quality"

HYGIENE_SCRIPTS = (
    "check_resolved_threads.py",
    "check_review_comments.py",
)

VERDICT_DRAFT = "draft"
VERDICT_FAILED_RUN = "failed-run"
VERDICT_STALE = "stale"
VERDICT_HYGIENE = "hygiene"
VERDICT_CAPPED = "capped"
VERDICT_EXHAUSTED = "exhausted"
VERDICT_OUTAGE = "outage"
VERDICT_CURRENT = "current"

# Every title token; `wl_prreview` reads these by value.
TITLE_TOKENS = (
    VERDICT_DRAFT,
    VERDICT_FAILED_RUN,
    VERDICT_STALE,
    VERDICT_HYGIENE,
    VERDICT_CAPPED,
    VERDICT_EXHAUSTED,
    VERDICT_OUTAGE,
    VERDICT_CURRENT,
)

CONCLUSION_SUCCESS = "success"
CONCLUSION_NEUTRAL = "neutral"
CONCLUSION_FAILURE = "failure"
ALLOWED_CONCLUSIONS = (CONCLUSION_SUCCESS, CONCLUSION_NEUTRAL, CONCLUSION_FAILURE)

TOKEN_CONCLUSION = {
    VERDICT_DRAFT: CONCLUSION_NEUTRAL,
    VERDICT_FAILED_RUN: CONCLUSION_FAILURE,
    VERDICT_STALE: CONCLUSION_FAILURE,
    VERDICT_HYGIENE: CONCLUSION_FAILURE,
    VERDICT_CAPPED: CONCLUSION_SUCCESS,
    VERDICT_EXHAUSTED: CONCLUSION_SUCCESS,
    VERDICT_OUTAGE: CONCLUSION_SUCCESS,
    VERDICT_CURRENT: CONCLUSION_SUCCESS,
}

TOKEN_TEXT = {
    VERDICT_DRAFT: "draft PR, review not expected",
    VERDICT_FAILED_RUN: "the Claude Review run failed; investigate and fix",
    VERDICT_STALE: "the current head has not been reviewed",
    VERDICT_HYGIENE: "reviewed, findings or threads still unanswered",
    VERDICT_CAPPED: "review cap reached, passing with a warning",
    VERDICT_EXHAUSTED: "head review attempts exhausted, passing with a warning",
    VERDICT_OUTAGE: "LLM outage, passing with a warning",
    VERDICT_CURRENT: "reviewed at the current head",
}

# Attempt-ledger classes that mean the model service was unavailable, matched by exact string. `api_error_<status>` is the class for a result record whose `is_error` is true and whose `api_error_status` is <status>; see the module docstring for what is excluded and why.
OUTAGE_CLASSES = (
    "api_error_429",
    "api_error_500",
    "api_error_502",
    "api_error_503",
    "api_error_504",
    "api_error_529",
)

# `workflow_run` resolves the PR from an artifact; the other four events are handed a number.
EVENT_WORKFLOW_RUN = "workflow_run"
EVENTS_WITH_PR_NUMBER = (
    "pull_request_review",
    "pull_request_review_comment",
    "issue_comment",
    "workflow_dispatch",
)

# `WR_CONCLUSION` values that mean no verdict was produced. `cancelled` is absent on purpose: Claude Review runs with cancel-in-progress, so a superseded push cancels the older run while a newer one is on its way.
FAILED_CONCLUSIONS = ("failure", "timed_out")

ARTIFACT_NAME = "review-target"
ARTIFACT_MEMBER = "review-target.txt"

# Lowercase hex, exactly 40; the LAST match across every line of every marker body wins.
MARKER_SHA_RE = re.compile(r"claude-reviewed: ([0-9a-f]{40})")

GITMODULES_PATH_RE = r"^submodule\..*\.path$"

FOOTER = (
    "\n\n_Posted by `rediacc_ci.review.review_status` from a workflow no CI job references, "
    "so it never blocks Console CI itself; a `failure` here is for the loop to investigate "
    "and fix._"
)


class ReporterError(Exception):
    """The reporter itself broke: the message is already logged, `code` is the exit status."""

    def __init__(self, code: int = 1) -> None:
        super().__init__("reporter failed with %d" % code)
        self.code = code


def title_for(token: str) -> str:
    """`<token>: <text>`, the frozen title format."""
    return "%s: %s" % (token, TOKEN_TEXT[token])


def _gh(args: list[str], *, quiet: bool = False) -> tuple[int, bytes]:
    """One `gh` call, stdout captured; stderr is discarded when `quiet`, inherited otherwise."""
    try:
        proc = subprocess.run(
            ["gh", *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if quiet else None,
            check=False,
        )
    except OSError:
        return 127, b""
    return proc.returncode, proc.stdout or b""


def _gh_input(args: list[str], payload: bytes) -> int:
    """`gh ... --input -` with the payload on stdin; stdout discarded, stderr inherited."""
    try:
        proc = subprocess.run(
            ["gh", *args],
            input=payload,
            stdout=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return 127
    return proc.returncode


def last_marker_sha(repo: str, pr: str, prefix: str) -> str:
    """The newest reviewed-SHA marker on the PR, or "".

    A failed read answers "", which reads as unreviewed: here that can only make the verdict stricter, never assert a review that did not happen.
    """
    code, body = _gh(["api", "repos/%s/issues/%s/comments" % (repo, pr), "--paginate"], quiet=True)
    if code != 0:
        return ""
    try:
        comments = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return ""
    if not isinstance(comments, list):
        return ""
    found = ""
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        text = comment.get("body") or ""
        if not text.startswith(prefix):
            continue
        for match in MARKER_SHA_RE.finditer(text):
            found = match.group(1)
    return found


def submodule_paths(cwd: str | None = None) -> list[str]:
    """Submodule paths from `.gitmodules` in `cwd`; no file means none."""
    try:
        proc = subprocess.run(
            ["git", "config", "-f", ".gitmodules", "--get-regexp", GITMODULES_PATH_RE],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            cwd=cwd,
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


def non_gitlink_count(files: list[str], subs: list[str]) -> int:
    """How many changed files are not a submodule path."""
    wanted = set(subs)
    return sum(1 for name in files if name not in wanted)


def check_payload(
    check_name: str, head_sha: str, conclusion: str, title: str, summary: str
) -> dict[str, object]:
    """The check-run body. Refuses any conclusion outside `ALLOWED_CONCLUSIONS`."""
    if conclusion not in ALLOWED_CONCLUSIONS:
        log.error("refusing to post unknown conclusion %r" % conclusion)
        raise ReporterError(1)
    return {
        "name": check_name,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": conclusion,
        "output": {"title": title, "summary": summary},
    }


def post_check(
    repo: str, check_name: str, head_sha: str, conclusion: str, title: str, summary: str
) -> None:
    """Upsert the named check-run on the PR's current head.

    Upsert rather than always-POST because the comment events fire on every comment, and a fresh check-run each time buries the PR's checks list. `head_sha` is not a PATCH field, so the update drops it.
    """
    payload = check_payload(check_name, head_sha, conclusion, title, summary)

    # A failed lookup POSTs a new run: a duplicate check-run, never a lost verdict.
    code, found = _gh(
        [
            "api",
            "-X",
            "GET",
            "repos/%s/commits/%s/check-runs" % (repo, head_sha),
            "-f",
            "check_name=%s" % check_name,
            "--jq",
            '[.check_runs[]? | select(.app.slug == "github-actions")] | last | .id // empty',
        ]
    )
    existing = "" if code != 0 else found.decode("utf-8", "replace").strip()

    if existing:
        patch = {key: value for key, value in payload.items() if key != "head_sha"}
        code = _gh_input(
            ["api", "-X", "PATCH", "repos/%s/check-runs/%s" % (repo, existing), "--input", "-"],
            json.dumps(patch).encode("utf-8"),
        )
        if code != 0:
            raise ReporterError(code)
        log.info("updated check-run %s: %s = %s" % (existing, check_name, conclusion))
        return

    code = _gh_input(
        ["api", "-X", "POST", "repos/%s/check-runs" % repo, "--input", "-"],
        json.dumps(payload).encode("utf-8"),
    )
    if code != 0:
        raise ReporterError(code)
    log.info("created check-run: %s = %s on %s" % (check_name, conclusion, head_sha))


def artifact_pr(repo: str, run_id: str) -> str:
    """The `review-target` artifact's PR number, or "" when the run wrote none.

    ABSENT IS SILENT, PRESENT IS BINDING. A push to main runs this chain with no PR and writes no artifact, which is a clean exit. An artifact that exists but cannot be honoured is a reporter failure and is loud.
    """
    if not PR_NUMBER_RE.fullmatch(run_id):
        log.error("WR_RUN_ID must be a number, got %r" % run_id[:80])
        raise ReporterError(1)
    runs_path = "repos/%s/actions/runs/%s/artifacts" % (repo, run_id)
    code, listing = _gh(
        ["api", runs_path, "--jq", '.artifacts[] | select(.name == "%s") | .id' % ARTIFACT_NAME],
        quiet=True,
    )
    if code != 0 or not listing.strip():
        return ""
    art_id = listing.decode("utf-8", "replace").split()[0]
    if not PR_NUMBER_RE.fullmatch(art_id):
        log.error(
            "run %s listed a review-target artifact id that is not a number: %r"
            % (run_id, art_id[:80])
        )
        raise ReporterError(1)

    code, blob = _gh(["api", "repos/%s/actions/artifacts/%s/zip" % (repo, art_id)], quiet=True)
    if code != 0:
        log.error(
            "review-target artifact %s exists on run %s but could not be downloaded"
            % (art_id, run_id)
        )
        raise ReporterError(1)
    digits = _read_member_digits(blob)
    if not digits:
        log.error("review-target artifact on run %s is present but carries no PR number" % run_id)
        raise ReporterError(1)
    return digits


def _read_member_digits(blob: bytes) -> str:
    """The ASCII digits of the artifact's text member; a corrupt zip or a missing member is ""."""
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            raw = archive.read(ARTIFACT_MEMBER).decode("utf-8", "replace")
    except (zipfile.BadZipFile, KeyError, OSError):
        raw = ""
    return "".join(ch for ch in raw if ch.isascii() and ch.isdigit())


def _resolve_pr(repo: str, event: str) -> str:
    """The PR number for this event, or "" when a `workflow_run` had no PR."""
    if event == EVENT_WORKFLOW_RUN:
        return artifact_pr(repo, common.require_var("WR_RUN_ID"))
    if event in EVENTS_WITH_PR_NUMBER:
        pr = common.require_var("PR_NUMBER")
        if not PR_NUMBER_RE.fullmatch(pr):
            log.error("PR_NUMBER must be a number, got %r" % pr)
            raise ReporterError(1)
        return pr
    log.error("Unsupported EVENT_NAME: %s" % (event or "unset"))
    raise ReporterError(1)


def _currency(repo: str, head_sha: str, last_sha: str) -> tuple[bool, str]:
    """ASSERTION 1. Returns (ok, detail); a failed compare fails closed."""
    if last_sha and last_sha == head_sha:
        return True, "head `%s` is the reviewed SHA" % head_sha
    if not last_sha:
        return False, (
            "no reviewed-SHA marker comment on this PR, so head `%s` has not been reviewed"
            % head_sha
        )

    code, body = _gh(
        [
            "api",
            "repos/%s/compare/%s...%s" % (repo, last_sha, head_sha),
            "--jq",
            "[.files[]?.filename]",
        ],
        quiet=True,
    )
    files: object = None
    if code == 0:
        try:
            files = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            files = None
    if not isinstance(files, list):
        log.warn(
            "compare %s...%s failed; treating head as unreviewed" % (last_sha[:7], head_sha[:7])
        )
        return False, (
            "could not compare `%s` with `%s` (compare API failed), so equivalence is unproven"
            % (last_sha, head_sha)
        )
    if not files:
        return True, "empty diff between reviewed `%s` and head `%s`" % (last_sha, head_sha)

    names = [name for name in files if isinstance(name, str)]
    count = non_gitlink_count(names, submodule_paths())
    if count == 0:
        return True, (
            "only submodule pointer bumps between reviewed `%s` and head `%s`"
            % (last_sha, head_sha)
        )
    return False, "%d non-submodule file(s) changed since the reviewed SHA" % count


def _hygiene(hygiene_dir: pathlib.Path, pr: str, repo: str) -> list[str]:
    """ASSERTION 2. Returns one failure text per failing script.

    A missing or non-executable script is a reporter failure, not a skipped check. Each script's combined output is echoed to stdout either way, and the last 20 lines of a failing one go into its failure text.
    """
    failures: list[str] = []
    for script in HYGIENE_SCRIPTS:
        path = hygiene_dir / script
        if not (path.is_file() and os.access(path, os.X_OK)):
            log.error("hygiene script missing or not executable: %s" % path)
            raise ReporterError(1)
        env = dict(os.environ)
        env["PR_NUMBER"] = pr
        env["GITHUB_REPOSITORY"] = repo
        try:
            proc = subprocess.run(
                [str(path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                check=False,
            )
            code, out = proc.returncode, proc.stdout or b""
        except OSError:
            code, out = 126, b""
        if code == 0:
            log.info("hygiene ok: %s" % script)
        else:
            lines = out.decode("utf-8", "replace").rstrip("\n").split("\n")
            tail = "\n".join(lines[-20:])
            failures.append("`%s` failed (exit %d):\n\n```\n%s\n```" % (script, code, tail))
            log.error("hygiene failed: %s" % script)
        sys.stdout.flush()
        sys.stdout.buffer.write(out)
        sys.stdout.buffer.flush()
    return failures


def build_summary(
    pr: str,
    head_sha: str,
    last_sha: str,
    failures: list[str],
    warnings: list[str],
    notes: list[str],
) -> str:
    """The check-run body: a header line, then Findings, Warnings and Context sections."""
    summary = "PR #%s -- head `%s`, last reviewed `%s`." % (pr, head_sha, last_sha or "<none>")
    for heading, items in (("Findings", failures), ("Warnings", warnings), ("Context", notes)):
        if not items:
            continue
        summary += "\n\n## %s\n" % heading
        for item in items:
            summary += "\n- %s" % item
    return summary + FOOTER


def select_token(*, failed_run: bool, currency_ok: bool, excuse: str, hygiene_failed: bool) -> str:
    """The title token for a non-draft PR, by the decision in the module docstring.

    `excuse` is "" or one of `capped`, `exhausted`, `outage`, and only counts when currency is not already satisfied.
    """
    if not currency_ok and not excuse:
        return VERDICT_FAILED_RUN if failed_run else VERDICT_STALE
    if hygiene_failed:
        return VERDICT_HYGIENE
    if not currency_ok:
        return excuse
    return VERDICT_CURRENT


def is_outage_class(cls: str) -> bool:
    """Whether an attempt-ledger class is an LLM outage: an exact member of `OUTAGE_CLASSES`."""
    return cls in OUTAGE_CLASSES


def _read_pr(repo: str, pr: str) -> tuple[str, bool, str]:
    """(state, draft, head sha) of the PR; a failed read is a reporter failure."""
    code, body = _gh(
        [
            "api",
            "repos/%s/pulls/%s" % (repo, pr),
            "--jq",
            "{state: .state, draft: .draft, head: .head.sha}",
        ]
    )
    if code != 0:
        raise ReporterError(code)
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        data = None
    if not isinstance(data, dict):
        log.error("PR #%s: unreadable pull request answer" % pr)
        raise ReporterError(1)
    return str(data.get("state") or ""), data.get("draft") is True, str(data.get("head") or "")


def run(hygiene_dir: pathlib.Path | None = None) -> int:
    """One evaluation and at most one check-run write. `hygiene_dir` exists for tests."""
    common.require_cmd("gh")
    repo = common.require_var("GITHUB_REPOSITORY")
    check_name = os.environ.get("CHECK_NAME") or DEFAULT_CHECK_NAME
    scripts_dir = DEFAULT_HYGIENE_DIR if hygiene_dir is None else hygiene_dir

    event = os.environ.get("EVENT_NAME", "")
    log.step("Review Complete: resolving the PR (event: %s)" % (event or "unset"))
    pr = _resolve_pr(repo, event)
    if not pr:
        # Greppable on purpose: this line for a run that DID have a PR means the artifact handoff broke.
        log.info(
            "no review-target artifact on run %s; no PR to report on"
            % (os.environ.get("WR_RUN_ID") or "?")
        )
        return 0

    pr_state, pr_draft, head_sha = _read_pr(repo, pr)
    if pr_state != "open":
        log.info("PR #%s is %s, not open; nothing to report" % (pr, pr_state or "unknown"))
        return 0
    if not head_sha:
        log.error("PR #%s returned no head SHA; refusing to post a check-run with no anchor" % pr)
        raise ReporterError(1)
    if not SHA40_RE.fullmatch(head_sha):
        log.error(
            "PR #%s head %r is not a 40-hex commit SHA; refusing to use it" % (pr, head_sha[:80])
        )
        raise ReporterError(1)
    log.info("PR #%s head %s" % (pr, head_sha))

    if pr_draft:
        post_check(
            repo,
            check_name,
            head_sha,
            TOKEN_CONCLUSION[VERDICT_DRAFT],
            title_for(VERDICT_DRAFT),
            "PR #%s is a draft. The review pipeline fires only for a non-draft PR whose current "
            "head has green CI, so there is nothing to assert about commit `%s` yet. This check "
            "re-evaluates once the PR is ready for review.%s" % (pr, head_sha, FOOTER),
        )
        return 0

    failures: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    failed_run = False
    wr_conclusion = ""
    if event == EVENT_WORKFLOW_RUN:
        wr_conclusion = os.environ.get("WR_CONCLUSION", "")
        failed_run = wr_conclusion in FAILED_CONCLUSIONS
        notes.append("Triggering Claude Review run: `%s`." % (wr_conclusion or "n/a"))

    log.step("CURRENCY: is the reviewed-SHA marker on the current head?")
    last_sha = last_marker_sha(repo, pr, MARKER_PREFIX)
    currency_ok, currency_detail = _currency(repo, head_sha, last_sha)

    try:
        # Posted reports PLUS spent attempts: the same numerator the gate caps on.
        review_count = review_budget.spend_total(
            review_budget.report_count(pr, repo=repo),
            review_budget.spent_attempt_count(pr, ATTEMPT_PREFIX, repo=repo),
        )
        states = review_budget.attempt_states(pr, ATTEMPT_PREFIX, repo=repo)
    except (ghx.GhError, ValueError) as exc:
        log.error("review budget could not be read for PR #%s: %s" % (pr, exc))
        raise ReporterError(1) from None

    pr_loc = review_budget.diff_loc(pr, repo=repo, on_error=review_budget.DIFF_LOC_FAILS_TO_ZERO)
    max_reviews = review_budget.cap_for(pr_loc)
    head_attempts, head_class = review_budget.head_attempt_state(states, head_sha)
    notes.append("Currency: %s." % currency_detail)
    notes.append(
        "Review passes spent: %d/%d (posted reports + spent attempts; cap %d for a %d-line diff)."
        % (review_count, max_reviews, max_reviews, pr_loc)
    )
    if head_attempts:
        notes.append(
            "Reportless attempts on this head: %d, last class `%s`."
            % (head_attempts, head_class or "<none>")
        )

    excuse = ""
    if currency_ok:
        log.info("CURRENCY ok: %s" % currency_detail)
    elif review_count >= max_reviews:
        excuse = VERDICT_CAPPED
        warnings.append(
            "**REVIEW CAP REACHED** (%d/%d) and the marker is stale: %s. The review pipeline will "
            "not run again on this PR, so the marker can never reach `%s`. Passing so the PR stays "
            "mergeable; the delta needs a manual review."
            % (review_count, max_reviews, currency_detail, head_sha)
        )
        log.warn(
            "CURRENCY stale but review cap reached (%d/%d); passing with a warning"
            % (review_count, max_reviews)
        )
    elif review_budget.head_is_exhausted(states, head_sha):
        excuse = VERDICT_EXHAUSTED
        warnings.append(
            "**HEAD REVIEW ATTEMPTS EXHAUSTED** for `%s` (%d reportless attempts, %d/%d of the PR "
            "budget spent): %s. The review pipeline will not retry this head, so the marker can "
            "never reach it. Passing so the PR stays mergeable; a new push earns another pass."
            % (
                head_sha,
                review_budget.REVIEW_MAX_ATTEMPTS_PER_HEAD,
                review_count,
                max_reviews,
                currency_detail,
            )
        )
        log.warn(
            "CURRENCY stale but head %s exhausted its %d attempts; passing with a warning"
            % (head_sha, review_budget.REVIEW_MAX_ATTEMPTS_PER_HEAD)
        )
    elif is_outage_class(head_class):
        excuse = VERDICT_OUTAGE
        warnings.append(
            "**LLM OUTAGE**: the last review attempt on `%s` died with class `%s`, an unavailable "
            "model service rather than an error in this PR or its pipeline (operator ruling "
            "2026-10-03). Passing so the PR stays mergeable; a re-run on the same head, or the "
            "next push, earns the review." % (head_sha, head_class)
        )
        log.warn("CURRENCY stale but head %s died of an LLM outage (%s)" % (head_sha, head_class))
    elif failed_run:
        reason = "the Claude Review run concluded `%s`" % wr_conclusion
        if head_class:
            reason += " (last attempt class `%s`)" % head_class
        failures.append(
            "investigate and fix: %s, so head `%s` has no review verdict. Run: %s"
            % (reason, head_sha, os.environ.get("WR_HTML_URL") or "<run url unavailable>")
        )
        log.error("review run failed for a non-outage reason: %s" % reason)
    else:
        failures.append(
            "Head `%s` has not been reviewed. Last reviewed SHA: `%s`. Detail: %s."
            % (head_sha, last_sha or "<none>", currency_detail)
        )
        log.error("CURRENCY stale: %s" % currency_detail)

    log.step("HYGIENE: running the review-hygiene checks")
    hygiene_failures = _hygiene(scripts_dir, pr, repo)
    failures.extend(hygiene_failures)

    token = select_token(
        failed_run=failed_run,
        currency_ok=currency_ok,
        excuse=excuse,
        hygiene_failed=bool(hygiene_failures),
    )
    post_check(
        repo,
        check_name,
        head_sha,
        TOKEN_CONCLUSION[token],
        title_for(token),
        build_summary(pr, head_sha, last_sha, failures, warnings, notes),
    )
    return 0


def main() -> int:
    """No arguments. Exit 0 after any verdict; non-zero only when the reporter broke."""
    try:
        return run()
    except common.RefusalError as refusal:
        refusal.report()
        return refusal.code
    except ReporterError as broken:
        return broken.code


if __name__ == "__main__":
    raise SystemExit(main())
