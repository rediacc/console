# Prompt: execute the backup-storage program

Your mission: implement the Rediacc-native chunk-store backup system as specified in
`docs/backup-storage/README.md`. Read its read order first (01 context, 02 design,
03 implementation map, 04 testing, 05 docs/decommission, 06 execution guide); the
design decisions are made and scored, so build, do not re-debate.

Validate, do not believe: every file:line in those docs is a hypothesis to re-verify
against the live tree before you build on it; run the real thing and read stdout and
stderr separately; plant a control before trusting any zero or any green.

Ask the README's operator decision points EARLY, in one round, before wave 1; park
deferrals as `- [?]` items with DEFAULTs.

Staffing: Opus is the default for coding sub-agents. Fable for the challenging
pieces (pkg/chunkstore, grant signing + ledger transactionality) AND for planning
agents. Sonnet for all translation/naturalization. At most 2 concurrent writers with
disjoint file ownership stated verbatim in every prompt; investigation agents fan
out freely; spot-check every report against the artifacts.

Program state (durable, survives compaction and reboots):
`~/.claude/projects/-home-muhammed-monorepo-console/programs/backup-storage/`
with `MANIFEST.md` (update at every phase boundary), `reports/` (every
writing/planning agent names its report `reports/<phase>-<agent>.md`), and
`checkpoints/` (periodic uncommitted-tree patches).

Checklist and worklist (fail-closed): the program checklist is
`docs/backup-storage/CHECKLIST.md`. At session start seed the shared worklist (path
via `.claude/hooks/stop/worklist.py --path`) with one item per unfinished wave:
`worklist.py --add <me> 'cl:backup-storage/<wN> <wave title>'`. The Stop hook blocks
while any wave is neither ticked in the checklist nor covered by such an item. Tick
a `wN` only after its store item is ticked with probed evidence; when all waves are
ticked, set the checklist `Status: done`.

Everything stays local and uncommitted: no commit, branch, push, or PR unless the
operator asks in-task; never `git checkout/restore/stash/clean`; repair forward.
Testing is a first-class deliverable: the drill's `--selftest` and the
corruption-injection control must be able to fire, and local proof precedes any
cloud probe. NO em dashes in any authored text, in any language.

Definition of done: every wave ticked with evidence; drill and battery green with
controls proven; quota enforced end-to-end live; a cross-machine and a
point-in-time restore byte-verified; hostinger migrated and OneDrive decommissioned
on its date; the 01 findings ledger cleared; docs and 12-locale translations
shipped; `docs/backup-storage/CHECKLIST.md` at Status: done.
