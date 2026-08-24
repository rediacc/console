# E2E — real machines, `run-e2e.sh`

For CLI or renet behaviour that only appears against a live machine: repo
lifecycle, forks, datastores, backup, containers, clustering.

## Where the case goes

`packages/e2e-tests/tests/NN-<name>.test.ts`. The number is the project name in
`playwright.config.ts` (`testMatch: 'NN-*.test.ts'`), so a file whose prefix has
no project is never selected — it exists and never runs.

## Running it locally, not through CI

CI runs a five-distro matrix and tells you one thing in ~40 minutes. Locally it
is about a minute per suite.

```bash
.ci/scripts/env/create-e2e-env.sh --vm-workers 1
.ci/scripts/test/run-e2e.sh --workers 1 --test 25-backup-chunk-store
```

`--test <substring>` is what turns 40 minutes into 60 seconds. `--fail-on-skip`
stops a skipped case reading as a pass. See the `e2e-local` agent for the three
env traps (missing `bin/renet`, `CI=true` stealing the data dir, wrong SSH key).

## Proof

- the case is selected: its prefix matches a project in `playwright.config.ts`
- `check:ci-e2e-coverage` — **both directions**: every shipped renet verb is
  exercised by a suite CI runs, and no test dispatches a verb renet dropped
- the `ct-tests.yml` job green on the PR head

## What makes an E2E case fake

Asserting on the CLI's own summary line instead of the machine's state. Ask the
machine: `rdc machine status`, a container list, a file that must exist. A case
that only reads stdout passes when the command lies.

Forks are constant-time regardless of repo size — use one per case for isolation
rather than sharing state between cases.
