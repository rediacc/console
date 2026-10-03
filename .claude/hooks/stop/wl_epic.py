"""Epics: a label over N worklist items, for PR structure and per-epic review.

WHY A SIDECAR AND NOT AN EVENT KIND. `compact()` in wl_store.py rewrites the event log down to the minimal item-reproducing set (md, add, lease), so a novel event kind there is SILENTLY DESTROYED. `record_intent` already learned this and says so at its own definition; `.intents` is the precedent this follows. An epic that vanished on the next compact would take a
PR's whole structure with it, and the failure would look like an empty section rather than an error.

WHY EPICS ARE NOT WORKLIST ITEMS. `wl_planfid.is_umbrella()` actively refuses an item that stands for several tasks ("Waves B-D", "phases 1 through 3"), because one item covering many tasks is how work goes untracked. An epic is a LABEL OVER items, never an item: the items stay individually tracked, ticked and evidenced, and the epic only groups them for rendering and review.

WHAT AN EPIC IS FOR. Two consumers, and both need the same grouping:
  1. the PR body, which gets one section per epic so a reader can see which
     change belongs to which task;
  2. the review, which runs once per epic against only that epic's commits, so a
     big-bang PR cannot starve one task's review by crowding it out.

IDS ARE NOT FIXED WIDTH. Worklist item ids are 8 hex from the CLI and 12 hex when migrated from the old markdown. Never parse assuming a width.
"""

import json
import os
import pathlib

import wl_core as C
import wl_store as S

EPIC_MAX_CHARS = 200
EPIC_MAX_COVERS = 64


def epics_path():
    """The DURABLE epic sidecar, `agent/worklist/epics.jsonl`.

    IT WAS `worklist.with_suffix(".epics")` AND THAT WAS THE WHOLE BUG. W12 P3.1a is recorded as "the TMPDIR sidecar moved into agent/worklist/" and the code read as if it had, because the durable-looking derivation hid where the argument actually points: `worklist` is the LEGACY markdown mirror, which lives at $TMPDIR/claude-worklist/<slug>.md. So the epics rode along in /tmp, and
    a /tmp clear between branches deleted them.

    Measured 2026-09-06, and it was not hypothetical. Eighteen commits on branch 0906-1 carry `PR-TASK: 24c98380`, an epic whose definition was gone: `check:ci-pr-task-trailers` reported them as naming no epic in the snapshot, which means the review would have covered none of them. The title survived only because a PREVIOUS branch's rendered snapshot, agent/pr/0903-1.md, is
    tracked. A generated view outliving its source is not a recovery plan.

    Repo-scoped, not per-session: an epic is a label many sessions attach items to, and it always behaved that way (one file, whoever wrote it). The `worklist` argument is GONE rather than kept and ignored, because a parameter nothing reads is the next reader's false lead about where this resolves from.
    """
    return S.store_dir() / "epics.jsonl"


def _new_epic_id(existing):
    """Short, collision-checked. Same shape as a CLI item id, 8 hex."""
    for _ in range(64):
        cand = os.urandom(4).hex()
        if cand not in existing:
            return cand
    raise RuntimeError("could not mint a distinct epic id")


PLAN_DIR = "agent/plans/"


def plan_rel_problem(rel, root=None):
    """Why `rel` cannot be an epic's plan, or "" when it can.

    The plan is how the Stop hook scopes items to the live PR (agent/plans/PLAN-stop-hook-one-plan-scope.md, Design 3), so a typo here would silently attach an epic to no plan at all and queue every item under it. A rel must be a repo-relative `agent/plans/....md` that exists, and must not climb out of `agent/plans/`.
    """
    rel = str(rel or "")
    if not rel.startswith(PLAN_DIR) or not rel.endswith(".md"):
        return "a plan is a repo-relative %s<name>.md path, not %r" % (PLAN_DIR, rel)
    if root is None:
        root = C.project_root(C.project_start())
    base = (pathlib.Path(root) / PLAN_DIR).resolve()
    target = (pathlib.Path(root) / rel).resolve()
    if base not in target.parents:
        return "%r leaves %s" % (rel, PLAN_DIR)
    if not target.is_file():
        return "no plan file %s under %s" % (rel, root)
    return ""


def record_epic(me, epic_id, title, covers, order=None, plan=None):
    """Append one epic record. Append-only, like every sidecar here.

    `plan` is written only when given: `load_epics` merges non-None fields later-wins, so a record that omits it (a later `add`) keeps the plan an earlier record set.
    """
    rec = {
        "at": C.stamp_now(),
        "by": (me or "")[:8],
        "id": epic_id,
        "title": (title or "")[:EPIC_MAX_CHARS],
        "covers": sorted({c for c in (covers or []) if c})[:EPIC_MAX_COVERS],
        "order": order,
    }
    if plan:
        rec["plan"] = str(plan)
    S._append_lines(epics_path(), str(epics_path()) + ".lock", [rec])


def load_epics():
    """{epic_id: record}, later lines winning, ordered by `order` then first-seen.

    A torn or malformed line is SKIPPED, never fatal: the same rule the event reader follows, because a crash mid-append must not make the whole file unreadable.
    """
    p = epics_path()
    if not p.exists():
        return {}
    out, seen = {}, []
    try:
        rows = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    for line in rows:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        eid = str(rec.get("id") or "")
        if not eid:
            continue
        if eid not in out:
            seen.append(eid)
        prev = out.get(eid) or {}
        merged = dict(prev)
        merged.update({k: v for k, v in rec.items() if v is not None})
        # covers ACCUMULATE across records: `--epic add` is additive, so a later line naming one more item must not drop the ones named before it.
        merged["covers"] = sorted(set(prev.get("covers") or []) | set(rec.get("covers") or []))
        out[eid] = merged
    ordered = sorted(
        out.values(),
        key=lambda r: (
            r.get("order") if r.get("order") is not None else 10**6,
            seen.index(r["id"]),
        ),
    )
    return {r["id"]: r for r in ordered}


def new_epic(me, title, order=None, plan=None):
    existing = set(load_epics())
    eid = _new_epic_id(existing)
    record_epic(me, eid, title, [], order, plan=plan)
    return eid


def set_plan(me, epic_id, rel):
    """Give an existing epic its plan (later-wins). Refuses an unknown epic by returning None; the caller validates `rel` first."""
    epics = load_epics()
    if epic_id not in epics:
        return None
    rec = epics[epic_id]
    record_epic(me, epic_id, rec.get("title"), [], rec.get("order"), plan=rel)
    return epic_id


def plan_epics(rel):
    """Every item id covered by an epic whose `plan` is `rel`.

    Titles are NEVER parsed (clean break, Design 3): an epic whose title names a plan but which carries no `plan` field belongs to no plan until `--epic <me> plan` gives it one.
    """
    out: set[str] = set()
    for rec in load_epics().values():
        if rec.get("plan") == rel:
            out.update(rec.get("covers") or [])
    return out


def add_to_epic(me, epic_id, item_ids):
    """Attach items to an existing epic. Refuses an unknown epic."""
    epics = load_epics()
    if epic_id not in epics:
        return None
    record_epic(me, epic_id, epics[epic_id].get("title"), item_ids, epics[epic_id].get("order"))
    return epic_id


def neutralize(text):
    """Defang HTML comment delimiters in text destined for a PR body.

    THIS IS NOT COSMETIC. The PR body carries managed blocks delimited by HTML comments, and an item whose own text contains `-->` would TERMINATE the block early, silently truncating every section after it. Found immediately: the worklist item tracking this very feature had `<!-- worklist-epics:begin/end -->` in its title, because that is what the task is called.

    Zero-width-space between the characters keeps the text readable to a human
    while making it inert to an HTML parser.
    """
    return (text or "").replace("<!--", "<\u200b!--").replace("-->", "--\u200b>")


def render(fold, heading="###"):
    """Markdown: one section per epic, its items beneath.

    Uses wl_store.brief_text, the v14 display identity (what the item FIRST said plus its LATEST note), never rec["text"] which accumulates every update note forever and would put twenty concatenated lines into a PR body.
    """
    epics = load_epics()
    items = {r["id"]: r for r in fold.items}
    lines, claimed = [], set()
    for eid, rec in epics.items():
        lines.append("%s %s" % (heading, neutralize(rec.get("title")) or "(untitled)"))
        lines.append("")
        lines.append("`PR-TASK: %s`" % eid)
        lines.append("")
        covered = [i for i in (rec.get("covers") or []) if i in items]
        if not covered:
            lines.append("_no tracked items yet_")
        for iid in covered:
            claimed.add(iid)
            r = items[iid]
            lines.append(
                "- [%s] `#%s` %s" % (r.get("state", " "), iid, neutralize(S.brief_text(r, cap=200)))
            )
        lines.append("")
    # An item in no epic is REPORTED, never hidden: silence here would be indistinguishable from having no such work.
    orphans = [r for r in fold.items if r["id"] not in claimed and r.get("state") != "x"]
    if orphans:
        lines.append("%s Not in any epic" % heading)
        lines.append("")
        lines.extend(
            "- [%s] `#%s` %s" % (r.get("state", " "), r["id"], neutralize(S.brief_text(r, cap=200)))
            for r in orphans
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
