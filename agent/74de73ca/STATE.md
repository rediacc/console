## SESSION 74de73ca 2026-09-04T05:31:53Z

# Session 74de73ca -- state

Branch `0903-1`, PR #585, epic `24c98380`. The operator's live request is the BINDER.

## The binder: Steps 0, 1 and half of 2 are DONE

Goal: stop hand-writing the four registrations every gate needs (package.json key,
manifest entry, workflow step, and the silent one -- the JOB). Design:
generate-and-check with a `---- gate ----` header in each gate script. NOT a big-bang:
three tools regex `manifest.ts` as TEXT, so it must keep containing every entry.

- `daed53572` gate-spec.ts + surface.ts split out of manifest.ts (re-exports both).
- `74b926351` `scripts/lib/gate-header.ts` -- parses the header; derives id/run/needs.
- `666d409f3` `scripts/ci-runner/lanes.ts` -- lane capabilities DERIVED from the
  workflow.
- `9c9b1935d` `scripts/gate-bind.ts` `--check` (= `check:ci-gate-bind`).
- `5eea0af11` `--write` emits the workflow step into a `# >>> gate-bind` region.
  Round trip proven: write on a correct tree is byte-identical; a hand edit is caught
  by --check and repaired by --write.

`npm run gate:bind` is the write verb. ONE gate declares a header so far:
`.ci/scripts/quality/check_environment_names.py`.

## Next action

`--extract <id>` was drafted this turn and did NOT land (a patch assertion failed
before writing, so scripts/gate-bind.ts is unchanged and green). Re-do it:
read one manifest entry by id as TEXT, derive id/run from its script leaf, and REFUSE
with a field-by-field diff if extraction would CHANGE anything -- that refusal is the
whole safety property, because a drain that rewrites as it moves cannot tell a move
from an edit. Then `manifest.legacy.ts` frozen shrink-only, then drain the 129
gate-tests (they need no header: id, run and the shared battery step are convention).

## Facts not to re-derive

- **The tutorial-player failure was TRANSIENT.** `Quality / Packages` succeeded on run
  53a52e8ed with no www change; it had failed once on cef71b63. Item ticked.
- **gate-bind found a real mis-placement on its first run**: check:ci-environment-names
  was hand-registered in quality-code; its needs put it in quality-static.
- **lanes.ts committed the bug it prevents** before its controls existed: it matched
  `PyYAML`/`setup-go` anywhere, and quality-code MENTIONS both in comments while
  installing neither. Comment lines are skipped now.
- **The secret cutover is COMPLETE and ticked.** `DOCKERHUB_TOKEN` has zero reads, so
  deletion is optional hygiene needing operator powers. `APP_PRIVATE_KEY` and
  `CLOUDFLARE_API_TOKEN` must NOT be deleted -- live reads at `breakpoint.yml:238` and
  `watchdog-monitor.yml:139`, both deliberate.
- **Neither `gh run rerun` form clears a cancelled reusable-workflow CALLER.**

## Repo state

origin/0903-1 at `53a52e8ed`; THIRTEEN commits local and unpushed -- nothing rides an
old run, so push them. Tree clean, ci:quick 302/302. CI on 53a52e8ed had the watchdog
retrying `Quality / Code`; every other Quality job succeeded.

## Remaining

- Optional, operator-only: `gh secret delete DOCKERHUB_TOKEN --org rediacc`.
