# @rediacc/e2e-tests

Playwright-driven e2e suites for the console/renet platform. Most suites go
through `BridgeTestRunner` (SSH → `sudo renet …`); suite 23 additionally drives
the real `rdc` CLI via `CliRunner` (the first CLI-driving harness, and the
interface point the future examples program reuses).

Suites are selected per CI job by the `playwright.*.config.ts` files. Which config
each CI job runs is the single source of truth for "is this suite live":

| Config | CI job | Suites |
|---|---|---|
| `playwright.config.ts` (default) | E2E Workers (×5 distros) | 01-07, 10-14, 15-19, 21, 22 |
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

7. **Suite 23 (CLI migrate routing) — pending local validation.** Authored and
   tsc-green, but the E2E Workers `ubuntu-24.04` leg does NOT set `CLI_SUITE=1` yet.
   Before enabling it, transcribe the exact `repo create`/datastore argv + the
   `beforeAll` machine-registration/SSH wiring from the wave round-log transcript
   and validate on a local two-worker fleet (`VM_WORKERS="11 12"`). To enable:
   add `cli-suite: '1'` to the `ubuntu-24.04` matrix leg in `ct-tests.yml`. Run
   locally with `CLI_SUITE=1` and two workers present.
