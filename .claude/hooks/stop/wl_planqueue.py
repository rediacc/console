"""wl_planqueue: the format of `agent/plans/QUEUE.md` and the render of its generated half (operator rulings, /ask 2026-10-02, worklist #0f45b81d).

THE FILE HAS TWO LISTS. `## Promoted` is the operator's hand-ordered list: it comes first, in its own order, and no tool ever writes it. `## Generated` sits between GEN_BEGIN and GEN_END and is rendered here from the canonical plan order, so the loop always has a next plan even when nobody has promoted one. `rediacc_hooks.plan_gate.queue` reads Promoted, then Generated, through `entries`; this module is the one place that
knows the headings, the markers and the entry shape.

THE RENDER REPLACES ONLY THE MARKED BLOCK. Every byte outside GEN_BEGIN..GEN_END is copied through unchanged, which is how the Promoted list and the header prose survive every regeneration. A file without the markers gets a `## Generated` section appended, never a rewrite of what is already there.

THE ORDER IS `wl_planorder.plan_key`'s, over a tier split the ruling asked for: open plans, then `Status: held` plans, each tier sorted by (dependency-blocked, operator Priority, AI Priority), then by path. The path is the tie-break instead of the backlog's mtime because this file is compared for equality in a clean CI checkout, where every mtime is the checkout's.

THE SUBJECTS are live plans directly under agent/plans (Status not in `wl_planfile.FINISHED_STATES`, not `removed`, stubs excluded), TRACKED ONLY: the file is a committed render, so another session's untracked draft must not enter it (`wl_store.agent_plan_files(root, tracked_only=True)`, the rule 9100e89f0 set for agent/INDEX.md). The dependency graph drops the same untracked files, so a draft cannot move a tracked plan's rank either.

Reads no environment variable. Heavy imports are lazy so `plan_gate` can read the format on the post-push path without loading the plan graph.
"""

from __future__ import annotations

import pathlib
import re

QUEUE_REL = "agent/plans/QUEUE.md"
PROMOTED_HEADING = "## Promoted"
GENERATED_HEADING = "## Generated"
GEN_BEGIN = "<!-- queue:generated:begin -->"
GEN_END = "<!-- queue:generated:end -->"
# The tier after the open plans (operator ruling: held plans are listed, after every open one).
HELD_STATES = frozenset({"held"})

# A queue entry: a numbered list item whose whole text is one plan path, optionally followed by ` -- <note>`. Prose lines naming a plan are not entries.
ENTRY = re.compile(
    r"^[ \t]*\d+[.)][ \t]+`?(agent/plans/PLAN-[A-Za-z0-9._-]+\.md)`?(?:[ \t]+--[ \t].*)?[ \t]*$",
    re.MULTILINE,
)
_HEADING = re.compile(r"(?m)^## ")
_BLOCK = re.compile(
    r"(?ms)^%s[ \t]*$\n?(.*?)^%s[ \t]*$" % (re.escape(GEN_BEGIN), re.escape(GEN_END))
)


def promoted_text(text: str) -> str:
    """The body of the `## Promoted` section: from its heading to the next `## ` heading or the generated block, "" when there is no such heading."""
    m = re.search(r"(?m)^%s[ \t]*$" % re.escape(PROMOTED_HEADING), text)
    if not m:
        return ""
    rest = text[m.end() :]
    stops = [s.start() for s in (_HEADING.search(rest), re.search(re.escape(GEN_BEGIN), rest)) if s]
    return rest[: min(stops)] if stops else rest


def generated_text(text: str) -> str | None:
    """The text between the markers, None when the block is absent."""
    m = _BLOCK.search(text)
    return m.group(1) if m else None


def entries(text: str) -> tuple[list[str], list[str]]:
    """(promoted, generated) plan paths in file order. Numbered entries outside both sections are not read."""
    promoted = [m.group(1) for m in ENTRY.finditer(promoted_text(text))]
    generated = [m.group(1) for m in ENTRY.finditer(generated_text(text) or "")]
    return promoted, generated


def ordered(text: str) -> list[str]:
    """Promoted first, then Generated, each path once."""
    promoted, generated = entries(text)
    out: list[str] = []
    for rel in promoted + generated:
        if rel not in out:
            out.append(rel)
    return out


# ---------------------------------------------------------------- the render


def live_plans(root) -> list[tuple[str, str, tuple[int, int, int]]]:
    """[(rel, status, plan_key)] in queue order: open tier, then held tier, each by (blocked, op, ai, path)."""
    import wl_planconc as X  # noqa: PLC0415
    import wl_plandeps as D  # noqa: PLC0415 -- the graph is loaded only for a render
    import wl_planfile  # noqa: PLC0415
    import wl_store  # noqa: PLC0415

    root = pathlib.Path(root)
    tracked = {
        p.relative_to(root).as_posix() for p in wl_store.agent_plan_files(root, tracked_only=True)
    }
    untracked = {p.relative_to(root).as_posix() for p in wl_store.agent_plan_files(root)} - tracked
    full = D.Graph.load(root)
    graph = D.Graph(
        {r: t for r, t in full.texts.items() if r not in untracked}, full.index_text, root
    )
    ctx = X.order_ctx(graph)
    rows = []
    for rel, info in graph.plans.items():
        status = info.header.status
        if (
            rel not in tracked
            or info.folder != D.PLANS_DIR
            or info.stub
            or status in wl_planfile.FINISHED_STATES
            or status == D.REMOVED_STATUS
        ):
            continue
        rows.append((rel, status, ctx.plan_key(rel)))
    rows.sort(key=lambda r: (r[1] in HELD_STATES, *r[2], r[0]))
    return rows


def note(status: str, key: tuple[int, int, int]) -> str:
    """`P1 (operator), approved`, `P3, held`, `P- (no Priority), draft`, with `, dep-blocked` when a dependency is still open."""
    blocked, op, ai = key
    if op < 4:
        rank = "P%d (operator)" % op
    elif ai < 4:
        rank = "P%d" % ai
    else:
        rank = "P- (no Priority)"
    return "%s, %s%s" % (rank, status or "no Status", ", dep-blocked" if blocked else "")


def render_block(rows, exclude) -> str:
    """The numbered lines between the markers, Promoted entries left out."""
    keep = [r for r in rows if r[0] not in set(exclude)]
    if not keep:
        return "(no live plan outside Promoted)\n"
    return "".join(
        "%d. %s -- %s\n" % (i, rel, note(st, key)) for i, (rel, st, key) in enumerate(keep, 1)
    )


def render(text: str, rows) -> str:
    """`text` with its generated block replaced by the render over `rows`. Every byte outside the block is kept."""
    promoted, _gen = entries(text)
    block = "%s\n%s%s" % (GEN_BEGIN, render_block(rows, promoted), GEN_END)
    m = _BLOCK.search(text)
    if m:
        return text[: m.start()] + block + text[m.end() :]
    sep = "" if text.endswith("\n\n") or not text else ("\n" if text.endswith("\n") else "\n\n")
    return "%s%s%s\n\n%s\n" % (text, sep, GENERATED_HEADING, block)


SKELETON = (
    "# Plan queue\n\n"
    "`## Promoted` is hand-ordered and wins; `## Generated` is rendered between the markers.\n\n"
    "%s\n\n" % PROMOTED_HEADING
)


def want(root) -> tuple[str, str]:
    """(on-disk text, rendered text). An absent file renders from SKELETON."""
    path = pathlib.Path(root) / QUEUE_REL
    try:
        got = path.read_text(encoding="utf-8")
    except OSError:
        got = ""
    return got, render(got or SKELETON, live_plans(root))


def refresh(root) -> bool:
    """Rewrite the generated block of an EXISTING queue file; True when it changed. A root with no queue file is left without one (fixtures, other checkouts)."""
    path = pathlib.Path(root) / QUEUE_REL
    if not path.is_file():
        return False
    got, new = want(root)
    if got == new:
        return False
    import wl_planrec as R  # noqa: PLC0415 -- the one atomic writer

    R.write_atomic(path, new)
    return True


def problems(root, update: bool = False) -> list[str]:
    """The freshness check: [] when the file equals its render. `update` writes the render (creating the file from SKELETON when absent) instead of reporting."""
    got, new = want(root)
    if got == new:
        return []
    if update:
        import wl_planrec as R  # noqa: PLC0415

        R.write_atomic(pathlib.Path(root) / QUEUE_REL, new)
        print("✓ wrote %s" % QUEUE_REL)
        return []
    what = "is absent" if not got else "has a generated section that differs from the render"
    return [
        "%s %s (the plan order changed, or the section was edited by hand). Regenerate and commit it:\n"
        "      npm run check:ci-plan-record -- --update\n"
        "      git add %s" % (QUEUE_REL, what, QUEUE_REL)
    ]
