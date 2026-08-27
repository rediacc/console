"""Epics: a label over N worklist items, for PR structure and per-epic review.

WHY A SIDECAR AND NOT AN EVENT KIND. `compact()` in wl_store.py rewrites the
event log down to the minimal item-reproducing set (md, add, lease), so a novel
event kind there is SILENTLY DESTROYED. `record_intent` already learned this and
says so at its own definition; `.requests` and `.intents` are the precedents this
follows. An epic that vanished on the next compact would take a PR's whole
structure with it, and the failure would look like an empty section rather than
an error.

WHY EPICS ARE NOT WORKLIST ITEMS. `wl_planfid.is_umbrella()` actively refuses an
item that stands for several tasks ("Waves B-D", "phases 1 through 3"), because
one item covering many tasks is how work goes untracked. An epic is a LABEL OVER
items, never an item: the items stay individually tracked, ticked and evidenced,
and the epic only groups them for rendering and review.

WHAT AN EPIC IS FOR. Two consumers, and both need the same grouping:
  1. the PR body, which gets one section per epic so a reader can see which
     change belongs to which task;
  2. the review, which runs once per epic against only that epic's commits, so a
     big-bang PR cannot starve one task's review by crowding it out.

IDS ARE NOT FIXED WIDTH. Worklist item ids are 8 hex from the CLI and 12 hex when
migrated from the old markdown. Never parse assuming a width.
"""

import json
import os

import wl_core as C
import wl_store as S

EPIC_MAX_CHARS = 200
EPIC_MAX_COVERS = 64


def epics_path(worklist):
    return worklist.with_suffix(".epics")


def _new_epic_id(existing):
    """Short, collision-checked. Same shape as a CLI item id, 8 hex."""
    for _ in range(64):
        cand = os.urandom(4).hex()
        if cand not in existing:
            return cand
    raise RuntimeError("could not mint a distinct epic id")


def record_epic(worklist, me, epic_id, title, covers, order=None):
    """Append one epic record. Append-only, like every sidecar here."""
    S._append_lines(
        epics_path(worklist),
        str(epics_path(worklist)) + ".lock",
        [
            {
                "at": C.stamp_now(),
                "by": (me or "")[:8],
                "id": epic_id,
                "title": (title or "")[:EPIC_MAX_CHARS],
                "covers": sorted({c for c in (covers or []) if c})[:EPIC_MAX_COVERS],
                "order": order,
            }
        ],
    )


def load_epics(worklist):
    """{epic_id: record}, later lines winning, ordered by `order` then first-seen.

    A torn or malformed line is SKIPPED, never fatal: the same rule the event
    reader follows, because a crash mid-append must not make the whole file
    unreadable.
    """
    p = epics_path(worklist)
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
        # covers ACCUMULATE across records: `--epic add` is additive, so a later
        # line naming one more item must not drop the ones named before it.
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


def new_epic(worklist, me, title, order=None):
    existing = set(load_epics(worklist))
    eid = _new_epic_id(existing)
    record_epic(worklist, me, eid, title, [], order)
    return eid


def add_to_epic(worklist, me, epic_id, item_ids):
    """Attach items to an existing epic. Refuses an unknown epic."""
    epics = load_epics(worklist)
    if epic_id not in epics:
        return None
    record_epic(
        worklist, me, epic_id, epics[epic_id].get("title"), item_ids, epics[epic_id].get("order")
    )
    return epic_id


def neutralize(text):
    """Defang HTML comment delimiters in text destined for a PR body.

    THIS IS NOT COSMETIC. The PR body carries managed blocks delimited by HTML
    comments, and an item whose own text contains `-->` would TERMINATE the block
    early, silently truncating every section after it. Found immediately: the
    worklist item tracking this very feature had `<!-- worklist-epics:begin/end
    -->` in its title, because that is what the task is called.

    Zero-width-space between the characters keeps the text readable to a human
    while making it inert to an HTML parser.
    """
    return (text or "").replace("<!--", "<\u200b!--").replace("-->", "--\u200b>")


def render(worklist, fold, heading="###"):
    """Markdown: one section per epic, its items beneath.

    Uses wl_store.brief_text, the v14 display identity (what the item FIRST said
    plus its LATEST note), never rec["text"] which accumulates every update note
    forever and would put twenty concatenated lines into a PR body.
    """
    epics = load_epics(worklist)
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
    # An item in no epic is REPORTED, never hidden: silence here would be
    # indistinguishable from having no such work.
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
