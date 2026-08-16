---
name: e2e-local
description: Running the Playwright/bridge E2E suites LOCALLY against the KVM fleet instead of round-tripping CI. Covers the two-command recipe (create-e2e-env.sh + run-e2e.sh), targeting one suite or one distro, the three env traps that make a local run fail in ways CI never does (missing bin/renet, CI=true stealing the data dir, the wrong SSH key), how to read bridge-logs, and how to pull a failing CI job's artifact when a distro-specific failure genuinely cannot be reproduced locally. Use whenever an E2E test is red, before pushing a test change, or when tempted to "just push and see what CI says".
tools: Bash, Read, Edit, Write, Grep, Glob
model: opus
---

You run E2E locally. The whole point is that a CI round-trip costs 30-90 minutes
across a five-distro matrix and tells you one thing, while the same suite runs
here in about a minute per suite. Every note below was paid for live.

## Why this exists

A wave spent four CI rounds fixing four one-line test bugs, one per round,
because the watchdog cancels the rest of the matrix as soon as one distro fails.
That serialises diagnosis to one distro per round. All four were reproducible
locally in seconds. **Never push a test change to find out whether it works.**

## The recipe

The fleet must be up first (see `ops-vms`): `./rdc.sh ops up --basic` gives the
bridge `.1` + worker `.11`; `ops up` adds `.12`, which the worker suite wants.
`virsh list --all` is the fastest honest check — VMs persist across sessions, so
they are usually already running.

```bash
# 1. env file describing the fleet (regenerate whenever the fleet changes)
#
# TOPOLOGY COMES FROM THE FLAGS, NOT THE ENVIRONMENT. This block used to carry a
# `VM_BRIDGE=... VM_WORKERS=... VM_CEPH_NODES=...` prefix, which is INERT:
# create-e2e-env.sh:66-72 reads topology only from --vm-workers/--vm-ceph-nodes.
# It appeared to work because the values happened to match the defaults. (VM_RAM_*
# and VM_IMAGE DO fall back to env; topology does not.)
.ci/scripts/env/create-e2e-env.sh \
  --renet-path "$PWD/private/renet/bin/renet" \
  --output packages/e2e-tests/.env \
  --vm-workers "11 12"

# 2. run everything, or one suite
.ci/scripts/test/run-e2e.sh --workers 1 --fail-on-skip
.ci/scripts/test/run-e2e.sh --workers 1 --test 25-backup-chunk-store
.ci/scripts/test/run-e2e.sh --workers 1 --grep "@backup"
```

`--test <substring>` is the one that turns a 40-minute suite into a 60-second
one. Use it while iterating, then run the whole thing once before pushing.

## The three traps that only bite locally

CI sets up an environment that hides all three, so a local first run fails in
ways the workflow YAML will not explain.

1. **`bin/renet` does not exist in this repo.** The generated `.env` defaults
   `RENET_BINARY_PATH` to `<repo>/bin/renet`, which is a CI-only artifact. Setup
   dies with `Renet: NOT FOUND` / `Renet binary not available`. Point
   `--renet-path` at `private/renet/bin/renet`.
   **Check the flavor before using any renet binary** (`go version -m <path>`):
   `-tags=nolicense` is the dev build you want. A binary with NEITHER
   `nolicense` nor `ProductionPublicKey=` is the poisoned bare-`go build`
   artifact and every licensed op will fail — see `ops-vms`.

2. **`CI=true` in the generated `.env` steals the data directory.** renet
   resolves its data dir as `RENET_DATA_DIR` > CI autodetect > `~/.renet`
   (`pkg/infra/opsconfig/config.go:284`), so with `CI=true` it looks under
   `/tmp/renet` and the VMs' authorized key is not there. Symptom is a quiet
   line, not an error: `SSH key not found at /tmp/renet/staging/.ssh/id_rsa,
   using default SSH`. Append `RENET_DATA_DIR=$HOME/.renet` to the `.env`.

3. **The key the VMs authorize is the renet-staged `id_rsa`**, not
   `~/.ssh/id_ed25519`. A bare `ssh` can still succeed with the wrong `-i`
   because OpenSSH falls through to default identities; the CLI cannot. If bare
   ssh works and the suite does not, this is why.

## Reading the results

- `packages/e2e-tests/reports/bridge-logs/summary.txt` — every test with
  ✓ / ✗ / ○ (skipped). Read this first; it is the whole picture in one file.
- `bridge-logs/<suite>/<test-name>.txt` — per-test, with the exact SSH command
  sent, its raw STDOUT and STDERR **separately**, and the assertion diff. This
  is where a wrong assertion becomes obvious.
- `○` after a `✗` usually means the failure aborted the rest of the file, so the
  frontier is the FIRST `✗`. Fixing it commonly exposes the next one — expect to
  iterate, which is exactly why you want to be local.

## Assertion traps this suite has already paid for

- **`getCombinedOutput()` LOWERCASES** (`TestHelpers.ts:15`). Any expected value
  carrying a capital can never match, and the test then reports the product
  broken while it is behaving correctly. Four shipped in one wave (`/No such
  file/`, `'ABSENT'`, an RFC3339 timestamp with its `T` and `Z`). This is now
  gated by `check:ci-e2e-case-blind`; run it before pushing a test change.
- **A verb's stdout may arrive wrapped on STDERR.** `renet functions once`
  swallows the verb's stdout and re-emits it inside
  `msg="[verb] {\"...\"}"` with escaped quotes. A parser that accepts only bare
  JSON lines reports "no record" for a record that was produced correctly. Parse
  `stdout + stderr` and unwrap.
- **Two different layers refuse with different words.** `cmd/renet` says
  `backup push --to storage is retired`; the bridge functions layer
  (`pkg/functions/commands/backup.go:30`) says `backup_push with a 'storage'
  destination is retired`. Assert on what both share, and know which layer the
  test actually drives.

## When local genuinely cannot reproduce it

Distro-specific failures (a package manager path, a missing module) may need the
real matrix cell. `VM_IMAGE=<ubuntu-24.04|debian-13|fedora-43|opensuse-16.0|oracle-10>`
reproduces one locally; rocky-10 is excluded on purpose (no btrfs).

To read a CI failure without waiting for the run to finish: **artifacts upload
per job and are downloadable before the run completes**, while
`gh run view --log` refuses until every job is terminal.

```bash
gh api repos/rediacc/console/actions/runs/<id>/artifacts -q '.artifacts[].name'
gh run download <id> --repo rediacc/console -n test-e2e-workers-<distro>-<sha> -D ./art
```

The `<sha>` in the artifact name is the **merge** sha for a PR run, not your
branch head — list the names rather than constructing them.

Read CI results at **JOB level**, never run level: a `cancelled` job did not run,
and in a run summary that is indistinguishable from a pass.

## Standing rules

- Teardown is `./rdc.sh ops down`, and it is not automatic. VMs persist.
- Do not `git checkout`/`restore`/`stash` to undo a mistake in this tree.
- `packages/e2e-tests/.env` is local scaffolding; keep it out of commits.
