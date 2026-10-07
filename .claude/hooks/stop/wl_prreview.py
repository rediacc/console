#!/usr/bin/env python3
"""wl_prreview: answer the PR-level Claude review on GitHub from the session (agent/plans/PLAN-github-pr-review-restore.md, box GR7).

WHY. The restored whole-PR review posts one summary comment on the PR, headed `**Claude finished the automated review of <sha7>**` and carrying a `json:review-findings` fence, and mirrors up to 20 findings as inline comments. The Review Gate (`rediacc_ci.quality.review_comments`) then wants a later, substantive reply to that summary from another author before the next push goes green, and the watchdog
cancels a run on a Review Gate failure. Answering by hand is slow and easy to get wrong, so this tool drafts the dispositions, checks each one in the per-commit review grammar, and posts the answer in the one shape the gate accepts.

THE MODES.

  --status [--pr N]          the newest summary, its head, its findings, the inline finding threads and whether each is answered
  --wait [--timeout S]       wait until Review Complete on the PR head carries a terminal title token; exit 0 reviewed, 4 failed-run, 3 timeout;
                             on failed-run, exhausted, outage or a timeout it also names the head's review-attempt comment, its class and its action (wl_prsignals)
  --draft                    print a dispositions file, one line per finding
  --answer <file>            validate the dispositions, then post one top-level reply, an in-thread reply per inline finding, and resolve each thread
  --check                    0 no summary / answered / empty findings with every finding thread resolved, 1 unanswered or a thread unresolved, 2 the API cannot be read

REVIEW COMPLETE IS A REQUIRED CHECK (operator ruling 2026-10-03). A timeout is not a pass: the loop does not merge on rc 3, it reports and checks again. A `failed-run` is a review-run error to investigate and fix, not an excuse; only `outage` (the LLM was unavailable) passes with a warning.

THE SELECTOR IS review_comments' OWN. `FENCE_NEEDLE`, `VERDICT_HEADING`, the low-effort list and the summary floors are imported from `.ci/rediacc_ci/quality/review_comments.py` through `rediacc_hooks/syspath.py` (`import_from_ci`, `.ci` on sys.path only while importing), so a summary this tool calls answered while the gate calls it unanswered cannot come from a drifted copy. `.claude/rediacc_hooks/tests/test_wl_prreview.py` still pins the names equal and the verdict agreeing. The import runs when this module loads, so a tree without `.ci` fails loudly here rather than judging with stale values.

THE DISPOSITION GRAMMAR IS THE PER-COMMIT ONE (`.claude/hooks/stop/wl_review.py`, `mark`): `fixed <sha40>` an ancestor of local HEAD, `not-a-bug | <evidence>` with at least 20 characters that pass `wl_review._citation_ok`, `deferred #<item>` an open, `[?]` or `[>]` worklist item. Every line is checked before anything is posted, so a refused file posts nothing.

SEALED. No environment variable is read. `gh` is the only external tool, reached through `wl_gh` (the Stop hook's one gh layer) with one injectable runner (`run_gh`, a `wl_gh.runner`), and the reply posts under the session's own gh identity, which is a different author from github-actions[bot]. Ancestry and citations are checked with wl_review's git helpers against the local checkout.

EVERY READ RETRIES A TRANSIENT FAULT, NO WRITE DOES (agent/plans/PLAN-gh-retry.md G13, PLAN-ci-consolidation.md T12). Reads go through `wl_gh.call` and `wl_gh.call_list` with the runner as their `run=` seam, so the retry (wl_gh.GH_READ_ATTEMPTS, wl_gh.GH_READ_PAUSE_S, bounded for the Stop hook's budget in wl_checks.prreview_runner) and the JSON arms live in one place; `_read` is the ONE conversion of their `(None, why)` into UnreadableError, which this module's callers expect. The comment POSTs and the resolveReviewThread mutation go through `wl_gh.write`, once: a retried POST after a lost response is a second comment.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import sys
import time
from collections.abc import Callable
from typing import Any

import wl_gh
import wl_review

HERE = pathlib.Path(__file__).resolve().parent
CONSOLE_ROOT = HERE.parents[2]


def _syspath() -> Any:
    """The canonical `.claude` hop, rediacc_hooks/syspath.py, loaded BY FILE: this module lives outside the `rediacc_hooks` package (the wl_ci shape)."""
    hop = HERE.parents[1] / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("_rediacc_syspath", hop)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % hop)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- the review gate's selector, imported from rediacc_ci.quality.review_comments (the one definition, no copy) ----
_RC = _syspath().import_from_ci("rediacc_ci.quality.review_comments")
LOW_EFFORT_PATTERNS = _RC.LOW_EFFORT_PATTERNS
INLINE_MIN_CHARS = _RC.INLINE_MIN_CHARS
SUMMARY_MIN_CHARS = _RC.SUMMARY_MIN_CHARS
SUMMARY_LONGFORM_CHARS = _RC.SUMMARY_LONGFORM_CHARS
TRAILING_PUNCT = _RC.TRAILING_PUNCT
FENCE_NEEDLE = _RC.FENCE_NEEDLE
VERDICT_HEADING = _RC.VERDICT_HEADING
FENCE_TICKS = _RC.FENCE_TICKS
FENCE_OPENER = _RC.FENCE_OPENER
FENCE_CLOSER = _RC.FENCE_CLOSER
# ---- end of the import ----

# The report header claude_review_gate.REPORT_HEADER writes, and the sha7 it names.
REPORT_HEAD = re.compile(r"\*\*Claude finished the automated review of ([0-9a-f]{7,40})\*\*")
BOT_LOGIN = "github-actions"

# Review Complete's title starts with one fixed token. current, capped, exhausted and outage are success (the last three with a warning), draft is neutral, stale, failed-run and hygiene are failure.
# `hygiene` is the normal state right after a review lands with findings, so --wait counts it as reviewed; `failed-run` ends the wait with its own exit code.
CHECK_NAME = "Review Complete"
TITLE_TOKENS = (
    "current",
    "capped",
    "exhausted",
    "outage",
    "draft",
    "stale",
    "failed-run",
    "hygiene",
)
REVIEWED_TOKENS = frozenset({"current", "capped", "exhausted", "outage", "hygiene"})
FAILED_RUN = "failed-run"
TERMINAL_TOKENS = REVIEWED_TOKENS | {FAILED_RUN}
TITLE_TOKEN = re.compile(r"^\s*([a-z][a-z-]*)")
WAIT_DEFAULT_S = 2100
WAIT_POLL_S = 30

RC_OK = 0
RC_UNANSWERED = 1
RC_UNREADABLE = 2
RC_TIMEOUT = 3
RC_FAILED_RUN = 4

FIXED_RE = re.compile(r"^fixed ([0-9a-f]{40})$")
NOT_A_BUG_RE = re.compile(r"^not-a-bug \| (.+)$")
DEFERRED_RE = re.compile(r"^deferred #([0-9a-f]{6,16})$")
DISPOSITION_LINE = re.compile(r"^F(\d+)[ \t]+(.*?)[ \t]*$")
SUMMARY_LINE = re.compile(r"^#[ \t]*summary:[ \t]*(\d+)[ \t]*$")
EVIDENCE_MIN = 20
TODO = "TODO"

THREADS_QUERY = (
    "query($owner:String!,$name:String!,$number:Int!,$after:String){"
    "repository(owner:$owner,name:$name){pullRequest(number:$number){"
    "reviewThreads(first:100,after:$after){pageInfo{hasNextPage endCursor}"
    "nodes{id isResolved comments(first:1){nodes{databaseId}}}}}}}"
)
RESOLVE_MUTATION = (
    "mutation($id:ID!){resolveReviewThread(input:{threadId:$id}){thread{isResolved}}}"
)

Runner = Callable[[list[str]], tuple[int, str, str]]
Items = Callable[[], dict[str, tuple[str, str]]]


class UnreadableError(RuntimeError):
    """A gh read failed or returned something that is not the expected JSON."""


# The CLI's own per-call bound: `--answer` and `--wait` run outside the Stop hook, which passes its budgeted runner instead (wl_checks.prreview_runner).
RUN_GH_TIMEOUT_S = 120
# (rc, stdout, stderr) of one `gh` call from the console root, stdin closed; rc 124 on a timeout and 127 when gh could not run.
run_gh: Runner = wl_gh.runner(CONSOLE_ROOT, timeout=RUN_GH_TIMEOUT_S)


def _read(what: str, result: tuple[Any, str]) -> Any:
    """The ONE conversion of a wl_gh read's `(None, why)` into UnreadableError, which every caller here expects."""
    data, err = result
    if data is None:
        raise UnreadableError("%s: %s" % (what, err))
    return data


def _gh_json(runner: Runner, what: str, argv: list[str]) -> Any:
    """The parsed JSON of the READ `gh <argv>` (wl_gh.call: a transient fault retried); UnreadableError otherwise."""
    return _read(what, wl_gh.call(argv, run=runner))


def _gh_list(runner: Runner, what: str, path: str) -> list[dict]:
    """Every page of a REST list, flattened (wl_gh.call_list); UnreadableError otherwise."""
    return _read(what, wl_gh.call_list(["api", path], run=runner))


# ---- the summary selector, the same rule review_comments runs ----


def _login(comment: dict) -> str:
    return ((comment.get("user") or {}).get("login")) or ""


def is_low_effort_reply(reply: str, min_chars: int = INLINE_MIN_CHARS) -> bool:
    normalized = TRAILING_PUNCT.sub("", reply.lower().strip())
    if normalized in LOW_EFFORT_PATTERNS:
        return True
    return len(normalized) < min_chars


def newest_summary(comments: list[dict]) -> dict | None:
    matches = []
    for comment in comments:
        body = comment.get("body") or ""
        if BOT_LOGIN not in _login(comment) or body.startswith("<!--"):
            continue
        if FENCE_NEEDLE in body or VERDICT_HEADING.search(body):
            matches.append(comment)
    if not matches:
        return None
    # `sort_by(.created_at) | last` in review_comments: the LAST of equal keys, which a plain max() would not pick.
    return max(enumerate(matches), key=lambda p: (p[1].get("created_at") or "", p[0]))[1]


def fence_block(body: str) -> list[str] | None:
    """The lines of the LAST closed findings fence, or None."""
    block: list[str] | None = None
    capturing = False
    buf: list[str] = []
    for line in body.split("\n"):
        if FENCE_OPENER.match(line):
            capturing, buf, block = True, [], None
            continue
        if capturing:
            if FENCE_CLOSER.match(line):
                block, capturing = buf, False
            else:
                buf.append(line)
    return block


def parse_findings(body: str) -> list[dict] | None:
    """The finding objects of the last closed fence, or None when it is absent or unparseable (fail closed: the summary then needs a reply)."""
    block = fence_block(body)
    if block is None:
        return None
    try:
        parsed = json.loads("\n".join(block))
    except ValueError:
        return None
    if not isinstance(parsed, list):
        return None
    return [f for f in parsed if isinstance(f, dict)] if parsed else []


def findings_fence_is_empty(body: str) -> bool:
    block = fence_block(body)
    if block is None:
        return False
    try:
        parsed = json.loads("\n".join(block))
    except ValueError:
        return False
    return isinstance(parsed, list) and not parsed


def summary_reply(comments: list[dict], summary: dict) -> dict | None:
    author = _login(summary)
    created = summary.get("created_at") or ""
    summary_id = str(summary.get("id"))
    candidates = [
        c for c in comments if _login(c) != author and (c.get("created_at") or "") > created
    ]
    for candidate in sorted(candidates, key=lambda c: c.get("created_at") or ""):
        body = candidate.get("body") or ""
        if is_low_effort_reply(body, SUMMARY_MIN_CHARS):
            continue
        if summary_id in body or len(body) >= SUMMARY_LONGFORM_CHARS:
            return candidate
    return None


def summary_verdict(comments: list[dict]) -> tuple[str, dict | None, dict | None]:
    """("none" | "empty" | "answered" | "unanswered", summary, reply)."""
    summary = newest_summary(comments)
    if summary is None:
        return "none", None, None
    if findings_fence_is_empty(summary.get("body") or ""):
        return "empty", summary, None
    reply = summary_reply(comments, summary)
    if reply is not None:
        return "answered", summary, reply
    return "unanswered", summary, None


# ---- reading the PR ----


class PrView:
    """Everything one mode needs from GitHub, read once."""

    def __init__(self, repo: str, number: int, head: str, issue: list[dict], inline: list[dict]):
        self.repo = repo
        self.number = number
        self.head = head
        self.issue = issue
        self.inline = inline
        self.verdict, self.summary, self.reply = summary_verdict(issue)

    @property
    def summary_id(self) -> str:
        return str(self.summary.get("id")) if self.summary else ""

    @property
    def summary_head(self) -> str:
        m = REPORT_HEAD.search((self.summary or {}).get("body") or "")
        return m.group(1) if m else ""

    def findings(self) -> list[dict] | None:
        return parse_findings((self.summary or {}).get("body") or "")


def read_repo(runner: Runner) -> str:
    data = _gh_json(runner, "repository", ["repo", "view", "--json", "nameWithOwner"])
    name = data.get("nameWithOwner") if isinstance(data, dict) else None
    if not isinstance(name, str) or "/" not in name:
        raise UnreadableError("repository: gh repo view gave no nameWithOwner")
    return name


def read_pr_head(runner: Runner, pr: int | None) -> tuple[int, str]:
    argv = ["pr", "view", *([str(pr)] if pr else []), "--json", "number,headRefOid"]
    data = _gh_json(runner, "pull request", argv)
    if not isinstance(data, dict) or not data.get("number") or not data.get("headRefOid"):
        raise UnreadableError("pull request: gh pr view gave no number or headRefOid")
    return int(data["number"]), str(data["headRefOid"])


def read_view(runner: Runner, pr: int | None) -> PrView:
    repo = read_repo(runner)
    number, head = read_pr_head(runner, pr)
    issue = _gh_list(runner, "issue comments", "repos/%s/issues/%d/comments" % (repo, number))
    inline = _gh_list(runner, "inline comments", "repos/%s/pulls/%d/comments" % (repo, number))
    return PrView(repo, number, head, issue, inline)


def _line_of(comment: dict) -> Any:
    line = comment.get("line")
    return comment.get("original_line") if line is None else line


def match_inline(findings: list[dict], inline: list[dict]) -> dict[int, dict]:
    """{finding index (1-based): its inline github-actions root comment}. A finding the gate skipped (no line, line outside the diff) has none."""
    roots = [
        c
        for c in sorted(inline, key=lambda c: c.get("created_at") or "")
        if c.get("in_reply_to_id") is None and BOT_LOGIN in _login(c)
    ]
    used: set[Any] = set()
    out: dict[int, dict] = {}
    for n, finding in enumerate(findings, 1):
        title = str(finding.get("title") or "")
        for c in reversed(roots):
            if c.get("id") in used:
                continue
            if c.get("path") != finding.get("path") or str(_line_of(c)) != str(finding.get("line")):
                continue
            if title and title not in (c.get("body") or ""):
                continue
            used.add(c.get("id"))
            out[n] = c
            break
    return out


def inline_answered(inline: list[dict], root: dict) -> bool:
    return any(
        r.get("in_reply_to_id") == root.get("id") and not is_low_effort_reply(r.get("body") or "")
        for r in inline
    )


def read_threads(runner: Runner, repo: str, number: int) -> dict[Any, tuple[str, bool]]:
    """{root comment databaseId: (thread node id, isResolved)} for every review thread."""
    owner, name = repo.split("/", 1)
    out: dict[Any, tuple[str, bool]] = {}
    after: str | None = None
    while True:
        argv = [
            "api",
            "graphql",
            "-f",
            "query=%s" % THREADS_QUERY,
            "-f",
            "owner=%s" % owner,
            "-f",
            "name=%s" % name,
            "-F",
            "number=%d" % number,
        ]
        if after:
            argv += ["-f", "after=%s" % after]
        data = _gh_json(runner, "review threads", argv)
        try:
            threads = data["data"]["repository"]["pullRequest"]["reviewThreads"]
            nodes = threads["nodes"]
            page = threads["pageInfo"]
        except (KeyError, TypeError) as exc:
            raise UnreadableError("review threads: unexpected GraphQL shape (%s)" % exc) from exc
        for node in nodes or []:
            first = ((node.get("comments") or {}).get("nodes") or [{}])[0]
            if first.get("databaseId") is not None:
                out[first["databaseId"]] = (str(node.get("id")), bool(node.get("isResolved")))
        if not page.get("hasNextPage"):
            return out
        after = page.get("endCursor")


# ---- --check and the Stop-hook entry point ----


def check_state(pr: int | None = None, runner: Runner = run_gh) -> dict[str, Any]:
    """The `--check` decision as data, for the Stop hook (GR9). Never raises.

    Keys: `rc` (0 no summary / answered / empty with every finding thread resolved, 1 unanswered or a finding thread unresolved, 2 unreadable), `pr`, `head`, `summary` (comment id or ""), `verdict`, `unresolved` (root comment ids of unresolved finding threads), `review_token` (Review Complete's title token on the head, "" when none or unreadable), `reason`.

    THE THREAD CLAUSE MATCHES THE REVIEW GATE, which runs check_resolved_threads.py beside the summary rule: an answered summary with a finding thread still open is a red gate, so it is rc 1 here too.
    """
    try:
        view = read_view(runner, pr)
        roots = [
            c for c in view.inline if c.get("in_reply_to_id") is None and BOT_LOGIN in _login(c)
        ]
        threads = read_threads(runner, view.repo, view.number) if roots else {}
    except UnreadableError as exc:
        return {
            "rc": RC_UNREADABLE,
            "pr": pr,
            "head": "",
            "summary": "",
            "verdict": "unreadable",
            "unresolved": [],
            "review_token": "",
            "reason": str(exc),
        }
    try:
        token = read_review_title(runner, view.repo, view.head)[0]
    except UnreadableError:
        token = ""
    unresolved = [c.get("id") for c in roots if not threads.get(c.get("id"), ("", False))[1]]
    rc = RC_UNANSWERED if view.verdict == "unanswered" or unresolved else RC_OK
    reasons = {
        "none": "no review summary on PR #%d" % view.number,
        "empty": "summary %s carries an empty findings array; nothing to answer" % view.summary_id,
        "answered": "summary %s answered by comment %s"
        % (view.summary_id, (view.reply or {}).get("id")),
        "unanswered": "summary %s on PR #%d has no substantive reply; run wl_prreview.py --draft, then --answer"
        % (view.summary_id, view.number),
    }
    reason = reasons[view.verdict]
    if unresolved:
        reason += (
            "; %d finding thread(s) unresolved (%s); run wl_prreview.py --draft, then --answer"
            % (
                len(unresolved),
                ", ".join(str(i) for i in unresolved),
            )
        )
    return {
        "rc": rc,
        "pr": view.number,
        "head": view.head,
        "summary": view.summary_id,
        "verdict": view.verdict,
        "unresolved": unresolved,
        "review_token": token,
        "reason": reason,
    }


def cmd_check(pr: int | None, runner: Runner) -> int:
    state = check_state(pr, runner)
    print(state["reason"], file=sys.stderr if state["rc"] == RC_UNREADABLE else sys.stdout)
    return int(state["rc"])


# ---- --status ----


def _loc(finding: dict) -> str:
    return "%s:%s" % (finding.get("path") or "?", finding.get("line") or "?")


def cmd_status(pr: int | None, runner: Runner) -> int:
    try:
        view = read_view(runner, pr)
    except UnreadableError as exc:
        print("wl_prreview --status: %s" % exc, file=sys.stderr)
        return RC_UNREADABLE
    print("PR #%d, head %s" % (view.number, view.head[:12]))
    if view.summary is None:
        print("no review summary")
        return RC_OK
    print(
        "summary #issuecomment-%s (reviewed head %s): %s"
        % (view.summary_id, view.summary_head or "?", view.verdict)
    )
    findings = view.findings()
    if findings is None:
        print("findings: the fence is absent or unparseable; the summary still needs a reply")
        return RC_OK
    print("findings: %d" % len(findings))
    matched = match_inline(findings, view.inline)
    for n, f in enumerate(findings, 1):
        root = matched.get(n)
        thread = (
            "inline %s %s"
            % (root.get("id"), "answered" if inline_answered(view.inline, root) else "unanswered")
            if root
            else "no inline thread"
        )
        print(
            "  F%d [%s] %s %s (%s)"
            % (n, f.get("severity") or "medium", _loc(f), f.get("title") or "finding", thread)
        )
    return RC_OK


# ---- --wait ----


def read_review_title(runner: Runner, repo: str, head: str) -> tuple[str, str]:
    """(title token, full title) of the newest Review Complete check run on `head`; ("", "") when none exists or the title carries no known token."""
    data = _gh_json(
        runner,
        "check runs",
        ["api", "repos/%s/commits/%s/check-runs?check_name=%s" % (repo, head, "Review%20Complete")],
    )
    runs = [
        r
        for r in (data.get("check_runs") or [] if isinstance(data, dict) else [])
        if isinstance(r, dict) and r.get("name") == CHECK_NAME
    ]
    if not runs:
        return "", ""
    newest = max(
        enumerate(runs),
        key=lambda p: (p[1].get("started_at") or p[1].get("completed_at") or "", p[0]),
    )[1]
    title = str((newest.get("output") or {}).get("title") or "")
    m = TITLE_TOKEN.match(title)
    return (m.group(1), title) if m and m.group(1) in TITLE_TOKENS else ("", title)


def read_pr_branch(runner: Runner, number: int) -> str:
    """The PR's head branch name, "" when gh does not say."""
    data = _gh_json(runner, "pull request", ["pr", "view", str(number), "--json", "headRefName"])
    name = data.get("headRefName") if isinstance(data, dict) else None
    return name if isinstance(name, str) else ""


# Tokens whose cause is usually written in an attempt comment rather than in the check title (agent/plans/PLAN-scheduled-red-detector.md, B3). On PR #594 the comment said `class: error_max_turns` and carried the re-run command, while the title said only that the review had not landed.
ATTEMPT_TOKENS = frozenset({FAILED_RUN, "exhausted", "outage", "stale"})


def attempt_note(runner: Runner, repo: str, number: int, head: str) -> str:
    """Lines naming the newest review-attempt comment on `head` (its class and the action it asks for), or "" when there is none or it cannot be read. Never raises: the generic text is the fallback."""
    try:
        import wl_prsignals as S  # noqa: PLC0415 -- sibling, loaded only when a wait ends badly

        comments = _gh_list(
            runner, "issue comments", "repos/%s/issues/%d/comments" % (repo, number)
        )
        try:
            branch = read_pr_branch(runner, number)
        except UnreadableError:
            branch = ""
        sig = S.newest_attempt(S.classify(comments, head, number, branch))
    except (UnreadableError, ImportError):
        return ""
    if sig is None:
        return ""
    return "  review attempt (class %s): %s\n  Next: %s" % (
        sig.get("cls") or "none",
        sig.get("text"),
        sig.get("action"),
    )


def cmd_wait(
    pr: int | None,
    timeout_s: int,
    runner: Runner,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    deadline = clock() + max(0, timeout_s)
    last = ""
    where: tuple[str, int, str] | None = None
    while True:
        try:
            repo = read_repo(runner)
            number, head = read_pr_head(runner, pr)
            token, title = read_review_title(runner, repo, head)
        except UnreadableError as exc:
            last = "unreadable: %s" % exc
        else:
            last = "token %r on %s" % (token or "none", head[:12])
            where = (repo, number, head)
            if token in REVIEWED_TOKENS:
                print(
                    "PR #%d head %s reviewed: Review Complete says %s" % (number, head[:12], token)
                )
                note = attempt_note(runner, repo, number, head) if token in ATTEMPT_TOKENS else ""
                if note:
                    print(note)
                return RC_OK
            if token == FAILED_RUN:
                note = attempt_note(runner, repo, number, head)
                # ONE "Next:". The attempt comment's action (re-run, excused, push) is the specific one, so it replaces the generic investigate line rather than printing beside it (review finding 3bc91573.1); the generic line stays the fallback when no attempt comment exists.
                generic = (
                    "  Next: investigate the Claude Review run (gh run list --workflow claude-review.yml), fix the cause,"
                    " then re-dispatch with `gh workflow run claude-review.yml -f pr_number=%d`."
                    % number
                )
                print(
                    "wl_prreview --wait: the review run for PR #%d head %s failed: %s\n%s"
                    % (number, head[:12], title, note or generic),
                    file=sys.stderr,
                )
                return RC_FAILED_RUN
        if clock() >= deadline:
            note = attempt_note(runner, *where) if where else ""
            print(
                "wl_prreview --wait: no terminal Review Complete within %ds (last: %s). Review Complete is required:"
                " the PR does not merge on a timeout; report it and run --wait again.%s"
                % (timeout_s, last, "\n" + note if note else ""),
                file=sys.stderr,
            )
            return RC_TIMEOUT
        sleeper(min(WAIT_POLL_S, max(1.0, deadline - clock())))


# ---- --draft ----


def _cell(text: Any) -> str:
    return str(text).replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def render_draft(view: PrView, findings: list[dict]) -> str:
    lines = [
        "# wl_prreview dispositions for PR #%d, head %s" % (view.number, view.head[:12]),
        "# summary: %s" % view.summary_id,
        "# Replace each TODO with one of:",
        "#   fixed <sha40>                 a commit on this branch (an ancestor of HEAD)",
        "#   not-a-bug | <evidence>        20+ characters citing an existing path:line or a sha on this branch",
        "#   deferred #<item>              an open worklist item",
    ]
    for n, f in enumerate(findings, 1):
        lines.append(
            "# F%d [%s] %s %s"
            % (n, f.get("severity") or "medium", _loc(f), _cell(f.get("title") or "finding"))
        )
        lines.append("F%d %s" % (n, TODO))
    return "\n".join(lines) + "\n"


def cmd_draft(pr: int | None, runner: Runner) -> int:
    try:
        view = read_view(runner, pr)
    except UnreadableError as exc:
        print("wl_prreview --draft: %s" % exc, file=sys.stderr)
        return RC_UNREADABLE
    if view.summary is None or view.verdict == "empty":
        print("wl_prreview --draft: no finding to answer (%s)" % view.verdict, file=sys.stderr)
        return RC_OK
    findings = view.findings()
    if findings is None:
        print(
            "wl_prreview --draft: summary %s has no parseable findings fence; answer it by hand with a reply citing #issuecomment-%s"
            % (view.summary_id, view.summary_id),
            file=sys.stderr,
        )
        return RC_UNANSWERED
    sys.stdout.write(render_draft(view, findings))
    return RC_OK


# ---- --answer ----


def default_items() -> dict[str, tuple[str, str]]:
    """{item id: (state, text)} from the worklist fold, the same fold `worklist.py --review-mark` supplies."""
    import wl_core as C  # noqa: PLC0415 -- sibling, loaded only when a deferral is checked
    import wl_store as S  # noqa: PLC0415

    fold = S.load(C.worklist_for(C.project_start()), sync=False)
    return {r["id"]: (r.get("state", " "), r.get("text", "")) for r in fold.items}


def parse_dispositions(text: str) -> tuple[str, dict[int, str], list[str]]:
    """(summary id named in the file, {finding number: disposition}, errors)."""
    summary = ""
    out: dict[int, str] = {}
    errors: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        m = SUMMARY_LINE.match(raw)
        if m:
            summary = m.group(1)
            continue
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = DISPOSITION_LINE.match(raw.strip())
        if not m:
            errors.append("line %d: %r is not `F<n> <disposition>`" % (lineno, raw.strip()))
            continue
        n = int(m.group(1))
        if n in out:
            errors.append("line %d: F%d has a second disposition" % (lineno, n))
            continue
        out[n] = m.group(2)
    return summary, out, errors


def validate(
    dispositions: dict[int, str],
    count: int,
    repo_root: pathlib.Path,
    items: Items,
) -> list[str]:
    """Every refusal, naming the finding. Empty means every finding has a valid disposition."""
    errors: list[str] = []
    fold: dict[str, tuple[str, str]] | None = None
    unreadable = ""
    errors.extend(
        "F%d: the summary has no such finding (it has %d)" % (n, count)
        for n in sorted(set(dispositions) - set(range(1, count + 1)))
    )
    for n in range(1, count + 1):
        d = dispositions.get(n, "")
        if not d or d == TODO:
            errors.append(
                "F%d: no disposition (fixed <sha40> | not-a-bug | <evidence> | deferred #<item>)"
                % n
            )
            continue
        m = FIXED_RE.match(d)
        if m:
            sha = m.group(1)
            if wl_review.git(repo_root, "merge-base", "--is-ancestor", sha, "HEAD")[0] != 0:
                errors.append(
                    "F%d: %s is not on this branch (not an ancestor of HEAD)" % (n, sha[:12])
                )
            continue
        m = NOT_A_BUG_RE.match(d)
        if m:
            evidence = m.group(1).strip()
            if len(evidence) < EVIDENCE_MIN:
                errors.append(
                    "F%d: not-a-bug needs at least %d characters of evidence" % (n, EVIDENCE_MIN)
                )
            elif not wl_review._citation_ok(repo_root, evidence):
                errors.append(
                    "F%d: not-a-bug evidence must cite a path:line that exists or a sha on this branch"
                    % n
                )
            continue
        m = DEFERRED_RE.match(d)
        if m:
            item = m.group(1)
            if fold is None and not unreadable:
                try:
                    fold = items()
                except Exception as exc:  # noqa: BLE001 -- an unreadable worklist refuses the deferral, it does not crash the verb
                    unreadable = str(exc) or type(exc).__name__
            if fold is None:
                # Every deferral is refused for the read failure, not only the first: an empty stand-in fold would call the later items missing.
                errors.append("F%d: the worklist cannot be read (%s)" % (n, unreadable))
                continue
            rec = fold.get(item)
            if rec is None:
                errors.append("F%d: worklist item #%s does not exist" % (n, item))
            elif rec[0] not in (" ", "?", ">"):
                errors.append(
                    "F%d: worklist item #%s is not open, [?] or [>] (state %r)" % (n, item, rec[0])
                )
            continue
        errors.append(
            "F%d: %r is not fixed <sha40> | not-a-bug | <evidence> | deferred #<item>" % (n, d)
        )
    return errors


def describe(d: str) -> str:
    m = FIXED_RE.match(d)
    if m:
        return "fixed in %s" % m.group(1)
    m = NOT_A_BUG_RE.match(d)
    if m:
        return "not a bug: %s" % m.group(1).strip()
    m = DEFERRED_RE.match(d)
    if m:
        return "deferred to worklist item #%s" % m.group(1)
    return d


def render_answer(view: PrView, findings: list[dict], dispositions: dict[int, str]) -> str:
    lines = [
        "Answer to the review summary #issuecomment-%s (reviewed head %s, PR head %s): %d finding(s), each with a disposition below."
        % (view.summary_id, view.summary_head or "?", view.head[:12], len(findings)),
        "",
        "| # | Severity | Location | Finding | Disposition |",
        "|---|---|---|---|---|",
    ]
    for n, f in enumerate(findings, 1):
        lines.append(
            "| F%d | %s | `%s` | %s | %s |"
            % (
                n,
                _cell(f.get("severity") or "medium"),
                _cell(_loc(f)),
                _cell(f.get("title") or "finding"),
                _cell(describe(dispositions[n])),
            )
        )
    return "\n".join(lines) + "\n"


def cmd_answer(
    pr: int | None,
    path: pathlib.Path,
    runner: Runner,
    repo_root: pathlib.Path = CONSOLE_ROOT,
    items: Items = default_items,
) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print("wl_prreview --answer: cannot read %s (%s)" % (path, exc), file=sys.stderr)
        return RC_UNANSWERED
    try:
        view = read_view(runner, pr)
    except UnreadableError as exc:
        print("wl_prreview --answer: %s" % exc, file=sys.stderr)
        return RC_UNREADABLE
    if view.summary is None or view.verdict == "empty":
        print("wl_prreview --answer: nothing to answer (%s); nothing posted" % view.verdict)
        return RC_OK
    findings = view.findings()
    if findings is None:
        print(
            "wl_prreview --answer: summary %s has no parseable findings fence; nothing posted"
            % view.summary_id,
            file=sys.stderr,
        )
        return RC_UNANSWERED
    named, dispositions, errors = parse_dispositions(text)
    if named and named != view.summary_id:
        errors.insert(
            0,
            "the file answers summary %s but the newest summary is %s; run --draft again"
            % (named, view.summary_id),
        )
    errors += validate(dispositions, len(findings), repo_root, items)
    if errors:
        print("wl_prreview --answer: refused, nothing posted:", file=sys.stderr)
        for e in errors:
            print("  %s" % e, file=sys.stderr)
        return RC_UNANSWERED

    body = render_answer(view, findings, dispositions)
    rc, out, err = wl_gh.write(
        [
            "api",
            "-X",
            "POST",
            "repos/%s/issues/%d/comments" % (view.repo, view.number),
            "-f",
            "body=%s" % body,
        ],
        run=runner,
    )
    if rc != 0:
        print(
            "wl_prreview --answer: posting the reply failed: %s" % (err or out).strip()[:300],
            file=sys.stderr,
        )
        return RC_UNREADABLE
    try:
        reply_id = str(json.loads(out).get("id") or "")
    except (ValueError, AttributeError):
        reply_id = ""
    print("posted the reply to summary %s as comment %s" % (view.summary_id, reply_id or "?"))

    failures = 0
    matched = match_inline(findings, view.inline)
    try:
        threads = read_threads(runner, view.repo, view.number) if matched else {}
    except UnreadableError as exc:
        print("wl_prreview --answer: %s; threads not resolved" % exc, file=sys.stderr)
        threads = {}
        failures += 1
    for n, root in sorted(matched.items()):
        cite = (
            "#issuecomment-%s" % reply_id
            if reply_id
            else "the reply to #issuecomment-%s" % view.summary_id
        )
        reply = "F%d: %s (answered in %s)." % (n, describe(dispositions[n]), cite)
        rc, _out, err = wl_gh.write(
            [
                "api",
                "-X",
                "POST",
                "repos/%s/pulls/%d/comments/%s/replies" % (view.repo, view.number, root.get("id")),
                "-f",
                "body=%s" % reply,
            ],
            run=runner,
        )
        if rc != 0:
            failures += 1
            print(
                "  F%d: in-thread reply to %s failed: %s" % (n, root.get("id"), err.strip()[:200]),
                file=sys.stderr,
            )
            continue
        thread = threads.get(root.get("id"))
        if thread is None:
            failures += 1
            print(
                "  F%d: no review thread found for comment %s" % (n, root.get("id")),
                file=sys.stderr,
            )
            continue
        if thread[1]:
            continue
        rc, _out, err = wl_gh.write(
            ["api", "graphql", "-f", "query=%s" % RESOLVE_MUTATION, "-f", "id=%s" % thread[0]],
            run=runner,
        )
        if rc != 0:
            failures += 1
            print(
                "  F%d: resolving thread %s failed: %s" % (n, thread[0], err.strip()[:200]),
                file=sys.stderr,
            )
    print("answered %d inline thread(s), %d failure(s)" % (len(matched), failures))
    return RC_UNREADABLE if failures else RC_OK


# ---- the CLI ----


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wl_prreview.py",
        description="Answer the PR-level Claude review summary (agent/plans/PLAN-github-pr-review-restore.md, GR7).",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--status", action="store_true", help="the newest summary, its findings and their threads"
    )
    mode.add_argument(
        "--wait",
        action="store_true",
        help="wait for a terminal Review Complete on the PR head (0 reviewed, 4 failed-run, 3 timeout)",
    )
    mode.add_argument(
        "--draft", action="store_true", help="print a dispositions file, one line per finding"
    )
    mode.add_argument(
        "--answer",
        metavar="FILE",
        help="validate the dispositions and post the reply, the in-thread replies and the resolves",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="0 no summary / answered / empty with threads resolved, 1 unanswered or a thread unresolved, 2 unreadable",
    )
    parser.add_argument(
        "--pr", type=int, help="the PR number (default: the PR of the current branch)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=WAIT_DEFAULT_S,
        help="--wait bound in seconds (default %(default)s)",
    )
    return parser


def main(argv: list[str] | None = None, runner: Runner = run_gh) -> int:
    args = build_parser().parse_args(argv)
    if args.status:
        return cmd_status(args.pr, runner)
    if args.wait:
        return cmd_wait(args.pr, args.timeout, runner)
    if args.draft:
        return cmd_draft(args.pr, runner)
    if args.answer:
        return cmd_answer(args.pr, pathlib.Path(args.answer), runner)
    return cmd_check(args.pr, runner)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
