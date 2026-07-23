# 03. Testing Pillar

This wave lands FIRST. It is valuable with zero licensing-model changes and it is the
harness every Wave-2 change is proven in. The operator's standing directive: testing
and concurrency support matter as much as the features.

## T1. License-enforcement e2e in CI (the missing seam)

Today no enforcing renet is ever exercised end-to-end: bridge legs build
`--nolicense`, and the `system`-tagged suite that talks to a real account server is
silently skipped (no server in the `test-renet` job). All pieces exist; compose them:

- New ct-tests job (or a leg on an existing bridge matrix): `ci-env.sh` already
  generates throwaway ED25519/X25519 keys; start the account server the way
  `run-account-e2e.sh` does; build renet ENFORCING with the generated pubkey baked
  (`ACCOUNT_ED25519_PUBLIC_KEY` ldflags path in build.sh); provision a bridge VM.
- Scenario battery (assert stdout/stderr/exit codes, not just absence of error):
  register + token mint (headless chain is proven: login, 2fa/verify via TEST_MODE
  totp, device-code or api-tokens), issue, create repo (succeeds, license file at the
  per-key path), remove license (exit 10, reason `missing`), reissue, expired-cert
  delegation leg (two-level validation live), strict backup tier (expired license
  blocks push; operate tier still runs).
- After Wave 2 lands, extend with: renewal happy path, renewal refusal on lapsed
  subscription, fork-identity remetering, slot-cap parallel issuance.
- Keep it on ONE OS leg to bound cost; the 5-OS matrix stays nolicense.

## T2. Tier-map completeness gate (kills the fail-open)

Registry-driven test in renet: enumerate every registered function name; assert each
has an EXPLICIT entry in the tier map; fail closed on any new unclassified function.
Include a prove-the-instrument control (a planted fake function must fail). This
retroactively forces explicit decisions for the ~32 unclassified `repository_*` verbs
and all cluster verbs. Gate wiring follows the repo pattern (npm script + `ci` chain;
workflow inclusion not required, chain-parity direction is workflow into chain).

## T3. Single-source license contract (kills silent drift)

Export the tier map into the generated renet contract
(`renet functions generate-types`, output under `packages/shared/src/renet-contract/`).
The CLI's `isLicensedRenetFunction`/deny-list derives from the contract data instead of
prefix matching. Add a parity test that fails when the CLI's view and renet's map
disagree. Contract regen has a gate (`check:ci-renet-types`); remember the e2e-coverage
gate greps `packages/e2e-tests` for new bridge function names if any are added.

## T4. Un-skip the skipped

Give the `system`-tagged renet suite a real server in CI (fold into T1's job is
acceptable) and add a loud-skip rule: a suite that skips for missing prerequisites
must FAIL the job unless the skip is explicitly expected by the job's configuration.
Silent green-that-never-ran is how this gap survived.

## T5. Drills become a harness

`./run.sh drill <name>` scripted versions of the three manual drills from the previous
campaign, each with setup, assertions, teardown, and a non-zero exit on any failed
assertion:
- `drill universe`: config current source labels, isolation md5s, env precedence,
  per-config tokens (headless, CI-able).
- `drill transfer`: full transfer battery against `./run.sh account dev` including
  seed-on-enable, offline cache reads with stderr warning, fail-closed writes,
  second-device enrollment (headless via password path + TEST_MODE totp; CI-able).
- `drill license`: the two-universe coexistence + delegation battery on ops VMs
  (local-only; documents its VM cost; reuses T1 assertions where possible).
Known footguns to bake in: dev-gateway restarts rotate dev passwords and may change
ports (re-read the credentials block and `.env` each run); a long-running gateway
serves stale server code (tsx does not hot-reload): the drill restarts it.

## T6. Cluster verbs live coverage

Drive `cluster create/join/fork` through the real CLI (`CliRunner`, suite-23
precedent) on the existing k8s-multinode leg; assert the licensing-visible outcomes
once Wave 2 lands (fork remeters, slots claimed per node, pre-flight message at the
wall). Multi-cluster and `rehearse` stay local per the 16GB runner ceiling
(rediacc/console#521), but scripted via T5 conventions.

## Concurrency testing requirements (applies across Waves)

- Parallel first-time issuance for N distinct machineIds vs maxActivations: a
  deterministic race test at the account layer (the in-memory sqlite integration
  suite can interleave promises; see the config seed-race test pattern in
  `config-remote.test.ts`).
- Concurrent renewal of the same blob (two units racing) and renewal racing a CLI
  batch refresh: idempotency asserted at the server, file-write atomicity asserted at
  renet (temp+rename, never a torn blob).
- Chain semantics under interleaving: equal-sequence same-hash passes, equal-sequence
  different-hash rejects, per-key scopes never cross.
- The 409-replay and seed races from the transfer feature already have tests; keep
  them green and extend rather than duplicate.

## Standing verification rules for this big-bang

- Run the real thing: every claimed behavior gets at least one live invocation with
  stdout and stderr read separately.
- Prove the instrument: every sweep/gate ships a planted-defect control; never trust
  a zero from a walker that has not demonstrated it can see arrays; liveness probes
  use absolute paths, no stderr suppression.
- Spot-check every sub-agent's report against the artifacts before building on it.
- Full `npm run ci` must be green at each wave boundary; name any gate you skipped.
