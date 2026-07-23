# 01. Verified Context

Everything below was verified against the tree on 2026-07-23 (branch 0722-1, with the
config-universe campaign uncommitted on top). RE-VERIFY each load-bearing claim before
building on it; line numbers drift, and other sessions commit to this tree.

## What the previous campaign landed (uncommitted)

- Config = universe: `server.json` deleted, per-config `account.*` + `api-token-<name>.json`,
  `REDIACC_TOKEN`, scoped `REDIACC_DEBUG`, `rdc config current`, rdc.sh `--dev` seeding.
- Licensing: `publicKeyId` = 16-hex SHA-256 fingerprint of the signing Ed25519 key;
  per-signer license path `/var/lib/rediacc/license/repos/<guid>/<keyId>.json`;
  chain-state scoped `"<keyId>:<subscriptionId>"`; two-level delegation validation
  implemented in renet (cert embedded in the blob).
- Tier model after two operator revisions: TWO tiers only.
  `modeOperate` (`repository_up`, `up_all`, autostart): license expiry AND cert window
  skipped; signatures, key binding, machine/repo binding, cert constraints enforced.
  Everything else (create/fork/resize, push/pull/sync/backups, post-fork check): FULL
  validation, both expiries block. `SkipExpiry` tier deleted.
- Transfer: seed-on-enable, encrypted offline read cache, fail-closed writes, bucket
  409 replay, `/account/config-remote` portal page, sealed wizard handoffs.

## The slot model (operator-confirmed semantics)

- Ledger: `subscription_activations`, ONE ROW PER (subscriptionId, machineId), unique
  index on that pair. Verify: `private/account/src/db/schema.ts` around :127.
- The 5-hour float: `MACHINE_AUTO_RELEASE_MS` prunes machine rows by `lastSeenAt`;
  pruned rows are re-created by the next issuance, so the cap applies to routine
  re-issuance bursts, not only first activation.
- Enforcement reads the `maxActivations` DB COLUMN (authoritative); the
  `PLAN_MAX_MACHINES` constant is only the default/reset value. Partner offer-builder
  machineCount flows into the column (`partner-grant.helpers.ts`).
- Repo-license issuance is the event that claims/refreshes the machine slot. The
  per-repo dimension is `maxRepoLicenseIssuancesPerMonth` (monthly) plus the refresh
  cadence below.
- OPERATOR LOCK: per-machine slot at fork/create, floating 5h burst window, NO
  cluster pooling. An N-node cluster consumes N slots during bursts. Clusters are
  metered at repo placement, not at infrastructure provisioning.

## License lifetimes (verified in subscription.service.ts ~:1081)

| Kind | refreshRecommendedAt | hardExpiresAt |
|---|---|---|
| grand | now + 30 days | subscription.expiresAt + 60 days (or now+90d+60d when no expiry) |
| fork | now + 7 days | min(subscription.expiresAt, now + 7 days) |

Two consequences:
- FORK licenses hard-expire in 7 days. Any fork-heavy machine relying on scheduled
  backups dies fast without renewal. Self-renewal (02 section 3) is therefore urgent.
- The pricing-page "60-day grace for scaling" claim, previously thought unbacked, very
  likely maps to the grand +60d window (resize/expand full-validate and keep passing
  for 60 days after subscription end). VERIFY this mapping end-to-end, then align the
  marketing copy and close that ledger item.

## Enforcement reality (verify in pkg/license/runtime.go and pkg/functions)

- `ClassifyRepositoryOperation` whitelists 8 function names; `default: TierNone`.
  32 of ~40 registered `repository_*` functions and EVERY `cluster_* / datastore_* /
  kube_* / ceph_*` function bypass licensing. Guarded only by a hardcoded 11-case
  unit test. No registry-driven completeness gate exists.
- CLI side, `renet-license-contract.ts` `isLicensedRenetFunction` is prefix-based
  (`repository_`/`backup_` minus a 4-entry deny-list), maintained independently of the
  renet tier map. The two can drift with no test noticing.
- Scheduled backups are machine-local systemd units invoking renet directly
  (`backup-schedule-unit-generator.ts`); licenses refresh once at deployment
  (`backup-schedule.ts` ~:122) and never again. renet cannot renew a license itself
  (no account credentials on machines, by design).
- CI reality: every live `repository_create/fork` in ct-tests runs a `--nolicense`
  renet; the one real-issuance system test (`tests/system/subscription_e2e_test.go`,
  build tag `system`) is silently skipped in CI because the `test-renet` job starts no
  account server. There is NO enforcing-renet end-to-end test anywhere.

## The verified holes (Wave 2 fixes these)

1. **Same-node fork license inheritance.** `datastore fork` (pkg/datastore/fork.go) is a
   pure RBD snap+clone: repo GUIDs are NOT reminted, and the cloned datastore keeps the
   parent's on-disk descriptor (Name field included; fork.go never calls
   WriteDescriptor). License files are HOST-local. Therefore a fork attached on the
   same node validates under the parent's license files: no issuance, no slot, and
   repositoryGuid binding cannot distinguish parent from clone. Cross-node forks
   self-meter (files absent, missing, reissue). The flagship whole-cluster fork on the
   same nodes never meters.
2. **Refresh-confluence cliff.** Monthly (grand) / weekly (fork) refreshes across an
   N-node cluster landing in one 5h window re-claim N slots. Under-slotted clusters
   trend to failed refreshes, then hard expiry, then blocked backups and growth under
   the strict tier.
3. **Slot-check race.** The cap is count-then-insert; parallel first-time issuances on
   distinct machineIds (exactly what cluster provisioning does) can all pass and
   overshoot maxActivations. Check whether `tests/integration/concurrency.test.ts`
   covers this; assume not until proven.
4. **PVC clone scope.** CSI `CreateVolume` (pkg/kubecsi/controller.go) provisions
   volumes inside the namespace repo with no license touch (consistent: volumes are
   repo contents) but supports clone-from-PVC. VERIFY whether a clone can source a
   volume from a different repo/namespace; if yes, dataset duplication escapes fork
   metering.
5. **ToS ceiling.** ToS defines Machine as any host running the Renet Agent; every
   cluster node qualifies. Enterprise is bound to "up to 25 Machine activations" in
   the ToS even though maxActivations is technically unlimited. Marketing promises
   cluster fork/migrate loudly and prices it nowhere.
6. **Failure UX.** MAX_MACHINES_REACHED mid-provisioning is a generic error; no
   pre-flight, no Enterprise-path guidance, possible half-provisioned cluster state.
7. **No cluster identity in issuance requests.** The server cannot tell cluster bursts
   from anything else; analytics and support are blind.

## Cluster identity substrate (from the design docs, verify in code)

- Repos live IN datastores; the mounting node changes on failover/migrate by design
  (single-mounter, SAN-LUN model). machineId is an unstable anchor for cluster repos.
- Real cluster principal: the cluster CA fingerprint (re-minted on fork, preserved on
  migrate; pkg/kube/distro/fork_remint.go, identity.go). Control anchor datastore
  `ds-control-<cluster>`; `ClusterConfig.controlNode` exists in the CLI schema.
- Machine-side registry key for a datastore fork is `<parent>:<tag>`; the on-disk
  descriptor does NOT yet reflect fork identity (see hole 1).
