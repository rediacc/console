"""The plan gate (box L2 of agent/plans/PLAN-plan-per-pr-loop.md): a console PR merges when its one plan has every box ticked, or when its body says why it merges otherwise.

THE LINK. A PR names its plan with one `Plan: agent/plans/PLAN-<slug>.md` line in its body. `.claude/hooks/post-bash/refresh_pr_body.py` writes that line from the head of the plan queue (`agent/plans/QUEUE.md`, read by `queue`) on the first push that finds the body without one, and never rewrites it after that: the link is set once and is then the PR's own, so a queue edit mid-PR cannot re-point a PR at another plan. A multi-plan PR, or a PR that
merges with open boxes, carries an `Operational-Reason:` line instead, and that line alone admits it.

THE ONE BOX PARSER. Boxes are counted by `wl_planfile.plan_boxes` (the Stop hook's parser, which `check_plan_boxes.py` and `.ci/config/plan-boxes.json` also use), cross-checked against `wl_planfile.raw_box_counts`, its dumber line count: the larger open count wins, so a parser that stops seeing a box cannot turn an open plan into a finished one. A plan with no
boxes at all proves nothing and is refused rather than read as finished.

WHICH COPY OF THE PLAN. `rev` names the commit whose copy is judged (`git show <rev>:<path>`), which is what the merge lands; "" reads the working tree. A moved plan (a `Status: moved` stub with `Moved-To:`) is followed once.

FAILS CLOSED. A body that could not be read, a plan that does not exist, a parser that does not import: each is a refusal with its reason, never an allow.

Used by `block_admin_merge` (every `gh pr merge` on the console PR) and `block_push_to_protected_branch` (the fast-forward fallback's last condition).
"""

from __future__ import annotations

import os
import pathlib
import re

from rediacc_hooks import commit_policy, syspath

QUEUE_REL = "agent/plans/QUEUE.md"

# A queue entry: a numbered list item whose whole text is one plan path, optionally followed by ` -- <note>`. Prose lines naming a plan are not entries.
QUEUE_ENTRY = re.compile(
    r"^[ \t]*\d+[.)][ \t]+`?(agent/plans/PLAN-[A-Za-z0-9._-]+\.md)`?(?:[ \t]+--[ \t].*)?[ \t]*$",
    re.MULTILINE,
)

# `Plan:` and `Operational-Reason:` at the start of a body line, tolerating list, quote and bold markup before or around the label.
PLAN_LINE = re.compile(r"(?m)^[ \t>*_-]*Plan\*{0,2}:\*{0,2}[ \t]*(.*?)[ \t]*$")
OPERATIONAL_REASON = re.compile(r"(?m)^[ \t>*_-]*Operational-Reason\*{0,2}:\*{0,2}[ \t]*\S")
PLAN_PATH = re.compile(r"^agent/plans/(?:_done/)?PLAN-[A-Za-z0-9._-]+\.md$")

# Machine-written blocks of a PR body. Their text is generated from other sources (worklist items, commit subjects), so a `Plan:` or `Operational-Reason:` inside one is not the PR's own statement.
GENERATED_BLOCK = re.compile(r"(?ms)^<!-- ([a-z-]+):begin -->$.*?^<!-- \1:end -->$")

STATUS = re.compile(r"(?m)^\*{0,2}Status\*{0,2}:[ \t]*([A-Za-z-]+)")
MOVED_TO = re.compile(r"(?m)^Moved-To:[ \t]*(\S+)[ \t]*$")

STOP_DIR = pathlib.Path(__file__).resolve().parent.parent / "hooks" / "stop"


def queue(root: str) -> list[str]:
    """The queued plan paths, in order, first = the plan the live branch works. [] when the file is absent."""
    try:
        text = (pathlib.Path(root) / QUEUE_REL).read_text(encoding="utf-8")
    except OSError:
        return []
    return [m.group(1) for m in QUEUE_ENTRY.finditer(text)]


def queue_head(root: str) -> str:
    """The first queued plan that exists in the working tree, "" when none does."""
    for rel in queue(root):
        if (pathlib.Path(root) / rel).is_file():
            return rel
    return ""


def own_text(body: str) -> str:
    """The body with every generated block removed."""
    return GENERATED_BLOCK.sub("", body)


def body_plans(body: str) -> list[str]:
    """Every value the body's `Plan:` lines name, comma-separated values split, backticks dropped."""
    found = []
    for m in PLAN_LINE.finditer(own_text(body)):
        for raw in m.group(1).split(","):
            value = raw.strip().strip("`").strip()
            if value:
                found.append(value)
    return found


def has_operational_reason(body: str) -> bool:
    return bool(OPERATIONAL_REASON.search(own_text(body)))


def with_plan_line(body: str, plan: str) -> str:
    """`body` with `Plan: <plan>` as its first line, unchanged when it already names a plan or `plan` is ""."""
    if not plan or body_plans(body):
        return body
    return "Plan: %s\n\n%s" % (plan, body) if body.strip() else "Plan: %s\n" % plan


def _read(root: str, rel: str, rev: str) -> str | None:
    if rev:
        return commit_policy.git(["show", "%s:%s" % (rev, rel)], cwd=root)
    try:
        return (pathlib.Path(root) / rel).read_text(encoding="utf-8")
    except OSError:
        return None


def _plan_text(root: str, rel: str, rev: str) -> tuple[str | None, str]:
    """(text, path actually read), following one `Moved-To:` stub."""
    text = _read(root, rel, rev)
    if text is None:
        return None, rel
    status = STATUS.search(text)
    moved = MOVED_TO.search(text)
    if status and status.group(1).lower() == "moved" and moved:
        target = moved.group(1)
        return _read(root, target, rev), target
    return text, rel


def open_boxes(root: str, rel: str, rev: str = "") -> tuple[int, int, str]:
    """(open, done, why-unreadable) for one plan. `why` is "" when the counts are real."""
    text, read = _plan_text(root, rel, rev)
    where = "%s at %s" % (read, rev) if rev else read
    if text is None:
        return 0, 0, "`%s` does not exist" % where
    try:
        syspath.on_sys_path(STOP_DIR)
        import wl_planfile  # noqa: PLC0415 -- loaded only for a merge decision

        parsed_open, parsed_done = wl_planfile.plan_boxes(text)
        raw_open, raw_done = wl_planfile.raw_box_counts(text)
    except Exception as exc:  # noqa: BLE001 -- unverifiable is refused, never allowed
        return 0, 0, "the plan parser could not run (%s: %s)" % (type(exc).__name__, exc)
    opened = max(len(parsed_open), raw_open)
    done = max(len(parsed_done), raw_done)
    if opened + done == 0:
        return 0, 0, "`%s` has no boxes, so nothing proves it finished" % where
    return opened, done, ""


def plan_merge_refusal(root: str, pr_body: str | None, rev: str = "") -> str:
    """ "" when the PR may merge on its plan, else the reason it may not.

    Admitted: the body carries an `Operational-Reason:` line, or it names exactly one plan (`Plan: agent/plans/PLAN-<slug>.md`) whose boxes are all ticked at `rev` ("" = the working tree under `root`).
    """
    if not isinstance(pr_body, str):
        return "the PR body could not be read, so its plan cannot be checked"
    if has_operational_reason(pr_body):
        return ""
    plans = body_plans(pr_body)
    if not plans:
        return "the PR body names no plan (`Plan: agent/plans/PLAN-<slug>.md`) and carries no `Operational-Reason:` line"
    if len(plans) > 1:
        return "the PR body names %d plans (%s); a multi-plan PR records an `Operational-Reason:` line" % (
            len(plans),
            ", ".join(plans),
        )
    rel = plans[0]
    if not PLAN_PATH.match(rel) or os.path.isabs(rel) or ".." in rel.split("/"):
        return "the `Plan:` line names `%s`, not agent/plans/PLAN-<slug>.md" % rel
    opened, done, why = open_boxes(root, rel, rev)
    if why:
        return why
    if opened:
        return "`%s` has %d open box(es) of %d, and the PR body carries no `Operational-Reason:` line" % (
            rel,
            opened,
            opened + done,
        )
    return ""


__all__ = [
    "QUEUE_REL",
    "body_plans",
    "has_operational_reason",
    "open_boxes",
    "plan_merge_refusal",
    "queue",
    "queue_head",
    "with_plan_line",
]
