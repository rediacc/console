# PLAN: npm 11 is the only npm, in console and in private/account, locally and in CI
Status: done -- implemented and verified 2026-09-24 (uncommitted on 0923-1, lands with PR #590); #587 closed.
First-Seen: 2026-09-24
Owner: d778be9d
Updated: 2026-09-24
Closes: rediacc/console#587 (the parent session closes it after review)

## Why

Operator, 2026-09-24: "maybe its time to upgrade https://github.com/rediacc/console/issues/587 and close the old issue ... including for private/account. So, full compatibility with npm 11 everywhere."

The estate ran two npms. npm 11 wrote the lockfiles (the devcontainer pins it, and `CANONICAL_NPM` in the lockfile gate names it) while every CI job installed with the npm 10 that `actions/setup-node` bundles with Node 22. `check:ci-lockfile` therefore resolved every lockfile under both majors, and it went red the moment an npm-11 regeneration pruned entries npm 10 still demands: measured today on this tree, `package-lock.json (npm@10 cannot resolve)` after the typescript-eslint 8.70.1 port, and `private/account/package-lock.json` carries 27 `vitest/node_modules/@esbuild/*` + `esbuild` entries that only npm 10 wants (vite 8 no longer depends on esbuild; npm 11 prunes the orphan).

## Where npm's version is decided today (measured)

| Site | npm today |
|---|---|
| `.github/actions/setup-workspace/action.yml:74` and 11 direct `actions/setup-node` steps in `cd-deploy-account.yml` (x2), `cd-deploy-worker.yml`, `cd-v2.yml`, `ci.yml` (x3), `ci-build-docker.yml` (x2), `cleanup-preview.yml`, `ct-tests.yml`, `housekeeping.yml` | Node 22's bundled npm 10 |
| `.devcontainer/Dockerfile:228` | `npm install -g npm@11`, unpinned minor |
| `Dockerfile` (server image, `account-builder` stage runs `npm ci` + `npm install`) | node:22-alpine's npm 10 |
| `workers/proxy/Dockerfile` (`npm ci`) | node:22-slim's npm 10 |
| `private/account/Dockerfile` (three stages) | npm 10 for `npm ci`, then `npm install -g npm@12.0.2` for the two `npm install` stages |
| `.ci/rediacc_ci/security/audit.py:172` | self-upgrades to a hard-coded `npm@11.17.0` before `npm audit signatures` |
| `.ci/rediacc_ci/quality/lockfile.py:114-117` | resolves under `npm@11` AND `npm@10` |
| `packageManager` / `devEngines` | absent in console and account; `engines` names node only |
| private/account | no setup-node of its own; its CI runs through console's workflows |

## Design

1. **One pin.** `NPM_VERSION=11.20.0` in `.devcontainer/toolchain.env`, beside `NODE_VERSION`. It meets that file's rule (a gate depends on it and several lanes install it). 11.20.0 is the newest 11.x and is past the 24 h `minimum-release-age` window.
2. **One CI entry point.** A composite `.github/actions/setup-node-npm` runs `actions/setup-node`, reads the pin through `.ci/scripts/lib/toolchain.sh` (`toolchain_pin_for npm`), runs `npm install -g "npm@${NPM_VERSION}"`, and fails unless `npm --version` then equals the pin. `setup-workspace` and all eleven direct sites call it; nothing else names `actions/setup-node`.
3. **Images.** The devcontainer installs `npm@${NPM_VERSION}` from the COPYed `toolchain.env`. The three Dockerfiles whose build context cannot reach `.devcontainer/` declare `ARG NPM_VERSION=<pin>` and run `npm install -g npm@${NPM_VERSION}` at the top of every stage that installs a project tree. private/account drops npm 12.0.2: npm 11.20.0 resolves its manifest cleanly (measured in a scratch replica of the `/app` + `/packages/shared` layout; npm 10.9.8 still crashes there with `Cannot read properties of null (reading 'edgesOut')`).
4. **The lockfile gate goes npm-11-only and grows two properties.**
   - Resolve: `npx -y npm@<pin> ci --dry-run --ignore-scripts`, once. The npm 10 probe is deleted.
   - Canonical form: a scratch mirror (the lockfile, its `package.json`, its `.npmrc`, every workspace and `file:` manifest the lockfile or `workspaces` names) is rewritten with `npx -y npm@<pin> install --package-lock-only --ignore-scripts`; any byte difference is a refusal naming the fix command. The committed file is never written.
   - CI npm: every `actions/setup-node` use lives only inside the composite; the composite installs and verifies the pin; `NPM_VERSION` is an exact 11.x; every Dockerfile stage (submodules included) that installs a project tree installs `npm@${NPM_VERSION}` first, and every `ARG NPM_VERSION=` equals the pin; the devcontainer installs it.
   - Discovery stops at `.venv` (a vendored gradio lockfile under `private/generative/.venv` was being linted as this repo's).
5. **`.npmrc` / `install:natives`.** Unchanged, and re-proved under npm 11: `check:ci-npmrc`, then `npm run install:natives` rebuilding ssh2, cpu-features and esbuild with `ignore-scripts=true` still in force.
6. **Lockfiles.** Regenerated with the pin: root, `workers/*`, and all three account lockfiles.
7. **Prose.** CLAUDE.md's 27-line section becomes a short "npm 11 only" statement; `docs/agent-reference/ci-gates.md`'s npm-10 drift row, `.claude/agents/pr-babysitter.md`, `.ci/lib/local-common.sh` and the Dockerfile comments stop describing npm 10 as CI's installer.

Rejected: `devEngines.packageManager` with `onFail: error`. Measured: npm 10.9.8 then refuses even `npm run`, and `quality-static` / `quality-branch` run `npm run check:*` on ubuntu-slim with no node setup at all, so the field would red those lanes for a property the gate already holds. `packageManager` + corepack: corepack is leaving Node's distribution, and it would still need a per-job enable step.

## Tasks

- [ ] Plan written
- [ ] `NPM_VERSION` pin in toolchain.env, toolchain.sh and `rediacc_ci.core.toolchain`
- [ ] Composite `.github/actions/setup-node-npm`; setup-workspace and eleven direct sites switched
- [ ] devcontainer, root, workers/proxy and private/account Dockerfiles install the pin
- [ ] audit.py reads the pin instead of hard-coding 11.17.0
- [ ] Lockfile gate: npm 11 only, canonical-form refusal, CI-npm property, `.venv` prune; selftest and pytest updated
- [ ] Planted defects: a bare setup-node step, a stale lockfile, a Dockerfile stage without the pin
- [ ] Lockfiles regenerated (console root, workers/*, account x3)
- [ ] CLAUDE.md, ci-gates.md, pr-babysitter.md, local-common.sh comments
- [ ] Verification recorded below
- [x] #587 closed by the parent session
    (ticked) 2026-09-24T05:41:03Z by d778be9d: closed https://github.com/rediacc/console/issues/587 after an independent rerun: check:ci-lockfile exit 0 across 10 lockfiles, check:ci-npmrc exit 0

## Verification

Measured 2026-09-24 on this tree, npm cache in the session scratchpad.

- `npm run check:ci-lockfile`: exit 0, "All 10 lockfile(s): supply-chain clean, resolvable by npm@11.20.0 and byte-identical to its rewrite; CI and every image install npm@11.20.0" (53 s).
- Planted, all three in one run, restored from a copy and confirmed with `sha256sum -c`: a bare `actions/setup-node` step in housekeeping.yml, the `npm@${NPM_VERSION}` line removed from workers/proxy/Dockerfile, and private/account/package-lock.json put back to its HEAD (npm 10) form. Exit 1, with `.github/workflows/housekeeping.yml:147: uses actions/setup-node directly`, `workers/proxy/Dockerfile:40: npm ci runs the base image's bundled npm`, and `private/account/package-lock.json ... npm@11.20.0 would rewrite 512 line(s)`.
- `check_lockfile.py --selftest`: 42 controls passed. pytest: test_quality_lockfile, test_security_audit, test_setup_tools, test_core_toolchain, the toolchain pin/sync tests and test_gate_python_control_plants all pass.
- `check:ci-npmrc` exit 0. `install:natives` under npm 11.20.0 in a scratch project with this `.npmrc` and the locked ssh2/cpu-features/esbuild: `npm install` built no native binding, then `npm run install:natives` produced `cpufeatures.node` and `sshcrypto.node`.
- private/account under npm 11.20.0: `npm ci --ignore-scripts --dry-run` exit 0 in the root, web and e2e.
- Workflow and wiring gates, all exit 0: ci-actionlint, ci-actions-allowlist, ci-docker-npm-pins, ci-gate-prerequisites, ci-gate-reachability-coverage, ci-host-toolchain-coverage, ci-parity, ci-toolchain-env-dockerfile-sync, ci-toolchain-pins, ci-workflow-env-provision, ci-workflow-gates, ci-workflow-invariants, ci-workflow-orphan-step-keys, ci-workflow-submodule-deps, ci-workflows.
- `cd packages/cli && npx tsc --noEmit -p tsconfig.json`: exit 0.

## Findings on the way

- npm 11 warns `Unknown project config "minimum-release-age". This will stop working in the next major version of npm` on every command. The key is read by this repo's own gates, not by npm, so an npm 12 move needs it out of `.npmrc` first.
- `npm run install:natives` in this checkout fails with `EACCES: permission denied, rmdir 'build/Release'`: `node_modules/cpu-features/build` is owned by root (built 2026-09-07 from a root container). Environmental; the scratch-project run above shows the npm 11 behaviour itself is correct.
