# E2E — real machines, `run-e2e.sh`

For CLI or renet behaviour that only appears against a live machine: repo
lifecycle, forks, datastores, backup, containers, clustering.

## Finding the file that already owns it

**Grep for the verb first.** Filenames mislead: fork behaviour is NOT in
`04-repository-lifecycle.test.ts`, which has zero fork references, but spread
across `13-postgres-fork-isolation`, `13b-live-fork-checkpoint` and
`17-repo-branching`.

```bash
grep -rln "repo fork" packages/e2e-tests/tests/
```

New file: `packages/e2e-tests/tests/NN-<name>.test.ts`. The prefix is the
project name in `playwright.config.ts` (`testMatch: 'NN-*.test.ts'`), so a
prefix with no project is never selected. Numbers are not contiguous.

**SUBDIRECTORIES ARE EXCLUDED.** `playwright.config.ts:30` ignores
`ceph/`, `kube/`, `migrate/` and `ops-lifecycle/` because each has its own
config (`playwright.ceph.config.ts` and friends) and its own CI job. A file
dropped in one of those without using its config is collected by nothing.

## Running it locally

CI runs a five-distro matrix in ~40 minutes. Locally it is about a minute.

```bash
.ci/scripts/env/create-e2e-env.sh --vm-workers 1
.ci/scripts/test/run-e2e.sh --workers 1 --test 25-backup-chunk-store
```

`--test <substring>` is what turns 40 minutes into 60 seconds. `--fail-on-skip`
stops a skipped case reading as a pass. See the `e2e-local` agent for the three
env traps.

## Proof

- the case is selected: its prefix matches a project, and it is not under an
  ignored subdirectory
- `check:ci-e2e-coverage` — **both directions**: every shipped renet verb is
  exercised by a suite CI runs, and no test dispatches a verb renet dropped
- **the job that runs YOUR file** green: `ct-tests.yml` has fourteen, from
  `test-e2e-workers` to `test-e2e-ceph`, `test-e2e-k8s` and `test-fork-isolation`

## What makes an E2E case fake

Asserting on the CLI's own summary line instead of the machine's state. Ask the
machine. A case that only reads stdout passes when the command lies.
