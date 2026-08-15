# 06. Execution guide

Status: forward-looking, written 2026-08-09. The implementing session follows this
top to bottom.

## Before anything

1. Read README.md and 01 through 05 in order; re-verify any file:line you build on.
2. Ask the README's operator decision points in ONE early round (AskUserQuestion,
   no previews so the write-in box stays available); park deferred answers as
   `- [?]` worklist items with DEFAULTs.
3. Settle packaging with the operator: worktree/branch per repo, PRs vs uncommitted
   trees. Do not create a worktree unilaterally; ask (repo standing rule).
4. Seed the worklist (see Gates below) and the program-state MANIFEST.
5. Confirm `REDIACC_ALLOW_CLUSTER_OPS=*` and `REDIACC_ALLOW_GRAND_REPO=*` are in the
   launching environment (ancestry-verified; an in-session export is rejected).

## Spikes (cheap, before wave-1 code)

- S1 churn instrument: read-only `delta.Compare` sweeps on real repos at 5m/1h/24h;
  output decides cell size and cadence defaults. Runs on ops VMs with synthetic
  load plus, operator-permitting, the real machines.
- S2 R2 probes (operator leg, bench bucket): temp-cred local signing `actions`
  enforcement + TTL bounds; If-None-Match 412; one multipart sanity pass.
- S3 btrfs test tier: wire `-tags btrfs` into renet's test runner over a
  loop-mounted btrfs; the existing round-trip tests must pass BEFORE pkg/chunkstore
  builds on pkg/delta.
- S4 grant double: design the local grant implementation (memory/fs) alongside the
  real one so tier-1 tests exist from the first commit.

## Waves and ordering

Wave 0 (parallel with spikes): in-path defect fixes. Renet/CI writer: S3 wiring,
churn instrument, `.pull-` sweep, snapshot-lock no-op fix. Account writer: cron
seam revival (seven `[triggers]` + `scheduled` re-export), NUL byte, config size
cap + versions prune, stale wrangler orphan. CLI quick fixes: restore credential
inheritance + GUID guard, dead `--watch` flags, regenerate-hint text, duplicate
destination schema deletion. Everything here is small, local, and de-risks the
campaign.

Wave 1: two writers, disjoint submodules (renet engine; account control plane), per
03-implementation-map ownership lists. The LEAD alone regenerates the six contract
files after the Go FunctionDefs settle. Contracts between writers are additive
JSON; neither blocks the other.

Wave 2: two writers (CLI+shared schema; portal). Depends on wave 1's contract
regenerate and routes.

Wave 3: two writers (vitest+drill; e2e battery). The drill's `--selftest` and the
corruption-injection control are non-negotiable deliverables: a battery that cannot
fail is not a battery.

Wave 4: Opus writes all English (docs, cheat sheet, CLI strings, claims
reconciliation, CLAUDE.md, skills); THEN the Sonnet fleet naturalizes 12 locales
through the existing pipelines; hashes regenerated. Tutorial re-record only if
wave 2 changed the seven recorded commands. i18n-guardian supervises.

Wave 5: local drill green including selftest; e2e battery green in CI; bench cloud
leg green; parallel-run on hostinger; N verified restores (one cross-machine, one
point-in-time); deploy account -> renet -> CLI; update all rdc installs; enable per
machine via `rdc backup schedule` (content-hash flip); portal verified; OneDrive
read-only window; decommission per 05 checklists in one commit with all generated
artifacts; superseding notes on R5.

## Staffing

Opus default for coding sub-agents; Fable for pkg/chunkstore, the grant signing +
ledger transactionality, and all planning agents; Sonnet for every translation. Max
2 concurrent writers with disjoint file ownership stated verbatim in every prompt;
forbid `git checkout/restore/stash` and any regenerate/sync script in writer
prompts (the lead regenerates); spot-check every report against artifacts. A
watchdog cron (about 20 min) runs while waves are in flight. Every writing agent's
prompt names its report path under the program-state `reports/` dir.

## Gates

Local: `npm run ci` (manifest-driven; new check scripts need a GateSpec +
anti-vacuity registration), the wave-relevant gate chains listed in 03 and 05.
Worklist wiring (fail-closed): at session start seed one item per wave, tagged with
the session prefix and carrying the checklist token:
`worklist.py --add <me> 'cl:backup-storage/<wN> <wave title>'`. The Stop hook
blocks any stopping session while a wave is neither ticked in
docs/backup-storage/CHECKLIST.md nor covered by such an item. Tick a `wN` only
after the store item is ticked with probed evidence. `- [?]` deferrals carry
DEFAULTs; `- [>]` leases carry expiry + worker id and are renewed on wake. Update
MANIFEST.md at every phase boundary; drop periodic uncommitted-tree patches into
`checkpoints/` (a host reboot once destroyed a /tmp scratchpad).

## Wave-promotion preflight (mandatory, session-side; no source-tree gate applies)

Before ticking any wave or relaunching any writer, and always after a process
restart: (1) list the harness's running background task ids (the lease-warning
path prints them) and reconcile every `- [>]` lease's `worker:<id>` against that
list, re-leasing or finishing items whose worker is gone; (2) probe the writers'
file sets with absolute-timestamp mtimes (this box's find rejects relative
-newermt; see docs/agent/TRAPS.md "Session liveness"), because the agent roster
lies after a restart while writers stay alive; (3) only then promote, relaunch,
or tick. The 2026-08-10 duplicate-writer incident is the recorded cost of
skipping this.

## Definition of done

Every wave ticked with evidence; the drill and battery green with their planted
controls proven able to fire; quota visible and enforced end-to-end (mint-time
refusal observed live); a cross-machine and a point-in-time restore byte-verified
against source; hostinger migrated and OneDrive decommissioned on its date; the
findings ledger in 01 empty of unfixed items (each fixed, or operator-deferred as
`- [?]`, or carrying a named last-resort door); docs and translations shipped with
zero em dashes; CHECKLIST.md Status: done.
