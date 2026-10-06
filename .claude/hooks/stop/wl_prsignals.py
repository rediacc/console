"""wl_prsignals: the bot comments on a PR that speak about its current head, each with the action it asks for (agent/plans/PLAN-scheduled-red-detector.md, Part B).

WHY. On PR #594 the review workflow posted `<!-- claude-review-attempt: 4d3b950c... -->` with `class: error_max_turns`, attempt 1 of 3 and a ready re-run command, and no CI-watching instrument printed it: `ci-trace.py --wait` read only the check rollup, so a review that died of its turn budget sat unseen until a human opened the PR page. This module turns those comments into one short block that
`ci-trace.py` prints on every verdict and `wl_prreview.py --wait` prints when Review Complete fails, goes stale or times out.

THE MARKERS ARE COPIED BY VALUE. A hook runs from `.claude/settings.json` with no path to the `rediacc_ci` package, so each prefix below is a copy, and `.ci/rediacc_ci/tests/test_prsignals_pins.py` pins every one equal to its source. A copy that drifts would silently classify a real attempt comment as an unknown bot comment, which is the exact blindness this module exists to end.

PURE. No read, no environment, no clock: callers pass the comments they fetched, the head, the PR number and the branch, so the same function serves the tracer's `gh api` fetcher and wl_prreview's injectable runner.
"""

from __future__ import annotations

import json
import re
from typing import Any

# ---- copied by value; test_prsignals_pins.py pins each one equal to its source ----
# .ci/rediacc_ci/review/claude_review_gate.py MARKER_PREFIX / ATTEMPT_PREFIX
MARKER_PREFIX = "<!-- claude-reviewed:"
ATTEMPT_PREFIX = "<!-- claude-review-attempt:"
# .ci/rediacc_ci/review/review_table.py MARKER_PREFIX
TABLE_PREFIX = "<!-- per-commit-reviews:"
# .ci/rediacc_ci/review/pr_labels.py LEDGER_PREFIX
LEDGER_PREFIX = "<!-- claude-labels:"
# .ci/scripts/ci/label-guide-comment.cjs MARKER
LABEL_GUIDE_MARKER = "<!-- rediacc:label-guide -->"
# .claude/hooks/stop/wl_prreview.py REPORT_HEAD
REPORT_HEAD = re.compile(r"\*\*Claude finished the automated review of ([0-9a-f]{7,40})\*\*")
# .ci/rediacc_ci/core/review_budget.py
INFRA_CLASSES = ("error_max_turns", "error_during_execution")
REVIEW_FREE_REATTEMPTS_PER_HEAD = 2
REVIEW_MAX_ATTEMPTS_PER_HEAD = 3
# .ci/rediacc_ci/review/review_status.py OUTAGE_CLASSES
OUTAGE_CLASSES = (
    "api_error_429",
    "api_error_500",
    "api_error_502",
    "api_error_503",
    "api_error_504",
    "api_error_529",
)
# ---- end of the copy ----

FENCE_NEEDLE = "json:review-findings"
FENCE_TICKS = r"(?:\\?`){3}"  # backslash-escaped backticks count (PR #595 comment 6004950311)
FENCE_RE = re.compile(
    r"^[ \t]*%s%s[ \t]*\n(.*?)^[ \t]*%s[ \t]*$" % (FENCE_TICKS, re.escape(FENCE_NEEDLE), FENCE_TICKS),
    re.MULTILINE | re.DOTALL,
)
SHA_IN_MARKER = re.compile(r"^\s*([0-9a-f]{7,40})\b")
ATTEMPTS_LINE = re.compile(r"^attempts:[ \t]*([0-9]+)", re.MULTILINE)
CLASS_LINE = re.compile(r"^class:[ \t]*(\S*)", re.MULTILINE)

PRREVIEW = "python3 .claude/hooks/stop/wl_prreview.py"
RERUN = "gh workflow run claude-review.yml --ref %s -f pr_number=%s"
BRANCH_PLACEHOLDER = "<this PR's branch>"
CLIP = 100

# Attempt dispositions, the same three-way split claude_review_gate.attempt_body writes in prose.
RERUN_FREE = "rerun"
EXCUSED = "excused"
PUSH = "push"


def _login(comment: dict) -> str:
    return str((comment.get("user") or {}).get("login") or "")


def is_bot(comment: dict) -> bool:
    user = comment.get("user") or {}
    login = _login(comment)
    return user.get("type") == "Bot" or login.endswith("[bot]") or "github-actions" in login


def _clip(text: str, n: int = CLIP) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 3] + "..."


def _marker_sha(body: str, prefix: str) -> str:
    m = SHA_IN_MARKER.match(body[len(prefix) :])
    return m.group(1) if m else ""


def _same_head(sha: str, head: str) -> bool:
    return bool(sha) and bool(head) and (head.startswith(sha) or sha.startswith(head))


def _stamp(comment: dict) -> str:
    return max(str(comment.get("created_at") or ""), str(comment.get("updated_at") or ""))


def attempt_disposition(cls: str, attempts: int) -> str:
    """RERUN_FREE, EXCUSED or PUSH for one recorded attempt; the rule claude_review_gate.attempt_body and review_status apply."""
    if cls in OUTAGE_CLASSES:
        return EXCUSED
    if cls in INFRA_CLASSES and attempts <= REVIEW_FREE_REATTEMPTS_PER_HEAD:
        return RERUN_FREE
    return PUSH


def _findings_count(body: str) -> int | None:
    blocks = FENCE_RE.findall(body)
    if not blocks:
        return None
    try:
        parsed = json.loads(blocks[-1])
    except ValueError:
        return None
    return len(parsed) if isinstance(parsed, list) else None


def _signal(comment: dict, kind: str, text: str, action: str = "", **extra: Any) -> dict:
    sig = {
        "id": comment.get("id"),
        "updated_at": str(comment.get("updated_at") or comment.get("created_at") or ""),
        "kind": kind,
        "text": text,
        "action": action,
        "url": str(comment.get("html_url") or ""),
    }
    sig.update(extra)
    return sig


def _attempt(comment: dict, body: str, sha: str, pr: Any, branch: str) -> dict:
    m = ATTEMPTS_LINE.search(body)
    attempts = int(m.group(1)) if m else 1
    m = CLASS_LINE.search(body)
    cls = m.group(1) if m else ""
    disposition = attempt_disposition(cls, attempts)
    text = "review attempt %d of %d on %s produced no report (%s)" % (
        attempts,
        REVIEW_MAX_ATTEMPTS_PER_HEAD,
        sha[:7],
        cls or "no class",
    )
    if disposition == RERUN_FREE:
        text += "; infrastructure class, a free re-attempt on the same head"
        action = RERUN % (branch or BRANCH_PLACEHOLDER, pr)
    elif disposition == EXCUSED:
        text += "; LLM outage class"
        action = "excused: Review Complete passes with an outage warning"
    else:
        text += "; this head's review budget is spent"
        action = "push a change to earn another review pass"
    return _signal(
        comment,
        "attempt",
        text,
        action,
        sha=sha,
        cls=cls,
        attempts=attempts,
        disposition=disposition,
    )


def classify(
    comments: list[dict], head: str, pr: Any, branch: str, head_date: str = ""
) -> list[dict]:
    """The signals for `head`, oldest first.

    A bot comment is for this head when its marker sha is the head, when its REPORT_HEAD sha7 is the head's prefix, or (a comment with no sha at all) when it was created or edited after `head_date`, the head's committer date. With no `head_date` a sha-less comment is dropped: noise from an older head is worse than one missing informational line.
    """
    out: list[dict] = []
    for c in sorted(
        (c for c in comments or [] if isinstance(c, dict)),
        key=lambda c: (str(c.get("created_at") or ""), str(c.get("id"))),
    ):
        if not is_bot(c):
            continue
        body = str(c.get("body") or "")
        stripped = body.lstrip()
        if stripped.startswith(ATTEMPT_PREFIX):
            sha = _marker_sha(stripped, ATTEMPT_PREFIX)
            if _same_head(sha, head):
                out.append(_attempt(c, stripped, sha, pr, branch))
            continue
        if stripped.startswith(MARKER_PREFIX):
            sha = _marker_sha(stripped, MARKER_PREFIX)
            if _same_head(sha, head):
                out.append(
                    _signal(
                        c,
                        "reviewed",
                        "Claude review completed for %s" % sha[:7],
                        "%s --status" % PRREVIEW,
                        sha=sha,
                    )
                )
            continue
        m = REPORT_HEAD.search(body)
        if m:
            sha = m.group(1)
            if not _same_head(sha, head):
                continue
            count = _findings_count(body)
            if count:
                out.append(
                    _signal(
                        c,
                        "summary",
                        "review summary for %s carries %d finding(s)" % (sha[:7], count),
                        "%s --draft, then --answer" % PRREVIEW,
                        sha=sha,
                        findings=count,
                    )
                )
            elif count == 0:
                out.append(
                    _signal(c, "summary", "review summary for %s: no findings" % sha[:7], sha=sha)
                )
            else:
                out.append(
                    _signal(
                        c,
                        "summary",
                        "review summary for %s has no parseable findings fence" % sha[:7],
                        "%s --status" % PRREVIEW,
                        sha=sha,
                    )
                )
            continue
        # The table and the ledger are upserted, and their marker names the head they were last written for, so a sha decides them when one is there.
        prefix = next((p for p in (TABLE_PREFIX, LEDGER_PREFIX) if stripped.startswith(p)), "")
        sha = _marker_sha(stripped, prefix) if prefix else ""
        if sha:
            if not _same_head(sha, head):
                continue
        elif not head_date or _stamp(c) <= head_date:
            continue
        if prefix == TABLE_PREFIX:
            out.append(_signal(c, "table", "per-commit review table updated", sha=sha))
        elif prefix == LEDGER_PREFIX:
            out.append(_signal(c, "ledger", "label ledger updated", sha=sha))
        elif stripped.startswith(LABEL_GUIDE_MARKER):
            out.append(_signal(c, "label-guide", "label guide posted"))
        else:
            first = next((ln for ln in body.splitlines() if ln.strip()), "")
            out.append(_signal(c, "bot", "%s: %s" % (_login(c), _clip(first))))
    return out


def newest_attempt(signals: list[dict]) -> dict | None:
    attempts = [s for s in signals or [] if s.get("kind") == "attempt"]
    return attempts[-1] if attempts else None


def render_signal(sig: dict) -> list[str]:
    lines = ["  %-11s %s" % (sig.get("kind"), sig.get("text"))]
    if sig.get("action"):
        lines.append("    next: %s" % sig["action"])
    return lines


def render(signals: list[dict], pr: Any, head: str) -> str:
    """The `PR SIGNALS (#<pr> @ <sha8>)` block."""
    title = "PR SIGNALS (#%s @ %s)" % (pr, (head or "?")[:8])
    if not signals:
        return "%s: no bot comment for this head" % title
    lines = [title]
    for sig in signals:
        lines.extend(render_signal(sig))
    return "\n".join(lines)
