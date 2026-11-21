"""The plan gate (box L2 of agent/plans/PLAN-plan-per-pr-loop.md): a console PR merges when its one plan has every box ticked, or when its body says why it merges otherwise.

THE LINK. A PR names its plan with one `Plan: agent/plans/PLAN-<slug>.md` line in its body. `.claude/hooks/post-bash/refresh_pr_body.py` writes that line from the head of the plan queue (`agent/plans/QUEUE.md`, read by `queue`: its hand-ordered `## Promoted` list first, then the `## Generated` one `wl_planqueue` renders) on the first push that finds the body without one, and never rewrites it after that: the link is set once and is then the PR's own, so a queue edit mid-PR cannot re-point a PR at another plan. A multi-plan PR, or a PR that
merges with open boxes, carries an `Operational-Reason:` line instead, and that line alone admits it.

THE ONE BOX PARSER. Boxes are counted by `wl_planfile.plan_boxes` (the Stop hook's parser, which `check_plan_boxes.py` and `.ci/config/plan-boxes.json` also use), cross-checked against `wl_planfile.raw_box_counts`, its dumber line count: the larger open count wins, so a parser that stops seeing a box cannot turn an open plan into a finished one. A plan with no
boxes at all proves nothing and is refused rather than read as finished.

WHICH COPY OF THE PLAN. `rev` names the commit whose copy is judged (`git show <rev>:<path>`), which is what the merge lands; "" reads the working tree. A moved plan (a `Status: moved` stub with `Moved-To:`) is followed once.

FAILS CLOSED. A body that could not be read, a plan that does not exist, a parser that does not import: each is a refusal with its reason, never an allow.

THE PLAN SET. `pr_plan_set` closes the PR's plans over their unfinished prerequisites (operator ruling 7 of agent/plans/PLAN-stop-hook-one-plan-scope.md), and the merge gate, P-A1 and the Stop hook all read it, so the three count the same plans.

Used by `block_admin_merge` (every `gh pr merge` on the console PR) and `block_push_to_protected_branch` (the fast-forward fallback's last condition).
"""

from __future__ import annotations

import os
import pathlib
import re

from rediacc_hooks import commit_policy, syspath

QUEUE_REL = "agent/plans/QUEUE.md"

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
    """The queued plan paths, in order: the `## Promoted` entries first (hand-ordered, they win), then the `## Generated` ones. [] when the file is absent or the format module cannot load, which leaves a PR body without a `Plan:` line and the merge refused for it."""
    try:
        text = (pathlib.Path(root) / QUEUE_REL).read_text(encoding="utf-8")
        syspath.on_sys_path(STOP_DIR)
        import wl_planqueue
    except (OSError, ImportError):
        return []
    return wl_planqueue.ordered(text)


def queue_head(root: str) -> str:
    """The first queued plan that exists in the working tree (the first Promoted one when any exists), "" when none does."""
    for rel in queue(root):
        if (pathlib.Path(root) / rel).is_file():
            return rel
    return ""


def pushed_tip(root: str, branch: str) -> str:
    """The 40-hex tip of `branch` on origin (`git ls-remote origin refs/heads/<branch>`), "" when it cannot be read: no such branch, an unreachable origin, a missing git or unparseable output. The PR body is judged at the pushed head, so a writer that names a plan reads it here, never from the working tree."""
    if not branch:
        return ""
    out = commit_policy.git(["ls-remote", "origin", "refs/heads/%s" % branch], cwd=root)
    first = (out or "").split("\n", 1)[0].split("\t", 1)[0].strip()
    return first if re.fullmatch(r"[0-9a-f]{40}", first) else ""


def exists_at(root: str, rev: str, rel: str) -> bool:
    """True when `rel` is a file in commit `rev` (`git cat-file -e <rev>:<rel>`); False for an empty `rev` or a `rev` missing locally."""
    if not rev or not rel:
        return False
    return commit_policy.git(["cat-file", "-e", "%s:%s" % (rev, rel)], cwd=root) is not None


def queue_at(root: str, rev: str) -> list[str]:
    """`queue`, read from agent/plans/QUEUE.md at commit `rev` instead of the working tree; [] when `rev` is empty or the file or the format module cannot be read there."""
    if not rev:
        return []
    text = _read(root, QUEUE_REL, rev)
    if text is None:
        return []
    try:
        return _planqueue().ordered(text)
    except ImportError:
        return []


def queue_head_at(root: str, rev: str) -> str:
    """`queue_head` judged at commit `rev`: the first queued plan, in the queue at `rev`, that is a file at `rev`; "" when none is or `rev` is empty."""
    for rel in queue_at(root, rev):
        if exists_at(root, rev, rel):
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
    """`body` with `Plan: <plan>` as its first line, unchanged when it already names a plan or `plan` is "": the write-once link. A PR carries one plan, so nothing is ever appended to an existing `Plan:` line."""
    if not plan or body_plans(body):
        return body
    return "Plan: %s\n\n%s" % (plan, body) if body.strip() else "Plan: %s\n" % plan


def _read(root: str, rel: str, rev: str) -> str | None:
    if rev:
        return commit_policy.git(["show", "%s:%s" % (rev, rel)], cwd=root)
    try:
        return (pathlib.Path(root) / rel).read_text(encoding="utf-8")
    # A non-UTF-8 file reads as absent, so callers fall back to defaults instead of crashing.
    except (OSError, UnicodeDecodeError):
        return None


def _planqueue():
    syspath.on_sys_path(STOP_DIR)
    import wl_planqueue

    return wl_planqueue


def settings_at(root: str, rev: str = ""):
    """(Settings, problems) of agent/plans/QUEUE.md's `## Settings` block at `rev` ("" = the working tree), parsed by `wl_planqueue.settings`, so the hook, the guards and CI read one switchboard through one parser. A file that does not exist is all defaults; one that exists but cannot be read is all defaults and a problem; a rev that cannot be read is all defaults and a problem; a parser that will not import is all defaults and a problem. Every default is the fail-safe one: effort high."""
    try:
        pq = _planqueue()
    except ImportError as exc:
        return _default_settings(), ["wl_planqueue could not import (%s)" % exc]
    text = _read(root, QUEUE_REL, rev)
    if text is None:
        if rev:
            return pq.Settings(), ["%s at %s is unreadable" % (QUEUE_REL, rev)]
        # `_read` also answers None for a file that exists but cannot be read (permissions, not UTF-8): defaults, with the problem said so callers that warn on problems do.
        if (pathlib.Path(root) / QUEUE_REL).exists():
            return pq.Settings(), ["%s is unreadable (not UTF-8 or not readable)" % QUEUE_REL]
        return pq.Settings(), []
    return pq.settings(text)


def _default_settings():
    """A stand-in carrying the fail-safe values when wl_planqueue cannot import."""
    import types

    return types.SimpleNamespace(
        effort="high",
        cadence=True,
        agent_hint=True,
        agent_pushback=True,
        judge="full",
        notes={},
    )


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
        import wl_planfile

        parsed_open, parsed_done = wl_planfile.plan_boxes(text)
        raw_open, raw_done = wl_planfile.raw_box_counts(text)
    except Exception as exc:
        # Fail closed: a plan that cannot be verified is refused, never allowed.
        return 0, 0, "the plan parser could not run (%s: %s)" % (type(exc).__name__, exc)
    opened = max(len(parsed_open), raw_open)
    done = max(len(parsed_done), raw_done)
    if opened + done == 0:
        return 0, 0, "`%s` has no boxes, so nothing proves it finished" % where
    return opened, done, ""


def _plandeps():
    syspath.on_sys_path(STOP_DIR)
    import wl_plandeps

    return wl_plandeps


def pr_plan_set(root: str, body: str | None, rev: str = "") -> tuple[tuple[str, ...], list[str]]:
    """(plans, problems): the plans a PR works (operator ruling 7 of agent/plans/PLAN-stop-hook-one-plan-scope.md, 2026-10-03).

    The body's own `Plan:` plans (every one it names; a multi-plan body is admitted only with `Operational-Reason:`, which is `plan_merge_refusal`'s question), or `queue_head(root)` when the body names none or is None, closed over every UNFINISHED plan they depend on, transitively, through `Depends-On:` edges and task refs (`wl_plandeps.Graph`, resolved at plan level). A prerequisite is finished when its Status is finished (`Graph.is_complete`) or every box is ticked (`open_boxes` at `rev`); a held one is not finished, so it stays in. The tuple is ordered prerequisites first (a deepest-first walk), so its first member is the plan to work first.

    `problems` names every cycle and every dependency that does not resolve to a live or finished plan (dangling, withdrawn, ambiguous), each with the depending plan's path, and the graph not loading at all. Each reader fails closed on a problem: the hook reports it, P-A1 and the merge gate refuse on it. The Stop hook (`wl_prscope.loop_state`), P-A1 (`check_plan_implementation.clock_scope`) and the merge gate (`plan_merge_refusal`) all call this, so the three count the same set.

    The dependency graph is read from the working tree; box completeness is read at `rev`.
    """
    problems: list[str] = []
    own: list[str] = []
    for rel in body_plans(body) if isinstance(body, str) else []:
        if not PLAN_PATH.match(rel) or os.path.isabs(rel) or ".." in rel.split("/"):
            problems.append("the `Plan:` line names `%s`, not agent/plans/PLAN-<slug>.md" % rel)
        elif rel not in own:
            own.append(rel)
    if not own and not problems:
        head = queue_head(root)
        if head:
            own.append(head)
    if not own:
        return (), problems
    try:
        deps = _plandeps()
        graph = deps.Graph.load(root)
    except Exception as exc:
        problems.append(
            "the plan dependency graph could not load (%s: %s)" % (type(exc).__name__, exc)
        )
        return tuple(own), problems

    def walk_from(rel: str) -> str:
        # A moved stub is walked from the plan it points at.
        target = graph.resolve(rel.rsplit("/", 1)[-1])
        if target.state in (deps.LIVE, deps.COMPLETE) and target.rel in graph.plans:
            return target.rel
        return rel

    def finished(rel: str) -> bool:
        opened, _done, why = open_boxes(root, rel, rev)
        return not why and opened == 0

    order: list[str] = []
    done: set[str] = set()

    def visit(rel: str, stack: list[str]) -> None:
        node = walk_from(rel)
        for edge in graph.edges(node):
            target = graph.resolve(str(edge))
            if target.state == deps.COMPLETE:
                continue
            if target.state != deps.LIVE:
                problems.append(
                    "`%s` depends on `%s`, which is %s: %s"
                    % (node, edge, target.state, target.detail)
                )
                continue
            if target.rel == node:
                continue
            if target.rel in stack:
                # Reported even when a member is ticked: the headers themselves are circular.
                loop = [*stack[stack.index(target.rel) :], target.rel]
                problems.append("a dependency cycle: %s" % " -> ".join(loop))
                continue
            if finished(target.rel):
                continue
            if target.rel not in done:
                visit(target.rel, [*stack, target.rel])
        if node not in done:
            done.add(node)
            order.append(rel if rel in own else node)

    for rel in own:
        if walk_from(rel) not in done:
            visit(rel, [walk_from(rel)])
    return tuple(order), problems


def _base(rel: str) -> str:
    return str(rel).rsplit("/", 1)[-1]


# WRITER-STARTABLE (#faedaaf9). A box only the lead or the operator can do (a production query, a deploy, an operator's own walk, a commit in a sibling repo outside the console PR) names that in its first words, `T4 Lead: ...` / `Operator: ...`, or anywhere as `lead-only` / `operator-only`; a plan whose remaining work is all of that kind says so once in its header, `Writers: none -- <reason>`. `writer_startable` reads both, so a plan whose open boxes are all of that kind starts no writer.
# THE BRACKET TAGS COUNT TOO (agent/plans/PLAN-idle-writer-capacity.md D1-D2): a box tagged `[live]`, `[operator window]`, `[hostinger rollout]`, `[fleet]` and the like, or waiting for the merge (`post-merge` in its tag, or a `Depends on:` clause naming a merge), is no writer's either. The tag grammar is `wl_boxready`'s, read here rather than copied. An untagged box stays startable, so an older plan with code boxes and no tags is still counted and picked.
_LEAD_BOX = re.compile(
    r"^\s*[-*+]\s+\[[ ?>]\]\s+(?:\*\*)?(?:\S+\s+)?(?:lead|operator):|\b(?:lead|operator)-only\b",
    re.IGNORECASE,
)
_OPEN_BOX = re.compile(r"^\s*[-*+]\s+\[[ ?>]\]\s+\S")


def _boxready():
    syspath.on_sys_path(STOP_DIR)
    import wl_boxready

    return wl_boxready


def writer_startable(text: str) -> bool:
    """Whether a writer can do any open box of this plan text before the merge: False under a `Writers: none` header, or when every open box is marked lead- or operator-only, carries a non-writer tag, or waits for the merge."""
    br = _boxready()
    if br.WRITERS_NONE_RE.search(text or ""):
        return False
    opened = [ln for ln in (text or "").splitlines() if _OPEN_BOX.match(ln)]
    return any(not _LEAD_BOX.search(ln) and br.startable(ln) for ln in opened)


def plan_merge_refusal(root: str, pr_body: str | None, rev: str = "") -> str:
    """ "" when the PR may merge on its plans, else the reason it may not.

    Admitted: the body carries an `Operational-Reason:` line; or it names exactly one plan (`Plan: agent/plans/PLAN-<slug>.md`) whose boxes are all ticked at `rev` ("" = the working tree under `root`). A body naming more than one plan without an `Operational-Reason:` line is refused: a plan rides exactly one PR, and a PR carries one plan (agent/plans/PLAN-simple-two-tree-loop.md ruling 4). Every unfinished prerequisite in the plan set's closure is checked too.
    """
    if not isinstance(pr_body, str):
        return "the PR body could not be read, so its plan cannot be checked"
    if has_operational_reason(pr_body):
        return ""
    plans = body_plans(pr_body)
    if not plans:
        return "the PR body names no plan (`Plan: agent/plans/PLAN-<slug>.md`) and carries no `Operational-Reason:` line"
    if len(plans) > 1:
        return (
            "the PR body names %d plans (%s); a multi-plan PR records an `Operational-Reason:` line"
            % (
                len(plans),
                ", ".join(plans),
            )
        )
    for rel in plans:
        if not PLAN_PATH.match(rel) or os.path.isabs(rel) or ".." in rel.split("/"):
            return "the `Plan:` line names `%s`, not agent/plans/PLAN-<slug>.md" % rel
    for rel in plans:
        opened, done, why = open_boxes(root, rel, rev)
        if why:
            return why
        if opened:
            return (
                "`%s` has %d open box(es) of %d, and the PR body carries no `Operational-Reason:` line"
                % (
                    rel,
                    opened,
                    opened + done,
                )
            )
    # Operator ruling 7 (2026-10-03): the PR's plan set holds every unfinished prerequisite, and a ticked plan whose prerequisite is open does not merge.
    owner = plans[0] if len(plans) == 1 else ", ".join(plans)
    members, problems = pr_plan_set(root, pr_body, rev)
    if problems:
        return "the PR's plan set cannot be trusted: %s" % "; ".join(problems)
    for member in members:
        if member in plans:
            continue
        opened, done, why = open_boxes(root, member, rev)
        if why:
            return "`%s`, a prerequisite of `%s`: %s" % (member, owner, why)
        if opened:
            return "`%s` is a prerequisite of `%s` and has %d open box(es) of %d" % (
                member,
                owner,
                opened,
                opened + done,
            )
    return ""


__all__ = [
    "QUEUE_REL",
    "body_plans",
    "exists_at",
    "has_operational_reason",
    "open_boxes",
    "plan_merge_refusal",
    "pr_plan_set",
    "pushed_tip",
    "queue",
    "queue_at",
    "queue_head",
    "queue_head_at",
    "settings_at",
    "with_plan_line",
    "writer_startable",
]
