# Review e2c4a3a7: fix(ci): enterprise remove refuses a stale export, export is owner-only and reports OS errors, audit precedes the state write

Commit: e2c4a3a73c3bc2de4bccce3ebb1c3fcd79127118
Repo: console
Branch: 1104-1
Parent: 3e438d01ddc33df38cd60b2d9fec2561d5dca7e1
Patch-Id: 3ca2ce24b4aec152f69d9f29c82aedf826bbbf11
Reviewed-At: 2026-11-09T17:31:32Z
Model: claude-haiku-5-5
Cost: $0.0069 USD, 1 call(s), 43.8s
Diff: 21197 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes remove/export/audit behaviour in the enterprise lifecycle tooling; refusals and file modes change for existing users, with no new capability.
Dropped: 0
Body-Sig: acb7a8ca5f2f4b93

## Findings

### e2c4a3a7.1 [high] .ci/rediacc_ci/enterprise/lifecycle.py:430
Anchor: in-diff
Claim: The CHECKED mark is written before any destructive step, so if a delete_data remove fails before deleting anything (e.g. the undeploy step), the mark persists; if the company then changes and remove is rerun, the mark matches exported_at, the stale check returns early, and rows written after the export are deleted unexported.
Resolution: fixed 0320431429a121eb32a03bcefa46c3c08fa37927 | d778be9d 2026-11-09T17:34:08Z

### e2c4a3a7.2 [medium] .ci/rediacc_ci/enterprise/lifecycle.py:9
Anchor: in-diff
Claim: The module docstring says every verb writes more than one row in separate statements, but list_companies and export write no rows at all, so the docstring states a wrong behaviour.
Resolution: fixed 7b8701ca90205de9b69cdfd34917added052c49e | d778be9d 2026-11-09T19:50:40Z
