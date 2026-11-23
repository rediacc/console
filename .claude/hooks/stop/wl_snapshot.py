#!/usr/bin/env python3
"""wl_snapshot: fold finished sessions' worklist logs into one snapshot, so the per-stop read skips them.

    python3 .claude/hooks/stop/wl_snapshot.py --plan     list the finished logs and the bytes a fold would take off the per-stop read
    python3 .claude/hooks/stop/wl_snapshot.py --write    fold them (wl_store.compact_store) when at least one qualifies; otherwise change nothing

agent/plans/PLAN-tooling-code-reduction.md CR9, design D7. Every Stop reads and folds every file in agent/worklist/ (12 MB on 2026-11-23, 9 MB of it one long session). A session whose newest event is older than WORKLIST_DEAD_HOURS (24) and whose liveness is not "live" cannot append again, so its log only has to be READ once: `--write` folds the whole store (the fold is global, an item one session added and another ticked only folds correctly with every file) into the compactor's own file and unlinks the finished logs. The next Stop then opens the snapshot instead of them.

THE SELECTION IS wl_store.compact_store's, spelled out here so `--plan` can print it without writing; test_wl_snapshot.py runs both on one store and asserts they agree, so the two cannot drift. epics.jsonl is a sidecar, not a writer's event log, and is never selected (compact_store used to unlink it: fixed in the commit that added this module).

`--write` with nothing finished is a no-op that says so: compact_store rewrites the compactor's own file every call, which a Stop must not pay for nothing.
"""

from __future__ import annotations

import os
import pathlib
import sys

import wl_core as C
import wl_store as S

SIDECARS = frozenset({"epics"})


def finished_logs(worklist, root=None, me=None, projects_dir=None):
    """[(path, bytes, verdict)] of the store files compact_store would clear because their writer is finished, the caller's own file excluded."""
    if root is None:
        root = C.project_root(C.project_start())
    me8 = S.agent_session_slug((me or C.resolve_session_id() or "compact")[:8])
    events = S._read_events(worklist, root)
    dead_h = float(os.environ.get("WORKLIST_DEAD_HOURS", "24"))
    out = []
    for f in sorted(S.store_dir(root).glob("*.jsonl")):
        writer = f.stem
        if writer in SIDECARS or writer == me8 or writer.startswith("_"):
            continue
        verdict, _why = S.session_liveness(worklist, writer, projects_dir, events)
        newest = max(
            (str(e.get("at") or "") for e in events if str(e.get("by") or "")[:8] == writer),
            default="",
        )
        when = C.parse_stamp(newest) if newest else None
        old_enough = not newest or (
            when is not None and (C.utcnow() - when).total_seconds() / 3600.0 >= dead_h
        )
        if verdict in ("idle", "remote", "unknown") and old_enough:
            out.append((f, f.stat().st_size, verdict))
    return out


def main(argv, worklist=None, root=None, me=None, projects_dir=None):
    if argv not in (["--plan"], ["--write"]):
        print(__doc__.split("\n\n", 1)[0], file=sys.stderr)
        return 2
    if root is None:
        root = C.project_root(C.project_start())
    if worklist is None:
        worklist = C.worklist_for(C.project_start())
    found = finished_logs(worklist, root, me, projects_dir)
    total = sum(n for _p, n, _v in found)
    for path, size, verdict in found:
        print("  %s  %d bytes  writer %s" % (pathlib.Path(path).name, size, verdict))
    print("finished logs: %d file(s), %d bytes off the per-stop read" % (len(found), total))
    if argv == ["--plan"]:
        return 0
    if not found:
        print("nothing to fold: no finished session log")
        return 0
    S.compact_store(worklist, root=root, me=me, projects_dir=projects_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
