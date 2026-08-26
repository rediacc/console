## SESSION 854ac1c6 2026-08-26T15:34:01Z

## Where things stand

Branch **`0826-2`** (cut from `main` at `1c006e53`). **NOTHING IS COMMITTED** — ~55 changed
files, all uncommitted. The operator approved landing it as ONE PR but has twice chosen
"keep going, cut later", most recently saying there is more they want first. **Do not
commit or open a PR until they say so.**

**RUN GATES IN THE DEVBOX, NOT ON THE HOST.** The host has no pyyaml, pip, aws or ruff, so
`check-workflow-gates.sh`, `check-ci-workflow-invariants.sh`, `check:ci-release-state` and
`check:ci-python-lint` all fail there for environment reasons. Use
`./run.sh devbox exec -- <gate>` (devbox has pyyaml 6.0.2 + `uvx`). `aws` is now in
`.devcontainer/Dockerfile:298` but needs an image rebuild.

**The v1.3.1 production defect is CLOSED** (remediated + code fix + T1-T4 gates).
`agent/PLAN-skip-release-gates-r2-manifest.md` is `Status: done`.

**Landed this session, all uncommitted and all locally green:**
- `ctx_budget.py` compaction-boundary bug; `ci-trace.py --run` (a branch rollup cannot see
  a workflow_dispatch run, so `--ref` false-greened a live release twice).
- skip_release threading; `assert-edge-tag-exists.sh` at `promote-stable.yml:55`;
  `mark-production.sh`; workflow renames `Release to Production` / `Release to Edge`.
- cd-v2's dead `skip_release` output and its ~9 permanently-true guards REMOVED
  (operator explicitly declined to veto). 9 jobs before/after, none lost.
- 10 drifted GitHub labels PATCHed live; `check-label-inventory.sh` compares
  description+color; new `check:ci-regions-sync` + `gate-test:regions-sync`.
- devbox: branch hostnames, `--default-folder` (VS Code was opening `/home/vscode`),
  `--telemetry-level off`, `devbox-autostart.sh`, `worktree create` starts it,
  `worktree remove` tears it down FIRST and aborts on failure, `prune` collects failures,
  `run.sh devbox url` + `--no-rehost` forwarding, `block-worktree-add.sh` catches the
  `run.sh worktree create` wrapper.
- Stop hook: `deferred_findings()` + `V_SWEEP_MOMENT`. Suite **802 passed / 0 failed**.

**REGIONS — investigated, deletion CONFIRMED SAFE, do not revert.** The operator said "I
don't remember that region feature" after approving it, so it was checked. `scripts/sign-regions.ts`
and the runtime-fetch path in `region-discovery.ts` are deleted. Origin: commit `7f2725bd`
/ PR #427, which added the signer with no caller; never wired, hidden because
`knip.jsonc:12` treats `scripts/*.ts` as entry points. The endpoint 404s on www, edge AND
eu (`SITE_URL` hardcoded at `packages/shared/src/config/defaults.ts:206`, no CLI override).
Decisively, the path was BROKEN: the signer predated `edgeDomain` (#429) and
`verifySignedRegions` does no shape validation, so a served manifest would have set
`accountServer = https://undefined`. Root `regions.json` is NOT dead — it is the live infra
registry for 6 workflows and 5 deploy scripts, and is untouched. The CLI region picker
still works exactly as before.

## Next action

1. **Ask the operator what they want next** — they said there is more before the PR is cut.
   Until they name it, there is no queued work; do NOT invent scope and do NOT commit.
2. If they say cut it: `git checkout -b` is unnecessary (already on `0826-2`); commit all
   ~55 files as ONE PR, then babysit CI. CI is the only thing that can validate the
   skip_release threading end to end, because a real `bump-none` merge is the only trigger.
3. Known-unfixed, deliberately: `${SITE_URL}/regions.json` stays a 404 (operator chose
   delete-over-revive); `verifySignedRegions` now has only test consumers (knip does not
   flag it today — checked).
4. A devbox recreate already happened and is verified (folderUri = /home/muhammed/console,
   all three routes live). RustFS failed once on that recreate — a ghost container held
   :9100; `account dev` degrades to config-storage-disabled and continues.
