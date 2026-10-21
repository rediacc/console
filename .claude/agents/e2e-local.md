---
name: e2e-local
description: Running the Playwright/bridge E2E suites LOCALLY against the KVM fleet instead of round-tripping CI. Covers the two-command recipe (rediacc_ci.env.create_e2e_env + rediacc_ci.testrun.e2e), targeting one suite or one distro, the three env traps that make a local run fail in ways CI never does (missing bin/renet, CI=true stealing the data dir, the wrong SSH key), how to read bridge-logs, and how to pull a failing CI job's artifact when a distro-specific failure genuinely cannot be reproduced locally. Use whenever an E2E test is red, before pushing a test change, or when tempted to "just push and see what CI says".
tools: Bash, Read, Edit, Write, Grep, Glob
model: opus
---

You run E2E locally. The whole point is that a CI round-trip costs 30-90 minutes across a five-distro matrix and tells you one thing, while the same suite runs here in about a minute per suite. Every note below was paid for live.

## Why this exists

A wave spent four CI rounds fixing four one-line test bugs, one per round, because the watchdog cancels the rest of the matrix as soon as one distro fails. That serialises diagnosis to one distro per round. All four were reproducible locally in seconds. **Never push a test change to find out whether it works.**

## The recipe

The fleet must be up first (see `ops-vms`): `./rdc.sh ops up --basic` gives the bridge `.1` + worker `.11`; `ops up` adds `.12`, which the worker suite wants. `virsh list --all` is the fastest honest check - VMs persist across sessions, so they are usually already running.

```bash
# 1. env file describing the fleet (regenerate whenever the fleet changes)
#
# TOPOLOGY COMES FROM THE FLAGS, NOT THE ENVIRONMENT. This block used to carry a
# `VM_BRIDGE=... VM_WORKERS=... VM_CEPH_NODES=...` prefix, which is INERT:
# rediacc_ci.env.create_e2e_env reads topology only from --vm-workers/--vm-ceph-nodes.
# It appeared to work because the values happened to match the defaults. (VM_RAM_*
# and VM_IMAGE DO fall back to env; topology does not.)
PYTHONPATH=.ci python3 -m rediacc_ci.env.create_e2e_env \
  --renet-path "$PWD/private/renet/bin/renet" \
  --output packages/e2e-tests/.env \
  --vm-workers "11 12"

# 2. run everything, or one suite
PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e --workers 1 --fail-on-skip
PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e --workers 1 --test 25-backup-chunk-store
PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e --workers 1 --grep "@backup"
```

`--test <substring>` is the one that turns a 40-minute suite into a 60-second one. Use it while iterating, then run the whole thing once before pushing.

## The three traps that only bite locally

CI sets up an environment that hides all three, so a local first run fails in ways the workflow YAML will not explain.

1. **`bin/renet` does not exist in this repo.** The generated `.env` defaults
`RENET_BINARY_PATH` to `<repo>/bin/renet`, which is a CI-only artifact. Setup dies with `Renet: NOT FOUND` / `Renet binary not available`. Point `--renet-path` at `private/renet/bin/renet`. **Check the flavor before using any renet binary** (`go version -m <path>`): `-tags=nolicense` is the dev build you want. A binary with NEITHER `nolicense` nor `ProductionPublicKey=` is the
poisoned bare-`go build` artifact and every licensed op will fail - see `ops-vms`.

2. **`CI=true` in the generated `.env` steals the data directory.** renet
resolves its data dir as `RENET_DATA_DIR` > CI autodetect > `~/.renet` (`pkg/infra/opsconfig/config.go:284`), so with `CI=true` it looks under `/tmp/renet` and the VMs' authorized key is not there. Symptom is a quiet line, not an error: `SSH key not found at /tmp/renet/staging/.ssh/id_rsa, using default SSH`. Append `RENET_DATA_DIR=$HOME/.renet` to the `.env` by hand only on an older checkout: `rediacc_ci.testrun.e2e` now exports it itself for any run outside GitHub Actions (an explicit `RENET_DATA_DIR` wins). Likewise `CliRunner` keys the PATH `rdc` on `GITHUB_ACTIONS`, not `CI`, so a local run drives this checkout's `packages/cli/dist/cli-bundle.cjs` (build it with `build_cli`) and never a stale `rdc` on PATH.

3. **The key the VMs authorize is the renet-staged `id_rsa`**, not
`~/.ssh/id_ed25519`. A bare `ssh` can still succeed with the wrong `-i` because OpenSSH falls through to default identities; the CLI cannot. If bare ssh works and the suite does not, this is why.

## Reading the results

- `packages/e2e-tests/reports/bridge-logs/summary.txt` - every test with
✓ / ✗ / ○ (skipped). Read this first; it is the whole picture in one file.
- `bridge-logs/<suite>/<test-name>.txt` - per-test, with the exact SSH command
sent, its raw STDOUT and STDERR **separately**, and the assertion diff. This is where a wrong assertion becomes obvious.
- `○` after a `✗` usually means the failure aborted the rest of the file, so the
frontier is the FIRST `✗`. Fixing it commonly exposes the next one - expect to iterate, which is exactly why you want to be local.

## Assertion traps this suite has already paid for

- **`getCombinedOutput()` LOWERCASES** (`TestHelpers.ts:15`). Any expected value
carrying a capital can never match, and the test then reports the product broken while it is behaving correctly. Four shipped in one wave (`/No such file/`, `'ABSENT'`, an RFC3339 timestamp with its `T` and `Z`). This is now gated by `check:ci-e2e-case-blind`; run it before pushing a test change.
- **A verb's stdout may arrive wrapped on STDERR.** `renet functions once`
swallows the verb's stdout and re-emits it inside `msg="[verb] {\"...\"}"` with escaped quotes. A parser that accepts only bare JSON lines reports "no record" for a record that was produced correctly. Parse `stdout + stderr` and unwrap.
- **Two different layers refuse with different words.** `cmd/renet` says
`backup push --to storage is retired`; the bridge functions layer (`pkg/functions/commands/backup.go:30`) says `backup_push with a 'storage' destination is retired`. Assert on what both share, and know which layer the test actually drives.

## When local genuinely cannot reproduce it

Distro-specific failures (a package manager path, a missing module) may need the real matrix cell. `VM_IMAGE=<ubuntu-24.04|debian-13|fedora-43|opensuse-16.0|oracle-10>` reproduces one locally; rocky-10 is excluded on purpose (no btrfs).

To read a CI failure without waiting for the run to finish: **artifacts upload per job and are downloadable before the run completes**, while the whole-run log is unavailable until every job is terminal. A finished job's own log reads at any time with `.ci/scripts/ci/ci-trace.py --job <id> --log` (`--errors` for the failing step only).

```bash
gh api repos/rediacc/console/actions/runs/<id>/artifacts -q '.artifacts[].name'
gh run download <id> --repo rediacc/console -n test-e2e-workers-<distro>-<sha> -D ./art
```

The `<sha>` in the artifact name is the **merge** sha for a PR run, not your branch head - list the names rather than constructing them.

Read CI results at **JOB level**, never run level: a `cancelled` job did not run, and in a run summary that is indistinguishable from a pass.

## vm:check: the push proof for VM-facing changes

`npm run vm:check -- --changed` proves a push against the ops VMs and the dev gateway, and writes the receipt that `block_vm_unverified_push` reads. The trigger is `.ci/rediacc_ci/drills/vm_check_trigger.py`, and every hit belongs to one of two sides. The renet side is `packages/cli/src/remote/`, `services/repo/repo-key-deployment.ts`, and a `private/renet` pointer move into `cmd/`, `pkg/`, `go.mod`, `go.sum` or `embed-assets.lock.json` (every non-test file the deployed binary is built from). The account side is a `private/account` pointer move into `src/`, `web/`, `drizzle/`, `scripts/`, `package.json`, `package-lock.json`, `tsconfig.json`, `wrangler.toml`, `dev.defaults.env`, `docker-compose.yml` or `Dockerfile`, plus the drill files `license.py`, `universe.py` and `transfer.py`. A change to `vm_check.py` or `lib.py` reaches both sides. Test-only paths (`_test.go`, `*.test.ts(x)`, `*.spec.ts(x)`, `/__tests__/`, `/testdata/`, `/tests/`, `/e2e/`) trigger nothing. A pushed range needs a VERIFIED receipt for its tree that covers each side it touches. With no hit, `--changed` prints the no-op line, writes nothing and exits 0.

Phases: `--changed` requires the phases of the sides the range touches, and a bare run, or a push base that cannot be resolved, requires both. P0 (lock), P1 (renet build check), P4 (token), P2 (fleet) and P3 (keys) run every time, and T (teardown) closes every run. The renet phase adds P5 and the V1.1-V1.7 checks of the repo shell, sync, SFTP and VS Code paths. The account phase adds three groups of steps. A1 runs before P0, so a red suite stops the run before any VM is touched: A1.1 `check:ci-account-server`, A1.2 `check:ci-test-account-web`, A1.3 `typecheck` and A1.4 `typecheck:web` of `private/account`. A0 decides gateway freshness after P1. A2 runs after P3 against the worker: A2.1 the universe drill, A2.2 the transfer drill and A2.3 the license drill with `--legs c,d,e,f --no-restart --seed-repo` (legs a and b need Ceph and the .12 VM, and stay the full-cluster drill's job; `--seed-repo` creates `drill-repo` on the worker once, and it stays there). Suites and drills run without `REDIACC_TOKEN`, `REDIACC_ACCOUNT_SERVER`, `RDC_DEV` and `DRILL_EXPECT_NO_KEYRING`, so a declared skip cannot turn into a pass.

A0 gateway freshness: the dev gateway does not hot-reload, so it is reused only when it answers, `.account-state` matches the record `.ci/cache/vm-check/gateway.json`, and the record's account digest equals the account worktree. Otherwise the runner restarts it (log in `.ci/cache/vm-check/gateway.log`), rewrites the record and leaves it running for the next run. A restart rotates the dev passwords and may move the port, and the run prints both.

Modes: a running fleet (bridge .1 and worker .11 up) is reused and never sent `ops down`; a stopped one is started with `ops up --basic` and taken down again at the end. `--os <image>` must match a reused fleet. The renet phase works on two `vmc-` forks of one grand (`--parent`), never on the grand itself.

Costs: the renet phase alone is 46-76 s warm and 146 s cold. The account phase with a reused gateway is about 8-11 min (A1 about 110 s for the server suite, 43 s for the web suite and 30-60 s per typecheck pair; A2 about 30-60 s universe, 60-120 s transfer and 2-4 min license), and a gateway restart adds 45-90 s. Both phases run about 9-13 min warm. These are estimates until the live acceptance run measures them.

Verdicts: VERIFIED exit 0, FAILED exit 1 (an assertion failed, a suite or typecheck exited non-zero, or a drill reported a failed count), NOT_VERIFIED exit 77 (the check could not judge). A run with no assertion is never VERIFIED. NOT_VERIFIED classes: `fleet-busy`, `no-kvm`, `fleet-unavailable`, `fleet-os-mismatch`, `worker-not-in-config`, `renet-build-mismatch`, `account-unavailable`, `account-gateway` (the gateway did not start or stayed unhealthy; the log tail is the evidence), `account-drill-setup` (a drill exited non-zero with no summary line, such as a missing keyring), `account-drill-skipped` (a drill reported SKIPPED or zero assertions), `phase-not-run` (a required phase did not finish every step), `parent-grand-missing`, `agent-policy-refused`, `vscode-absent`, `no-assertions`, `teardown-failed`, `crashed`.

Receipt: schema 2 is a clean break. It adds `phases` (per side: `required`, `ran`), `account` (`pointer`, `checkout`, `modified`, `gateway`) and `trigger.sides`, and a VERIFIED one needs every required phase to have run. The input digest covers both the `private/renet` and `private/account` pointers. Schema 1 receipts in `.ci/cache/vm-check/` stay on disk but no longer count: they admit nothing and back no `vm-unavailable` escape, and the runner says so once. The guard refuses a receipt with `phase-missing` (a touched side whose phase did not run, such as a renet-only receipt on an account range), `account-mismatch` (the account checkout is not the pointer) or `modified-account` (the account worktree differs from its checkout), beside the existing build codes.

Teardown runs in `finally`, also on SIGINT and SIGTERM: `vscode cleanup`, `repo delete` of the run's forks, a `repo list` proving neither tag remains, then the lock. Anything left behind is named in the receipt and turns VERIFIED into NOT_VERIFIED `teardown-failed`. The gateway is the one thing teardown leaves running. Receipts live in `.ci/cache/vm-check/` (`receipt.json` plus one archive per tree).

The escape is the operator's: `VM_CHECK_PUSH_REASON='<vm-unavailable|not-runtime|deadline>: <why, 40+ chars> ASKED:<YYYY-MM-DDTHH:MM>Z'` on the push, where the minute matches an AskUserQuestion answer in the transcript; `vm-unavailable` also needs a schema 2 NOT_VERIFIED receipt (such as `account-gateway`) for the same inputs. Each admitted escape is a line in `agent/ledgers/vm-check-push-reasons.jsonl`, which records the sides and the `private/account` pointer.

## Standing rules

- Teardown is `./rdc.sh ops down`, and it is not automatic. VMs persist.
- Do not `git checkout`/`restore`/`stash` to undo a mistake in this tree.
- `packages/e2e-tests/.env` is local scaffolding; keep it out of commits.
