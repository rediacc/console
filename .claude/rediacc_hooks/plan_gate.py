"""The plan gate (box L2 of agent/plans/PLAN-plan-per-pr-loop.md): a console PR merges when its one plan has every box ticked, or when its body says why it merges otherwise.

THE LINK. A PR names its plan with one `Plan: agent/plans/PLAN-<slug>.md` line in its body. `.claude/hooks/post-bash/refresh_pr_body.py` writes that line from the head of the plan queue (`agent/plans/QUEUE.md`, read by `queue`: its hand-ordered `## Promoted` list first, then the `## Generated` one `wl_planqueue` renders) on the first push that finds the body without one, and never rewrites it after that: the link is set once and is then the PR's own, so a queue edit mid-PR cannot re-point a PR at another plan. A multi-plan PR, or a PR that
merges with open boxes, carries an `Operational-Reason:` line instead, and that line alone admits it.

TURBO (agent/plans/PLAN-stop-hook-turbo.md D5/D6). With `turbo: on` in agent/plans/QUEUE.md `## Settings` (read by `settings_at`, the one parser `wl_planqueue.settings`), the PR keeps taking plans: `next_turbo` names the queued plans to start on free writer slots, `record_turbo_named` keeps what the Stop hook named, and `refresh_pr_body` appends those to the existing `Plan:` line (`with_plan_line`'s append mode) without rewriting an entry. The merge gate then admits a body naming any number of plans when turbo is on at the merged rev and every named plan, and every unfinished prerequisite, is ticked. With turbo off every rule above holds byte for byte.

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
        import wl_planqueue  # noqa: PLC0415 -- the one reader of the queue's format
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


def with_plan_line(body: str, plan: str, append: tuple[str, ...] | list[str] = ()) -> str:
    """`body` with `Plan: <plan>` as its first line, unchanged when it already names a plan or `plan` is "".

    `append` is the turbo mode (agent/plans/PLAN-stop-hook-turbo.md D5): the plans the Stop hook named for this PR. A body that already names plans gains each missing one at the end of its first own `Plan:` line (a line inside a generated block is not the body's own); a body that names none is written `Plan: <plan>, <appended...>`. A plan the body names already is never written twice and an existing entry is never rewritten. An empty `append` is the write-once link, byte for byte."""
    have = body_plans(body)
    if not append:
        if not plan or have:
            return body
        return "Plan: %s\n\n%s" % (plan, body) if body.strip() else "Plan: %s\n" % plan
    if not have:
        wanted = []
        for rel in (plan, *append):
            if rel and rel not in wanted:
                wanted.append(rel)
        if not wanted:
            return body
        line = "Plan: %s" % ", ".join(wanted)
        return "%s\n\n%s" % (line, body) if body.strip() else "%s\n" % line
    missing = []
    for rel in append:
        if rel and rel not in have and rel not in missing:
            missing.append(rel)
    if not missing:
        return body
    generated = [m.span() for m in GENERATED_BLOCK.finditer(body)]
    for m in PLAN_LINE.finditer(body):
        if any(lo <= m.start() < hi for lo, hi in generated):
            continue
        cut = m.end(1)
        sep = ", " if m.group(1).strip() else ""
        return body[:cut] + sep + ", ".join(missing) + body[cut:]
    return body


def _read(root: str, rel: str, rev: str) -> str | None:
    if rev:
        return commit_policy.git(["show", "%s:%s" % (rev, rel)], cwd=root)
    try:
        return (pathlib.Path(root) / rel).read_text(encoding="utf-8")
    except OSError:
        return None


def _planqueue():
    syspath.on_sys_path(STOP_DIR)
    import wl_planqueue  # noqa: PLC0415 -- the one reader of the queue's format and its settings block

    return wl_planqueue


def settings_at(root: str, rev: str = ""):
    """(Settings, problems) of agent/plans/QUEUE.md's `## Settings` block at `rev` ("" = the working tree), parsed by `wl_planqueue.settings` (agent/plans/PLAN-stop-hook-turbo.md D2), so the hook, the guards and CI read one switchboard through one parser. A file that does not exist is all defaults; a rev that cannot be read is all defaults and a problem; a parser that will not import is all defaults and a problem. Every default is the fail-safe one: hook on, turbo off, batch 1."""
    try:
        pq = _planqueue()
    except ImportError as exc:
        return _default_settings(), ["wl_planqueue could not import (%s)" % exc]
    text = _read(root, QUEUE_REL, rev)
    if text is None:
        if rev:
            return pq.Settings(), ["%s at %s is unreadable" % (QUEUE_REL, rev)]
        return pq.Settings(), []
    return pq.settings(text)


def _default_settings():
    """A stand-in carrying the fail-safe values when wl_planqueue cannot import."""
    import types  # noqa: PLC0415

    return types.SimpleNamespace(
        stop_hook=True,
        turbo=False,
        batch_size=1,
        plan_concurrency=1,
        writer_cap=4,
        commit_remind_min=15,
        cadence=True,
        agent_hint=True,
        agent_pushback=True,
        judge=True,
        notes={},
    )


def plan_concurrency(settings) -> int:
    """How many unfinished plans may be in flight at once under turbo: QUEUE.md `plan_concurrency:` (operator 2026-10-04: "batch_size: 3 is for plan concurrency? Maybe we need a new field"), 1 with turbo off. `batch_size` stays the merge minimum; this is the parallelism ceiling `next_turbo` fills up to."""
    return max(1, int(getattr(settings, "plan_concurrency", 1))) if settings.turbo else 1


def batch_size(settings) -> int:
    """The effective batch size: `batch_size` under turbo, 1 otherwise (agent/plans/PLAN-stop-hook-turbo.md D2). The one place it is computed."""
    return max(1, int(settings.batch_size)) if settings.turbo else 1


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


def _plandeps():
    syspath.on_sys_path(STOP_DIR)
    import wl_plandeps  # noqa: PLC0415 -- the one home of the Depends-On grammar and its graph

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
    except Exception as exc:  # noqa: BLE001 -- a graph that cannot load hides every prerequisite
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


# WRITER-STARTABLE (#faedaaf9). A box only the lead or the operator can do (a production query, a deploy, an operator's own walk, a commit in a sibling repo outside the console PR) names that in its first words, `T4 Lead: ...` / `Operator: ...`, or anywhere as `lead-only` / `operator-only`; a plan whose remaining work is all of that kind says so once in its header, `Writers: none -- <reason>`. A turbo pick is a writer slot, so a plan with no open box a writer can do is no pick.
_LEAD_BOX = re.compile(
    r"^\s*[-*+]\s+\[[ ?>]\]\s+(?:\*\*)?(?:\S+\s+)?(?:lead|operator):|\b(?:lead|operator)-only\b",
    re.IGNORECASE,
)
_OPEN_BOX = re.compile(r"^\s*[-*+]\s+\[[ ?>]\]\s+\S")
_NO_WRITERS = re.compile(r"^Writers:\s*none\b", re.IGNORECASE | re.MULTILINE)


def writer_startable(text: str) -> bool:
    """Whether a writer can do any open box of this plan text: False under a `Writers: none` header or when every open box is marked lead- or operator-only."""
    if _NO_WRITERS.search(text or ""):
        return False
    opened = [ln for ln in (text or "").splitlines() if _OPEN_BOX.match(ln)]
    return any(not _LEAD_BOX.search(ln) for ln in opened)


def next_turbo(
    root: str,
    live_plans,
    open_slots: int,
    rev: str = "",
    in_set=(),
    ceiling: bool = True,
) -> list[str]:
    """The plans the turbo loop names to start now (agent/plans/PLAN-stop-hook-turbo.md D5), at most `open_slots` of them, [] when turbo is off at `rev`.

    Walked in `queue` order (Promoted, then Generated). An entry is eligible when it exists, has an open box, is not held (`wl_planenforce.plan_held`, the rule P-A1 keeps off the clock), is not in `in_set` (the PR's plan set), is not served by a live writer already, is not picked already, and has an open box a writer can do (`writer_startable`). The pick is the entry's deepest unfinished prerequisite when it has one (the first member of its `pr_plan_set`, as `wl_prscope.next_queued` does), and an entry with a held prerequisite is skipped, since nothing of it can start. Each pick must pass `wl_planconc.spawn_verdict` against `live_plans` (the plans live writers serve, paths or basenames) plus the picks before it, so an exclusive plan is never paired with a live writer's plan and two picks never claim one file.

    A ` -- solo` entry (D11) is eligible only for an empty PR with no pick before it, and then it is the only pick; a PR whose plan set holds a solo plan takes no further plan."""
    slots = int(open_slots or 0)
    if slots <= 0:
        return []
    settings, _problems = settings_at(root, rev)
    if not settings.turbo:
        return []
    text = _read(root, QUEUE_REL, rev)
    if text is None:
        return []
    try:
        pq = _planqueue()
        import wl_planconc  # noqa: PLC0415 -- the concurrency rules the spawn guard applies
        import wl_planenforce  # noqa: PLC0415 -- the held rule P-A1 shares
    except ImportError:
        return []
    solos = pq.solo_plans(text)
    taken = {str(p) for p in in_set or ()}
    if taken & solos:
        return []
    live = {_base(p) for p in live_plans or ()}
    # THE PARALLELISM CEILING (`plan_concurrency`): the PR's own unfinished plans and the plans live writers serve already count against it, so a free writer slot is not by itself a reason to open another plan.
    if ceiling:
        inflight = {_base(p) for p in taken if open_boxes(root, p, rev)[0] > 0} | live
        slots = min(slots, plan_concurrency(settings) - len(inflight))
        if slots <= 0:
            return []
    picks: list[str] = []

    def held(rel: str) -> bool:
        return wl_planenforce.plan_held(_read(root, rel, rev) or "")

    def compatible(rel: str) -> bool:
        busy = {b: ["live"] for b in live | {_base(p) for p in picks}}
        try:
            verdict = wl_planconc.spawn_verdict(
                {_base(rel)}, busy, lambda b: wl_planconc.plan_x(root, b)
            )
        except Exception:  # noqa: BLE001 -- a verdict that cannot be reached is no pick
            return False
        return verdict.allow

    for rel in pq.ordered(text):
        if len(picks) >= slots:
            break
        if rel in taken or rel in picks or _read(root, rel, rev) is None:
            continue
        opened, _done, why = open_boxes(root, rel, rev)
        if why or opened <= 0:
            continue
        members, problems = pr_plan_set(root, "Plan: %s" % rel, rev)
        if problems:
            continue
        chain = [m for m in members if m not in taken and m not in picks]
        if not chain or any(held(m) for m in chain):
            continue
        pick = chain[0]
        if not writer_startable(_read(root, pick, rev) or ""):
            continue
        if _base(pick) in live:
            # A live writer already serves it: it is started, not a plan to start.
            continue
        solo = rel in solos or pick in solos
        if solo and (taken or picks):
            continue
        if not compatible(pick):
            continue
        picks.append(pick)
        if solo:
            break
    return picks


TURBO_NAMED_SUFFIX = ".turbo-named.json"


def _named_path(root: str) -> pathlib.Path:
    """The record of the plans the Stop hook named under turbo, beside the worklist store (`wl_core.worklist_for`), so it is per checkout and never committed."""
    syspath.on_sys_path(STOP_DIR)
    import wl_core  # noqa: PLC0415 -- the store's own location rule

    return wl_core.worklist_for(root).with_suffix(TURBO_NAMED_SUFFIX)


def record_turbo_named(root: str, branch: str, plans) -> None:
    """Add `plans` to the turbo names recorded for `branch` (D5: a plan joins the PR when the hook names it; `refresh_pr_body` appends the record to the body's `Plan:` line on the next push). Written atomically; a failure is silent, since the hook names the plan again on the next stop."""
    import json  # noqa: PLC0415

    if not branch or not plans:
        return
    try:
        path = _named_path(root)
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = {}
        if not isinstance(doc, dict):
            doc = {}
        have = [p for p in doc.get(branch) or [] if isinstance(p, str)]
        for rel in plans:
            if rel and rel not in have:
                have.append(rel)
        doc[branch] = have
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 -- a record that cannot be written is named again next stop
        pass


def turbo_named(root: str, branch: str) -> list[str]:
    """The plans the Stop hook named under turbo for `branch`, in naming order; [] when none or unreadable."""
    import json  # noqa: PLC0415

    try:
        doc = json.loads(_named_path(root).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- nothing recorded reads as nothing named
        return []
    got = doc.get(branch) if isinstance(doc, dict) else None
    return [p for p in got or [] if isinstance(p, str) and PLAN_PATH.match(p)]


def plan_merge_refusal(root: str, pr_body: str | None, rev: str = "") -> str:
    """ "" when the PR may merge on its plans, else the reason it may not (agent/plans/PLAN-stop-hook-turbo.md D6).

    Admitted: the body carries an `Operational-Reason:` line; or it names exactly one plan (`Plan: agent/plans/PLAN-<slug>.md`) whose boxes are all ticked at `rev` ("" = the working tree under `root`); or, with `turbo: on` in agent/plans/QUEUE.md AT `rev` (the merge lands that copy, so a working-tree flip admits nothing), it names any number of plans and every one of them has its boxes ticked. Every unfinished prerequisite in the plan set's closure is checked too. No minimum batch is enforced here.
    """
    if not isinstance(pr_body, str):
        return "the PR body could not be read, so its plan cannot be checked"
    if has_operational_reason(pr_body):
        return ""
    plans = body_plans(pr_body)
    if not plans:
        return "the PR body names no plan (`Plan: agent/plans/PLAN-<slug>.md`) and carries no `Operational-Reason:` line"
    if len(plans) > 1:
        settings, _problems = settings_at(root, rev)
        if not settings.turbo:
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
    "TURBO_NAMED_SUFFIX",
    "batch_size",
    "body_plans",
    "exists_at",
    "has_operational_reason",
    "next_turbo",
    "open_boxes",
    "plan_concurrency",
    "plan_merge_refusal",
    "pr_plan_set",
    "pushed_tip",
    "queue",
    "queue_at",
    "queue_head",
    "queue_head_at",
    "record_turbo_named",
    "settings_at",
    "turbo_named",
    "with_plan_line",
    "writer_startable",
]
