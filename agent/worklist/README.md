# agent/worklist/ — the worklist event log, tracked

One append-only JSONL file per **writer** (`<session8>.jsonl`). This is the
store the Stop hook and `worklist.py` read; it lives here, in git, so open work
survives a machine switch. Before 2026-09-04 it lived in `TMPDIR` and did not.

**Never hand-edit these files.** Use the verbs (`worklist.py --add/--tick/
--update/--defer/--lease/--migrate`). They append one event under a lock, which
is what makes concurrent sessions safe; an editor does not.

**Per writer, not one shared file, on purpose.** Both sides of a merge append at
EOF, so one shared file would conflict on every concurrent append from two
branches. A session id exists in exactly one process, so each file here has
exactly one appender and two machines write disjoint paths.

**A conflict is resolved by UNION, never by picking a side.** Keep both halves,
delete the markers. The reader sorts every event by timestamp before folding, so
the union of two histories folds to the same state as one history. Dropping a
side silently loses whatever that machine tracked.

**Commit your own file by name**, alongside your `agent/<session>/STATE.md`. A
file that is never pushed is work the next machine will not see — which is the
whole failure this directory exists to prevent.

Locks, caches, transcripts, briefs and `.lastevent-*` remain per-machine runtime
state in `TMPDIR`; only the log moved. `worklist.py --path` still prints the
TMPDIR handle those sidecars hang off.
