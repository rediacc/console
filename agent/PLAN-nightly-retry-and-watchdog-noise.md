# PLAN: nightly retry for failed runs, and the watchdog noise underneath it
Status: compacted
Owner: 854ac1c6
Full-Text-Blob: 4a9cbc2c50de489738800acfa12a87f853130c27
Record-Sig: be1d7534

## Why
The watchdog-monitor.yml workflow generates ~2,000 runs/month, almost all of which fail by design (to signal CI cancellation). This drowns a nightly retry sweeper in false positives and makes the run-cleanup job unreachable — it scans only the newest 1,000 runs and watchdog runs sit 18 days old, outside the 30-day retention window. The cleanup exits green while deleting zero runs, a vacuous success masquerading as completion.

## Outcome
Phases 1, 2, and 3a landed on branch 0826-1 (PR #576). Phase 1 adds per-workflow retention overrides so watchdog runs can be pruned on a 7-day schedule. Phase 2 installs a nightly retry job in housekeeping.yml that filters on failure + live head + non-watchdog paths + attempt cap. Phase 3a makes the watchdog's by-design failure legible with a step summary and annotation, rather than relying on a run-name that GitHub evaluates before the outcome exists. Phase 3b (exiting 0 instead of non-zero) was deliberately deferred pending a grep for consumers of the watchdog's exit code.

## Lessons
- GitHub evaluates `run-name` at workflow creation, before the run outcome exists — it cannot express a verdict decided mid-run. Step summaries and annotations are the earliest surface for legibility.
- A cleanup that deletes nothing is indistinguishable from a cleanup with nothing to delete unless an anti-vacuity gate fires when the scan window cannot reach the retention threshold.
- Per-workflow retention overrides are load-bearing for high-volume telemetry workflows; global page caps become a treadmill.
- Retry filters on live head + failure conclusion + non-telemetry path are all necessary; any one missing re-introduces false positives across hundreds of runs.
- A monitoring workflow that fails when working correctly poisons signal interpretation across the entire Actions tab and confuses retry sweepers — coordinate the exit code change with any downstream consumer.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T12:26:08Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: .ci/scripts/housekeeping/cleanup-versions.sh, .github/actions/app-token/action.yml
Gates: none
Why-Source: model
Read-History: `git show 4a9cbc2c50de489738800acfa12a87f853130c27` recovers the text; `git log --find-object=4a9cbc2c50de489738800acfa12a87f853130c27 --all` names the commit

## History
- 2026-09-20T12:26:08Z compacted by d778be9d from `done` (record-sig be1d7534)
