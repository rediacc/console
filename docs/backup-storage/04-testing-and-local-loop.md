# 04. Testing and the local loop

Status: verified 2026-08-09, branch main. The operator's standing rule: prove
everything locally that can be proven locally; cloud probes are a separate,
cost-declared, operator-visible leg. The operator has exported
`REDIACC_ALLOW_CLUSTER_OPS=*` and `REDIACC_ALLOW_GRAND_REPO=*` in the launching
terminal, so datastore/cluster and grand-repo drill legs are unblocked (ancestry
verification requires it to be set BEFORE the session starts).

## The vacuum being filled (do not repeat it)

The existing "backup" e2e suites verify nothing: suite 10's 17 tests assert only
`hasValidCommandSyntax`, which never reads the exit code (its unreachable-machine
test passes on connection failure); suite 15 string-matches generated rclone flags
with fabricated credentials. No test anywhere composes create-with-known-content,
push-to-S3, pull-elsewhere, compare-checksums. The proven techniques exist apart:
suite 17's LUKS-image sha256 identity (`repositoryImageSha256`,
`RepositoryHelpers.ts:195`, plus its divergence-before-convergence promote proof),
suite 19's real S3 round-trip, suite 13's MD5 table hashes. The battery composes
them. Also: the `pkg/delta` btrfs round-trip tests have NEVER RUN (build tag with no
invoker); wave 0 wires them first.

## Three tiers, all on existing harnesses

1. Control plane (seconds, no infra): vitest in private/account on the
   `config-portal.test.ts:27-50` shape (fresh in-memory SQLite replaying the real
   drizzle migrations, `MemoryBlobStorageService`, `blob.clear()` per test).
   Additions: grant-path local double (the memory blob service has no URL concept;
   the grant abstraction needs a memory/local implementation designed in), DTO
   planted-strip control, scope-registry registration, no clock seam exists so
   retention tests backdate rows (the house convention).
2. Byte-verify battery (minutes, ops VMs): new numbered suite in packages/e2e-tests
   under the default config (runs inside `test-e2e-workers`). Registration: the
   playwright project list, the README table, LIVE_CONFIG_REGISTRY only if a new
   config, skip-hygiene testIgnore if a new subdir. Zero-skip contract: any
   `test.skip()` firing in CI is a job failure, select by config instead. Delete
   `.e2e-coverage-allowlist` lines (`backup_delete`, `backup_list`) as coverage
   arrives (a covered entry fails the gate as stale). New corruption-injection
   helper (does not exist anywhere): flip a byte in a stored chunk, delete another,
   assert verify/scrub fire; a verification-disabled twin MUST fail it (prove the
   instrument). Restore assertions prefer image-sha over mounted-content reads
   (post-swap remounts over two-hop SSH are flaky; suite 17 documents it).
3. Live drill: `scripts/drills/backup.sh` reusing `scripts/drills/lib.sh` verbatim
   (separate stdout/stderr capture, numbered assertions, `drill_setup_run` vs
   assertion split, `--selftest` that must fire, `--keep-work`, SKIPPED-not-PASSED,
   the check-drill-verdicts meta-gate). Dispatch: about 10 lines in `run.sh:1982+`.
   The offline battery is the drill's NAMED CONTROL (the license precedent: "if a
   leg fails here but its twin passes there, the difference is the machine").
   Preflight refuses unsupported legs BY NAME and reports both missing operator
   overrides at once.

## Local end-to-end topology

Bridge VM (.1) runs RustFS on :9000 as the chunk store. TRAP: `ops up` does not
start RustFS and `rdc ops` has NO rustfs subcommand; call the renet binary directly
(`"$RENET_BINARY" ops rustfs start`, creds `rediacc-rustfs`/`rediacc-rustfs-secret-key`,
bucket `rediacc-test`, `pkg/infra/opsconfig/config.go:240-252`). Worker .11 hosts
the source repo (real btrfs/LUKS datastore, `--basic` suffices); worker .12 is the
cross-machine restore target (full `ops up`). Host runs `./run.sh account dev`
(gateway port is DYNAMIC, re-read from `.account-state` every time; tsx never
hot-reloads, restart the gateway after every server edit) with its own RustFS on
:9100 for control-plane blobs. EVERY machine-facing URL uses the bridge host
192.168.111.254, one value per run (IP-bound tokens key on the Host header).
Backup verbs carry only grandGuard, which does not apply to forks: the near-instant
fork is the per-test isolation unit and agents drive the whole battery without
overrides. Edit-test cycle: renet Go changes auto-deploy on any `./rdc.sh` call;
account changes cost a gateway restart; a tsc error anywhere in packages/cli fails
`ops up` before any VM work (check `npx tsc --noEmit` when ops dies instantly).

## Cloud probes (the only things local cannot prove)

1. Temp-cred local signing against a real parent token: `actions` enforcement and
   the undocumented TTL bounds.
2. If-None-Match 412 on real R2 (RustFS conditional writes are known-fragile; never
   assume parity).
3. Bucket lifecycle rules (Cloudflare-side API, no RustFS equivalent).
4. One multipart sanity pass (not needed for MiB cells, but cheap insurance).

Vehicle: a `rediacc-backups-bench` R2 bucket on the `rediacc-configs-bench` footing
(wiped by the `reset-bench.sh` pattern, credentials via the cf-r2 rotation slug,
`rotation check --for=bench` preflight), exercised by a `--cloud` leg on the drill,
operator-run, cost-declared. Keep it out of the free local battery.

## CI placement

Offline battery job: template is `test-drills` (`ct-tests.yml:1728-1732`,
ubuntu-latest, 30 min, S3 free via `./run.sh account dev`, no org secrets, mind
`set -o pipefail`). A job inside ct-tests.yml rolls up through RESULT_TESTS with no
assert-ci-complete edit. Scope key `backup_e2e` spelled in FOUR places:
`scope-map.cjs` JOB_SURFACES, `ci.yml` initialize outputs (a key missing there is
SILENTLY DROPPED and the job just runs), the ct-tests input pass-through, and
`test-scope-gate-outputs.sh` WORKFLOW_CONTRACT_KEYS. Battery scripts placed under
`.ci/scripts/` force a full 70-minute round on every self-edit (82.5% of PRs touch
.ci/.github); weigh placement. Slim runners die at 15 minutes as CANCELLED; use
ubuntu-latest. The elite conformance probes extend the existing Elite Run job's
healthcheck (`ci.yml:888-949`, gated by `run_elite_run`); the portal quota page
smoke rides `deploy-preview`/`smoke-test-preview` (TRUE as of 2026-08-15, and it
was NOT before: this line asserted the coverage while `smoke-test-preview.ts`
matched neither `backup` nor `quota`, and CHECKLIST w3 was ticked on the strength
of it. `stepQuotaPageShipped` now asserts the SERVED BUNDLE still mentions the
`backup-storage` route, because the portal is a single-page app and a 200 on the
route would prove nothing); future Stripe quota purchases
ride `stripe-sandbox` (`ci.yml:538-607`). The btrfs-tagged delta tests get a
loop-mounted btrfs invocation in `run-tests.sh` (wave 0). New renet verbs must be
exercised by a suite a LIVE playwright config selects or `check:ci-e2e-coverage`
counts them dark.
