# 05. Execution Guide

## Before anything else

1. Read this doc set fully, then `01-verified-context.md` twice.
2. VALIDATE the load-bearing claims against the tree: line numbers drift and other
   sessions commit here. Minimum validation set before planning:
   the tier map and its default case; the activation schema and cap check; the
   expiry-window derivation; `datastore fork` not touching descriptors or GUIDs; the
   backup unit generator and the one-time refresh; the skipped `system` suite.
3. Ask the operator the five decision points in `README.md` EARLY, in one round.
4. Run the spikes (below) before writing the Wave-2 plan.

## Spikes (short, evidence-producing, before Wave-2 implementation)

- S1 Descriptor write point for fork identity: where a fork's clone is first mounted,
  whether writing the fork registry key into the descriptor there is safe, nested-fork
  behavior. (02 section 2)
- S2 Renewal URL in the license payload: payload schema change, on-prem/delegated
  self-description, air-gapped story. (02 section 3)
- S3 PVC clone-from-PVC scope: can CSI CreateVolume clone across repos/namespaces?
  (01 hole 4)
- S4 Concurrency substrate: what atomicity the account DB layer actually offers for
  the activation insert (D1 vs better-sqlite3 paths), informing 02 section 4.
- S5 The 60-day claim mapping: grand hard-expiry (+60d) vs the pricing copy; align or
  correct. (01)

## Waves and ordering

- Wave 1 (testing substrate, 03 T1-T4): no design dependencies; start immediately
  after validation. T2/T3 will force the explicit tier decisions that Wave 2 codifies.
- Wave 2 (licensing, 02): after decisions + spikes. Order inside the wave: tier map
  totality, fork-identity binding, renewal endpoint + renet command + unit hook,
  race hardening, telemetry field, UX, then public surfaces last (docs/ToS/pricing,
  with the locale delta as the final step so English is stable).
- Wave 3 (03 T5-T6 + live battery): after Wave 2; ends with the full drill set green
  and a written found-not-fixed ledger.

## Staffing rules (operator standing policy)

- Coding sub-agents: Opus by default. Fable for the challenging pieces, at minimum:
  renet fork-identity binding + renewal command (touches validation internals),
  the account renewal endpoint + race hardening (auth-by-blob, concurrency),
  and the T1 e2e composition job.
- Sonnet for ALL translation/naturalization deltas (12 locales, ledgers, hashes).
- At most 2 concurrent writers, disjoint file ownership stated verbatim in each
  prompt; forbid git checkout/restore/stash/clean and repo-wide regenerate scripts in
  every writer prompt; sub-agent reports are spot-checked against artifacts before
  the next phase (full-file reads of the load-bearing files).
- Investigation and planning fan out freely (read-only agents are cheap).

## Standing constraints

- Local and uncommitted. No commit, branch, push, or PR unless the operator asks in
  that task. Multiple sessions share the tree; the shared worklist protocol applies
  (`.claude/hooks/stop/worklist.py --path`, tag items, lease delegated work).
- No em dashes in ANY authored text, any language (repo gate enforces docs; the rule
  is global per operator preference).
- English docs first, hashes regenerated, Sonnet locale delta, search index; the
  naturalization ledger (`.naturalized-hashes.json`) accompanies en.json value edits.
- Deploy-order rule for any server-consumed change: account servers deploy before
  CLIs that require the new behavior (see C3).

## Gates and verification

- Per phase: shared build; tsc (cli, account, account-web); cli + account + web test
  suites; biome; the license-relevant gates (`check:ci-renet` in full, schema
  coverage, contract/tier gates added by T2/T3); shell format/lint for any script.
- Wave boundaries: full `npm run ci` green (expect and triage genuine catches; the
  previous campaign's battery caught six real issues at gates the writers never ran).
- Wave 3 exit: T1 job green in CI, `./run.sh drill` all green locally, the license
  drill re-run on ops VMs, and a final report with verbatim gate outputs and the
  found-not-fixed ledger.

## Definition of done

1. Wave 1: T1 e2e job exists and is green; tier gate + contract parity gates wired
   into the `ci` chain; the `system` suite runs (or loudly fails) in CI.
2. Wave 2: all seven holes from 01 closed or explicitly deferred by the operator;
   scheduled backups survive unattended operation on active subscriptions (renewal
   proven live); lapsed subscriptions block per policy; public surfaces consistent in
   13 languages.
3. Wave 3: drills scripted; cluster verbs covered; concurrency tests green; final
   ledger delivered.
