"""wl_planindex: the PLAN CENSUS half of `agent/INDEX.md`, and the three-state
reader that lets SessionStart print the plans block from ONE file read.

THE DEFECT THIS CLOSES (W12 P1.7). `wl_checks.plans_block` is the SessionStart and PostCompact plans listing. It called `plan_records` and then `plan_box_census`, and BOTH of those open every `agent/PLAN-*.md` in full. Measured on this tree 2026-09-06, before this module existed:

    read_text calls = 166
    distinct files  = 83
    bytes read      = 2,018,737
    wall_ms         = 56.9
    listing lines   = 56

Two megabytes and 166 opens, on every session start, to print 56 lines. Nothing in those 2 MB reaches the session; only the per-plan status, line count and box counts do, and those are five small integers per plan.

WHAT THIS MODULE ADDS. A `## Plan census` section in `agent/INDEX.md` carrying exactly those integers, one row per plan, plus the plan's byte size. The hook reads that ONE file and stats the plan directory. No plan file is opened.

WHY THE CENSUS LIVES IN agent/INDEX.md AND NOT IN A SIDECAR. `agent/INDEX.md` is already compared for EQUALITY against its render by `check:ci-plan-record`'s R8, so a stale index is RED IN CI rather than quietly wrong. A sidecar nothing checks would be a cache that can lie, which is the shape this repo refuses. R8 was taught about the census in the same change that added this
module; without that edit the census section would red R8 as "disagrees with the records on disk", which is why the two land together and not one before the other.

------------------------------------------------------------------------------
THE FRESHNESS SIGNAL IS `stat`, AND ITS ONE BLIND SPOT IS NAMED HERE.

The whole point is to avoid reading the plans, so the hook's own check cannot hash them. It compares two things it can get from `os.stat`:

    1. the SET of plan paths on disk against the SET the census names, and
    2. each plan's byte size against the size the census recorded.

`st_mtime` is deliberately NOT part of it. A fresh clone stamps every file with checkout time, so an mtime comparison would report STALE forever after a clone and the fast path would never once be taken.

THE BLIND SPOT, named with its most likely instance rather than left abstract: an edit that rearranges a plan's bytes WITHOUT changing their count is invisible here, and `Status: draft` -> `Status: ready` is exactly that -- two five-letter words, one of this repo's commonest plan edits. So a plan can read `[draft]` in the SessionStart listing for a while after it went `ready`.

That is a real gap and it is accepted, because the hook's check is the CHEAP half of a two-part answer, not the whole one. The authoritative half is R8's byte-equality against a full re-read, which runs in CI on every branch and reds until the index is regenerated. The hook can be behind the truth between an edit and the next CI run; it cannot be wrong for longer than that, and the
listing is never SHORT or EMPTY as a result -- only, briefly, one field stale.

Closing it in the hook would mean opening the plans, which is the entire cost this module removes: reading ten header lines each still costs 83 opens.

------------------------------------------------------------------------------
THREE STATES, AND "EMPTY" IS NOT "ABSENT".

    CENSUS_FRESH   the census section is there and agrees with the directory
    CENSUS_STALE   it is there and DISAGREES, with the disagreement itemised
    CENSUS_ABSENT  there is no index, or the index carries no census section

Only the first one takes the fast path. The other two SAY SO, loudly, in the block the session reads, and then fall back to opening every plan -- the slow path, which is exactly what this module replaced and is kept working for that reason. A hook that printed a short list because its index was missing would be worse than the cost it saves, so a missing index degrades to
slow-and-correct and never to fast-and-blind.

`banner()` is what makes the states visible. It is prefixed `!!` and names the regeneration command, because a stale index that nobody regenerates is a permanent slow path nobody knows they are on.

------------------------------------------------------------------------------
WHAT THIS MODULE DOES NOT DO. It never writes `agent/INDEX.md`. `render_census` returns text and `check_plan_record.py --update` is the only writer, for the reason two writers of one generated file always give: they disagree, and the disagreement shows up as a gate that flaps. `--render` on the command line prints to stdout for a human or a test; it does not touch the tree.
"""

from __future__ import annotations

import os
import pathlib
import re

import wl_store as S

#: The section heading, and the grammar of one row. The FIRST cell is backticked
#: and the row has SIX cells, which is true of neither the record table nor the
#: edge table in the same file, so the three cannot be confused by a parser that
#: sees the whole document.
CENSUS_SECTION = "## Plan census"
CENSUS_ROW_RE = re.compile(
    r"^\|[ \t]*`([^`|]+)`[ \t]*\|[ \t]*([^|]*?)[ \t]*\|[ \t]*(\d+)[ \t]*"
    r"\|[ \t]*(\d+)[ \t]*\|[ \t]*(\d+)[ \t]*\|[ \t]*(\d+)[ \t]*\|[ \t]*$",
    re.MULTILINE,
)

#: The three answers `index_census` can give. See the module docstring: the
#: middle one is a RESULT and the last one is an admission that no search
#: happened, and collapsing them would let a blind index look like a clean one.
CENSUS_FRESH = "fresh"
CENSUS_STALE = "stale"
CENSUS_ABSENT = "absent"

#: How the session is told to fix a stale or absent index. Named once so the
#: banner and the module docstring cannot drift apart.
REGEN_CMD = "npm run check:ci-plan-record -- --update"

#: Same relative path `wl_planrec.INDEX_REL` names. Restated rather than imported
#: so this module has no import-time dependency on the record machinery: the hook
#: path must load it, and the record machinery pulls in git. `test-planindex.py`
#: asserts the two are equal, which is the only thing that could drift.
INDEX_REL = "agent/INDEX.md"
PLAN_GLOB = "PLAN-*.md"


def plan_dir(root) -> pathlib.Path:
    """`wl_store.agent_plan_dir`, not a second `root / "agent"`.

    Deferring to the store is what keeps this module and `wl_checks.plan_dir` pointed at the same directory: a hardcoded literal here would be a second definition of the tree layout, and the first symptom of it drifting would be a census that is permanently STALE because the two halves globbed different directories. `wl_store` imports nothing from this package, so there is no cycle
    to defer around.
    """
    return S.agent_plan_dir(root)


def plan_stats(root):
    """[(rel, size, mtime)] for every plan on disk. STAT ONLY, no file is read.

    This is the cheap half of the freshness check and it is also what restores the listing's ORDER: `wl_checks.plan_records` sorts newest-mtime-first and `plan_status_excerpt` then takes `live[0]` as "the newest live plan", so an index that dropped mtime would silently change which plan a compacted session gets excerpted. mtime is read here, from the same `stat` the size needs, and
    is deliberately NOT stored in the committed file (see the docstring).
    """
    d = plan_dir(root)
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob(PLAN_GLOB)):
        try:
            st = f.stat()
        except OSError:
            continue
        try:
            rel = str(f.relative_to(pathlib.Path(root)))
        except ValueError:
            rel = str(f)
        out.append((rel, st.st_size, st.st_mtime))
    return out


def census_rows(root, plan_records=None, plan_box_census=None):
    """[(rel, status, lines, open, ticked, size)] for every plan. THE SLOW PATH.

    This opens every plan, which is the cost the index exists to avoid. It has exactly two callers and both are correct: `check_plan_record.py --update`, which has to read them to write the index, and `plans_block`'s FALLBACK when the index is absent or stale.

    THE BOX COUNTING IS `wl_checks.plan_box_census`, NOT A SECOND PARSER. That
    function used to be what `plans_block` called, and lifting the numbers into
    the index took away its only production caller. Re-implementing the count here would have left it as dead code beside a fresh copy of itself, and the two would have drifted -- the exact shape where a plan reads `2 open` at SessionStart and `3 open` in the per-stop advisory. One reader, one answer.

    Note that `plan_box_census` returns NO entry for a plan carrying no boxes, so the `(0, 0)` default below is load-bearing: the census needs a row for every plan (the freshness check compares the path SET), while the totals must count only box-carrying ones. `_plan_census_summary` re-imposes that filter.

    `plan_records` and `plan_box_census` are injected rather than imported for the reason `wl_planrec.index_rows` gives about the same two functions: this module is driven by a CI gate, by a hook and by a test fixture, and none of the three should have to own `wl_checks`'s import to enumerate a directory. The defaults resolve them lazily, so a caller that has them already does not
    pay twice.
    """
    if plan_records is None or plan_box_census is None:
        # DEFERRED ON PURPOSE, and it is not a style slip. `wl_checks` imports THIS module, so a top-level `import wl_checks` here is a cycle that fails at hook-load time. Deferring also keeps the fast path honest: the fresh path never calls this function, so it never pays the import.
        import wl_checks  # noqa: PLC0415 -- wl_checks imports this module; top-level would cycle

        plan_records = plan_records or wl_checks.plan_records
        plan_box_census = plan_box_census or wl_checks.plan_box_census
    sizes = {rel: size for rel, size, _mt in plan_stats(root)}
    recs = plan_records(root)
    counts = plan_box_census(root, recs)[0]
    return [
        (
            rel,
            status,
            lines,
            counts.get(rel, (0, 0))[0],
            counts.get(rel, (0, 0))[1],
            sizes.get(rel, 0),
        )
        for rel, status, lines in recs
    ]


def render_census(rows):
    """The `## Plan census` section, or "" when there is nothing to census.

    "" matches `wl_planrec.render_index`'s own empty answer, and for the same reason it gives: a generated table with no rows is a committed document that says nothing. It also keeps R8's zero-record controls working unchanged -- a fixture with no plans renders no census, so `render_index(rows) + census` is `render_index(rows)`.

    Rows are sorted by PATH here, not by mtime, because this text is committed and mtime is not stable across a clone. The hook re-imposes mtime order from its own `stat` pass; see `plan_stats`.
    """
    if not rows:
        return ""
    body = "".join(
        "| `%s` | %s | %d | %d | %d | %d |\n" % (r[0], r[1], r[2], r[3], r[4], r[5])
        for r in sorted(rows)
    )
    n_boxed = sum(1 for r in rows if r[3] or r[4])
    return (
        "\n%s\n\n"
        "Every `agent/PLAN-*.md`, one row, so the SessionStart and PostCompact plans\n"
        "block can be printed from THIS file instead of opening all %d of them. The\n"
        "hook checks freshness with `stat` alone (path set plus byte size) and falls\n"
        "back to reading the plans, loudly, when the two disagree.\n\n"
        "| Plan | Status | lines | open | ticked | bytes |\n|---|---|---|---|---|---|\n%s"
        "\n%d plan(s), %d carrying boxes. Regenerate with `%s`.\n"
        % (CENSUS_SECTION, len(rows), body, len(rows), n_boxed, REGEN_CMD)
    )


def parse_census(text):
    """[(rel, status, lines, open, ticked, size)] read back out of index TEXT.

    Returns [] for text with no census section, which the caller must NOT read as "no plans": `index_census` distinguishes the two by asking whether the section heading is present at all, and that distinction is the whole of CENSUS_ABSENT.
    """
    cut = text.find(CENSUS_SECTION)
    if cut < 0:
        return []
    return [
        (
            m.group(1).strip(),
            m.group(2).strip(),
            int(m.group(3)),
            int(m.group(4)),
            int(m.group(5)),
            int(m.group(6)),
        )
        for m in CENSUS_ROW_RE.finditer(text[cut:])
    ]


def read_index(root):
    """(text, present). "" and False for an absent or unreadable index.

    `present` is not derivable from the text: an index that exists and is empty reads back as "" too, and the two must not be confused -- an empty index over zero records is R8's LEGAL state, while an absent one over a tree full of plans is the thing this module reports.
    """
    try:
        return (pathlib.Path(root) / INDEX_REL).read_text(encoding="utf-8", errors="replace"), True
    except OSError:
        return "", False


def census_diff(rows, stats):
    """(added, removed, resized) between the census and the directory.

    Three lists of relative paths, always in that order. `added` is on disk and not in the census, `removed` is the reverse, `resized` is in both with a different byte count. All three are empty exactly when the census is fresh, which is what makes this function the whole of the staleness verdict rather than an explanation bolted onto one.
    """
    have = {rel: size for rel, size, _mt in stats}
    want = {r[0]: r[5] for r in rows}
    added = sorted(set(have) - set(want))
    removed = sorted(set(want) - set(have))
    resized = sorted(p for p in set(have) & set(want) if have[p] != want[p])
    return added, removed, resized


def index_census(root, stats=None):
    """(rows, state, detail) -- the census, and whether it can be believed.

    `stats` is the `plan_stats` result when the caller already has it. It is not an optimisation for its own sake: `plans_block` needs the same list to restore mtime order, and computing it twice would stat 83 files twice on the FAST path, which is the path this whole module exists to keep cheap.

    `rows` is [] for every state except CENSUS_FRESH; a caller must not use the rows of a stale index, because a stale row is a confident wrong number and the fallback is cheap enough to always be right. `detail` is the `census_diff` triple for CENSUS_STALE and () otherwise.

    A directory with NO plans at all answers ([], CENSUS_FRESH, ()): there is nothing to index, the empty census agrees with the empty directory, and forcing a project without plans onto the fallback would make it pay a directory walk to be told nothing. That is the one case where [] rows and CENSUS_FRESH travel together.
    """
    if stats is None:
        stats = plan_stats(root)
    text, present = read_index(root)
    has_section = present and CENSUS_SECTION in text
    if not stats:
        return [], CENSUS_FRESH, ()
    if not has_section:
        return [], CENSUS_ABSENT, ()
    rows = parse_census(text)
    diff = census_diff(rows, stats)
    if any(diff):
        return [], CENSUS_STALE, diff
    return rows, CENSUS_FRESH, ()


def _names(paths, cap=4):
    """A capped, comma-joined path list. Capped because a stale index right after
    a compaction wave differs by dozens of files, and a banner that prints 33
    paths is a banner the reader scrolls past."""
    shown = ", ".join(paths[:cap])
    return shown + (" and %d more" % (len(paths) - cap) if len(paths) > cap else "")


def banner(state, detail, n_plans):
    """The loud line, or "" when the index was believed.

    LOUD IS THE REQUIREMENT, not a style. The failure this whole module could introduce is a session that reads a short or empty plans list and believes it, so every path that did NOT take the index says which state it was in, what the disagreement was, how much it cost, and the command that fixes it.
    """
    if state == CENSUS_FRESH:
        return ""
    cost = (
        "  Listing rebuilt the slow way, by opening all %d plan file(s).\n"
        "  Regenerate and commit the index: %s\n" % (n_plans, REGEN_CMD)
    )
    if state == CENSUS_ABSENT:
        return (
            "  !! PLAN INDEX ABSENT: %s has no `%s` section.\n" % (INDEX_REL, CENSUS_SECTION)
        ) + cost
    added, removed, resized = detail or ([], [], [])
    parts = []
    if added:
        parts.append("%d not in the index (%s)" % (len(added), _names(added)))
    if removed:
        parts.append("%d indexed but gone (%s)" % (len(removed), _names(removed)))
    if resized:
        parts.append("%d changed size (%s)" % (len(resized), _names(resized)))
    return (
        "  !! PLAN INDEX STALE: %s disagrees with agent/ -- %s.\n"
        % (INDEX_REL, "; ".join(parts) or "unparseable census")
    ) + cost


if __name__ == "__main__":  # pragma: no cover -- a human/test entry point only
    import sys

    ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or str(pathlib.Path(__file__).resolve().parents[3])
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    argv = sys.argv[1:]
    if argv[:1] == ["--render"]:
        sys.stdout.write(render_census(census_rows(ROOT)))
    elif argv[:1] == ["--check"]:
        rows, state, detail = index_census(ROOT)
        n = len(plan_stats(ROOT))
        sys.stderr.write(banner(state, detail, n))
        print("state=%s rows=%d plans=%d" % (state, len(rows), n))
        sys.exit(0 if state == CENSUS_FRESH else 1)
    else:
        sys.stderr.write("usage: wl_planindex.py --render | --check\n")
        sys.exit(2)
