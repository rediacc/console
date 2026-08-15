# @rediacc/e2e-tests

Playwright-driven e2e suites for the console/renet platform. Most suites go
through `BridgeTestRunner` (SSH → `sudo renet …`); suite 23 additionally drives
the real `rdc` CLI via `CliRunner` (the first CLI-driving harness, and the
interface point the future examples program reuses).

Suites are selected per CI job by the `playwright.*.config.ts` files. Which config
each CI job runs is the single source of truth for "is this suite live":

| Config | CI job | Suites |
|---|---|---|
| `playwright.config.ts` (default) | E2E Workers (×5 distros) | 01-07, 10-14, 15-19, 21, 22, 25 |
| `playwright.ceph.config.ts` | E2E Ceph | ceph/08, 09, 12c |
| `playwright.ceph-workers.config.ts` | E2E Ceph Workers | ceph/13, 14 |
| `playwright.k8s.config.ts` | E2E K8s | kube/15 |
| `playwright.k8s-ceph.config.ts` | E2E K8s Ceph | kube/16 |
| `playwright.k8s-multinode.config.ts` | E2E K8s Multinode | kube/17 |
| `playwright.migrate.config.ts` | E2E Migrate | migrate/18 |

## Leg-gated suites (run in CI, but not on every leg)

- **12a/12b/12d (full-integration composition) + 13b (live CRIU fork)** run only on
  the `FULL_INTEGRATION` legs of E2E Workers (`ubuntu-24.04` + `fedora-43`;
  `ct-tests.yml` matrix `include`). Composition logic is distro-agnostic, so two
  legs — one apt-family, one rpm-family — are the honest floor. On those legs
  `CRIU_EXPECTED=1` turns 13b's "CRIU absent" guard from a silent skip into a hard
  failure. **Locally (no `CI`) all of these always run**, so they can never go dark
  on a developer machine.

## Deliberately not in CI

These are intentionally omitted from the pipeline, with the reason recorded here so
whoever reads the tests or the workflow hits it (rediacc/console#521 CI-visibility
requirement). `ct-tests.yml`'s header points here.

1. **Cross-site / concurrent multi-cluster migrate; parent + fork concurrent
   clusters.** Two concurrent KVM clusters exceed the 16 GB runner ceiling
   (rediacc/console#521 class). Proven live in the P3 batteries and the B1 window;
   re-verify locally per release. The single-cluster migrate IS in CI (E2E Migrate,
   suite 18).

2. **`cluster rehearse` e2e.** Needs a second concurrent bare KVM dest cluster
   (≈ +5 GB over the ~11.3 GB single-cluster budget) — over the 16 GB runner ceiling
   (rediacc/console#521 class). Proven live in the B1 window; re-verify locally per
   release via the B1 recipe.

3. **Suite 20 (image-build).** 35-min-per-test VM image builds; the surface changes
   rarely and only deliberately. Run locally when touching image-build code:
   `npx playwright test --config=playwright.image.config.ts`.

4. **Suite 18 ops-workflow destructive VM tests.** Self-skipped in CI by design
   (`tests/18-ops-workflow.test.ts`): they stop/start the fleet other suites depend
   on, so they only run in a dedicated local session.

5. **The two `csi-sanity` conformance specs that stay red by design.** The
   Renet-job `csi-sanity` step skips exactly two upstream specs — "CreateVolume …
   maximum-length name" and "CreateSnapshot … same name / different source". Both
   are RULED design deviations (spec 09 §16, CSI-DEVIATION-1/2), each already
   enforced by a dedicated Go unit test. 48/50 specs run and must pass. Do not
   remove the skips without re-ruling the deviations.

6. **Examples suite (07 §1-5).** A separate program; its CI topology is specified
   there. Interface points this wave leaves for it: `CliRunner`
   (`src/utils/CliRunner.ts`) as the rdc-driving precedent, and the live-config
   registry the coverage gate uses (add `ci-examples.yml`'s config to it).

7. **Suite 26 (chunk-store backup: control plane, upload engine, restore).**
   All three of its tiers need something the E2E Workers legs do not have, and
   that job runs `--fail-on-skip`, so a skip inside it is a job failure rather
   than a notice. The ACCOUNT tier needs a running account server plus an api
   token carrying `backup:read`; the ENGINE tier additionally needs a two-worker
   fleet (the run verb `renet backup snapshot` exists since 2026-08-14 and is
   probed, not assumed); the RESTORE tier additionally needs a two-worker fleet
   AND a real bucket. Its download path landed 2026-08-14 (`renet backup
   restore`, `pkg/chunkstore/download.go` + `restore.go`), so
   `E2E_CHUNK_RESTORE_VERB` now DEFAULTS to `backup restore` and needs no
   export — but the tier still probes `renet backup --help` on the DEPLOYED
   binary, so a fleet whose renet predates the verb skips loudly rather than
   going green on a variable. The project is therefore gated behind
   `BACKUP_STORAGE_SUITE=1` and collects nothing in CI. The machine-tier
   coverage CI DOES run is suite 25, which drives `backup snapshot --dry-run`
   with no account server at all. Locally:

   ```bash
   ./run.sh account dev     # note the gateway port it prints
   BACKUP_STORAGE_SUITE=1 \
     REDIACC_ACCOUNT_SERVER=http://127.0.0.1:<port> \
     E2E_ACCOUNT_API_TOKEN=<token with backup:read> \
     npx playwright test tests/26-backup-storage-cli.test.ts
   # the ENGINE tier additionally wants VM_WORKERS="11 12";
   # the RESTORE tier wants the same fleet plus a real bucket. Its verb now
   # defaults correctly, so E2E_CHUNK_RESTORE_VERB is an override, not a
   # prerequisite.
   ```

   All three tiers fail CLOSED: absent prerequisites with no declaration are a
   RED, not a skip. Declare an intentional omission with
   `E2E_EXPECT_NO_ACCOUNT_SERVER`, `E2E_EXPECT_NO_CHUNK_ENGINE` or
   `E2E_EXPECT_NO_CHUNK_RESTORE`.

8. **Suite 23 (CLI migrate routing) — pending local validation.** Authored and
   tsc-green, but the E2E Workers `ubuntu-24.04` leg does NOT set `CLI_SUITE=1` yet.
   Before enabling it, transcribe the exact `repo create`/datastore argv + the
   `beforeAll` machine-registration/SSH wiring from the wave round-log transcript
   and validate on a local two-worker fleet (`VM_WORKERS="11 12"`). To enable:
   add `cli-suite: '1'` to the `ubuntu-24.04` matrix leg in `ct-tests.yml`. Run
   locally with `CLI_SUITE=1` and two workers present.

9. **`packages/json`'s Rediaccfile template suite** (`packages/json/test-templates.sh`,
   28 templates). Not an e2e suite, listed here because this is the repo's one
   discoverable index of "runs nowhere in CI, and here is why" — leaving it
   undocumented is how an unrun suite reads as a passing one.

   It is MACHINE-TIER and cannot run on a bare CI runner. Every Rediaccfile calls
   `renet compose`, which needs a per-repo network id; on a freshly provisioned
   fleet member with Docker healthy and `renet` on disk it exits
   `--network-id is required and must be a valid non-zero value`, because the
   worker has no `/mnt/rediacc/repositories` at all. Running one template
   therefore needs a LICENSED rediacc repo on a VM, not merely a VM: the ops
   nodes are absent from every config, so it also needs machine registration and
   a repo created through the account server.

   Sizing, measured 2026-08-14 rather than estimated: one LIGHT template
   (`caching/redis`) took 374s wall, and the script allows `TEST_TIMEOUT=240` per
   lifecycle function plus `HEALTH_CHECK_TIMEOUT=360`. Twenty-eight templates is
   hours, so it belongs behind a `run_*` flag in `ct-tests.yml` on a fleet-backed
   job, never in the quality lane.

   Whether it earns that job is an OPEN OPERATOR DECISION, not an oversight. Until
   it is taken the suite stays manual and this entry is the record of that.
   Run it locally with a licensed repo present:

   ```bash
   cd packages/json && ./test-templates.sh --template caching/redis
   ```
