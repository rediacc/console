# PLAN: the two baked VM image checks left open when PLAN-ci-prebaked-vm-images closed

Status: approved -- the lead packaged operator-ruled work 2026-11-09 (CB5 of PLAN-plan-compaction-bindings.md): ruling #c3a46b36 moved the B5 live check and the B7 measurement out of the closed plan to post-merge worklist items, and they stay wanted
Depends-On: no-dep -- the bake workflow, the E2E Workers consumption and the harness assertion all landed with the closed plan (a312694e9d); these boxes only read PR runs and touch the GHCR retention list
Owner: d778be9d
Worklist: #c8f185c8, #86a94e05
First-Seen: 2026-09-29
Updated: 2026-11-09
Priority: P3 -- a measurement and a live check of a speed-up that already runs; no correctness fix rides on them
Concurrency: parallel -- one box reads CI runs, the other edits only the housekeeping retention list and this plan
Live-Proof: none -- CI tooling only: `surfaces.owns_surfaces` over this Owns list returns no surface, so no live receipt is owed; ruling #11c34df3 (the operator request behind the surface map, closed with its answers)
Owns: agent/plans/PLAN-ci-vm-image-followups.md, .ci/rediacc_ci/housekeeping/cleanup_versions.py, .ci/rediacc_ci/tests/**

## Context

PLAN-ci-prebaked-vm-images.md (now in the done folder) closed under ruling #c3a46b36 with B5 [25afa53a] and B7 [0352e5e4] open: both need PR runs after the bake was on main, which it now is (`.github/workflows/ci-vm-bake.yml`, `VM_BAKE: 'on'` in `.github/workflows/ct-tests.yml`). Their worklist items carried them until this plan; the closed plan names this one under each box.

## Tasks

- [ ] V1 The closed bake plan's B5 live check: one PR run where 35 E2E Workers legs report a baked hit and every worker logs `[setup] pkg-calls 0`, the 5 shard-2 legs log full setup, and no baked leg saves the stock cache; control: a PR changing `private/renet/cmd/renet/setup_command.go` runs all 40 legs on stock. Accept: the run ids and the per-leg counts, read through `.ci/scripts/ci/ci-trace.py --job <id> --log` before the logs expire.
- [ ] V2 The closed bake plan's B7 measurement: 5 PR runs with baked images, per-distro leg duration and setup phases against B0 (run 36528227779), written here as a table with run ids; a net saving under 20 runner-min per run sets `vars.VM_BAKE=off`. Also add `ci-vm-bake` to `GHCR_PACKAGES` in `.ci/rediacc_ci/housekeeping/cleanup_versions.py` with a test, and audit the build journal the bake leaves (D2). Accept: the table, and the retention test under `.ci/rediacc_ci/tests` rc 0.
  Progress 2026-11-09 (d778be9d, re-read against the tree): the bake runs on main (`VM_BAKE: 'on'` at `.github/workflows/ct-tests.yml:429`), so V1 and V2 wait only on PR runs. The retention half of V2 is still open: `ci-vm-bake` is named in no line of `.ci/rediacc_ci/housekeeping/cleanup_versions.py`, so `GHCR_PACKAGES` does not yet carry it.
