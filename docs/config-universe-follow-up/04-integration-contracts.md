# 04. Integration Contracts: renet / rdc / account

The three components must move as one system. These contracts are the seams; every
Wave-2 change names which contract it touches and adds the cross-side test with it.

## C1. The tier map (renet owns, everyone consumes)

- Source of truth: renet's explicit total tier map (02 section 1).
- Distribution: the generated renet contract carries it; the CLI consumes the
  generated data; a parity test fails on divergence (03 T3).
- Change protocol: adding a renet function REQUIRES a tier entry (T2 gate) and a
  contract regen (`check:ci-renet-types`); the CLI never hand-maintains function
  lists again.

## C2. Failure-reason taxonomy (renet emits, CLI maps, docs promise)

- Wire reasons: missing, expired, machine_mismatch, repository_mismatch,
  sequence_regression, invalid_signature, identity_mismatch, cert_expired,
  cert_invalid. Wave 2 adds none unless the datastore-identity binding needs a
  distinct reason (RECOMMENDED: reuse identity_mismatch with a datastore-specific
  message, keeping the taxonomy stable).
- Every reason has: a renet error, a CLI recovery-guidance entry (auto-recover vs
  fail-fast), and a docs row in the recovery matrix. The three MUST move together;
  the docs' recovery matrix is a public promise (this is what the invalid_signature
  force-reissue deviation violated before it was fixed).

## C3. Issuance and renewal API (account owns)

- Existing: `POST /licenses/activate-repo[,-batch]` with api-token auth
  (`license:activate`), returns signed blob with fingerprint publicKeyId (+ embedded
  delegation cert on on-prem). Responses pass the `responds()` airlock.
- Wave 2 additions: optional `clusterId` on activate/renew (informational);
  datastore-identity field in the license payload (02 section 2); `POST
  /licenses/renew` authenticated by the presented blob itself (02 section 3),
  slot-neutral per the recommended policy.
- Compatibility note: servers must deploy BEFORE new CLIs rely on new fields, same
  deploy-order rule as the fingerprint change (old servers emitting "default" are
  refused by the current CLI). State the order in the rollout notes of every change.
- Concurrency semantics are part of the contract: renewal idempotent; activation
  insert race-hardened (02 section 4); sequence bumps monotonic per
  (keyId, subscriptionId) scope.

## C4. On-machine artifacts (renet owns the read side, CLI owns the write side)

- License files: unscoped population `/var/lib/rediacc/license/repos/<guid>/<keyId>.json`
  for the implicit default datastore, datastore-scoped population
  `/var/lib/rediacc/license/datastores/<dsId>/repos/<guid>/<keyId>.json` for named
  datastores (landed Wave 2); chmod 640, written atomically; the ONLY file the CLI may
  delete is the legacy flat `<guid>.json` (the no-clobber property is test-pinned).
  Renewal (renet-side writes) must follow the same atomicity and never touch other
  keyIds' files.
- Chain state: `/var/lib/rediacc/license/chain-state.json`, composite
  `"<keyId>:<subscriptionId>:<repositoryGuid>:<datastoreId>"` keys (repository part
  landed with the P1 fix; datastore part landed after the drill's S8d leg caught a
  datastore fork — same repo GUID, re-minted dsId — regressing its parent's head.
  datastoreId is empty for default-datastore repos; older key shapes self-GC on save).
- New in Wave 2: the license-blocked failure marker directory (02 section 3) and the
  fork-identity descriptor write (02 section 2). Both get explicit owners: renet
  writes markers and descriptors; the CLI only reads them.

## C5. Cross-language fixtures (the fingerprint precedent)

Any value computed on both sides (fingerprints, datastore identity derivation, chain
hashes, renewal request signatures) ships ONE fixture used verbatim by the Go tests
and the TS tests, generated once and committed. Divergence between implementations
must be structurally impossible to miss (the campaign's fingerprint fixture is the
template: same constants in `pkg/subscription/fingerprint_test.go` and the account
cross-language suite; regenerating `fixtures.json` requires both sides re-run).

## C6. Config and state ownership (from the config-universe model)

- The CLI's config is the universe: machines, clusters, datastores, account server,
  tokens per config. The account server never learns machine addresses; it learns
  machineIds, guids, and (new) clusterId/datastore identity.
- renet learns nothing about accounts except what license blobs carry; the renewal
  URL travels IN the blob (recommended) to preserve this.
- State bucket writes (`state.clusters`, `state.datastores`) never enter the remote
  config blob (verified property of the transfer feature; keep it true when adding
  cluster-license state, which belongs machine-side or account-side, not in config
  state).
