import { expect, test } from '@playwright/test';
import { CliMigrateSuite, canRun, M1, M2 } from '../src/utils/cliMigrateHarness';

// Suite 23a (`E2E Full Integration`, ubuntu-24.04 CLI_SUITE leg): the FIRST rdc-driven e2e. The two-VM `repo migrate` routing family is CLI logic — config placement rewrite + `config reconcile` — that renet-side tests structurally cannot cover (07 §1-9). This suite drives the real `rdc` binary via CliRunner and cross-checks the CLI's claims against the bridge (SSH → renet) so the CLI
// asserts are falsifiable, not self-referential. Its sibling 23b (migrate ordering, failed target, gc race) shares the harness in src/utils/cliMigrateHarness.ts and runs in another CI leg (ct-tests.yml gives each its own fleet; the vm:check cli-migrate-23 leg runs the two files one after the other under --workers 1, never together): tests 7 and 8 here run an UNFILTERED `config reconcile` and assert on every conflict in the e2e-cli config, so 23b's repos must never exist on this fleet while they run.
//
// Gated on TWO worker VMs (machine-11 / machine-12).
const APP = 'e2ecli-app';
const APP2 = 'e2ecli-keep';

// Shape of `config reconcile -o json` (the ReconcileReport the command prints — see packages/cli/src/commands/config.ts runReconcileInner).
interface ReconcileJson {
  conflicts: { kind: 'placement' | 'duplicate'; repository: string; message: string }[];
  placementsAccepted: { repository: string; from: string; to: string }[];
}

test.describe
  .serial('rdc migrate routing (CLI-driven) @cli @migrate @landlock', () => {
    test.skip(!canRun, 'Requires two worker VMs (machine-11 / machine-12)');
    test.setTimeout(600_000);

    const s = new CliMigrateSuite([APP, APP2]);

    // Run `config reconcile` with `-o json` and hand back the parsed report. Asserting on the conflicts ARRAY is the honest surface: the old regex (`.not.toMatch(/duplicat|conflict/)`) false-matched the JSON field name "conflicts" even when the array was empty.
    //
    // `-o json` wraps the payload in the standard CLI envelope
    // ({ success, command, data, errors, warnings, metrics } — output.ts
    // formatJson), so the ReconcileReport lives under `.data`, not at top level.
    const reconcileJson = async (...args: string[]): Promise<ReconcileJson> => {
      const { result, json } = await s.cli.runJson<{ data: ReconcileJson }>([
        'config',
        'reconcile',
        ...args,
      ]);
      expect(result.code, `config reconcile ${args.join(' ')}: ${result.stderr}`).toBe(0);
      expect(json?.data, `non-JSON reconcile output: ${result.stdout.slice(0, 400)}`).toBeDefined();
      return json!.data;
    };

    test.beforeAll(async () => {
      await s.setup();
    });

    test.afterAll(async () => {
      await s.teardown();
    });

    test('1. preflight: both machines respond to `rdc machine status` (CliRunner + config wired)', async () => {
      // Read-only probes of two different machines, so they run side by side.
      const [s1, s2] = await Promise.all([
        s.cli.run(['machine', 'status', M1]),
        s.cli.run(['machine', 'status', M2]),
      ]);
      expect(s1.code, `machine status ${M1}: ${s1.stderr}`).toBe(0);
      expect(s2.code, `machine status ${M2}: ${s2.stderr}`).toBe(0);
    });

    test('2. create e2ecli-app on machine-11, bring it up, seed a marker', async () => {
      // TRANSCRIPT-CONFIRMED live: create takes EXACTLY ONE placement flag — -m for a docker repo on the default datastore (this suite), or --datastore for a named one. Passing both is a validation error.
      const create = await s.cli.run(['repo', 'create', APP, '-m', M1, '--size', '1G']);
      expect(create.code, `repo create: ${create.stderr}`).toBe(0);
      s.guids[APP] = await s.guidOf(APP);
      expect(s.guids[APP], 'create registered no GUID in the config').toBeTruthy();
      const up = await s.cli.run(['repo', 'up', `${APP}@${M1}`]);
      expect(up.code, `repo up: ${up.stderr}`).toBe(0);
      // The repo is really on machine-11 (bridge ground truth).
      expect(await s.repoPresentOnBridge(s.w1, APP)).toBe(true);
      expect(await s.placementOf(APP)).toBe(M1);
    });

    test('3. migrate to machine-12 rewrites the config placement', async () => {
      const mig = await s.cli.run(['repo', 'migrate', `${APP}@${M1}`, '--to', M2]);
      expect(mig.code, `migrate: ${(mig.stdout + mig.stderr).slice(-600)}`).toBe(0);
      // The whole point: config now resolves the repo to machine-12.
      expect(await s.placementOf(APP)).toBe(M2);
    });

    test('4. `repo up` with NO machine flag derives machine-12 from the ref and lands there', async () => {
      // Derivation from the ref is the point — no -m flag.
      const up = await s.cli.run(['repo', 'up', APP]);
      expect(up.code, `repo up (derived): ${up.stderr}`).toBe(0);
      expect(await s.repoPresentOnBridge(s.w2, APP)).toBe(true);
    });

    test('5. default migrate left NO repo on the source (machine-11), cross-checked on the bridge', async () => {
      // The CLI removed the source copy; the bridge is ground truth so this is a real absence, not a config-only claim.
      expect(await s.repoPresentOnBridge(s.w1, APP)).toBe(false);
    });

    test('6. `--keep-source` retains both copies; config still points at the target', async () => {
      const create = await s.cli.run(['repo', 'create', APP2, '-m', M1, '--size', '1G']);
      expect(create.code, `repo create keep: ${create.stderr}`).toBe(0);
      s.guids[APP2] = await s.guidOf(APP2);
      await s.cli.run(['repo', 'up', `${APP2}@${M1}`]);

      const mig = await s.cli.run([
        'repo',
        'migrate',
        `${APP2}@${M1}`,
        '--to',
        M2,
        '--keep-source',
      ]);
      expect(mig.code, `migrate --keep-source: ${(mig.stdout + mig.stderr).slice(-600)}`).toBe(0);
      // Config points at the target...
      expect(await s.placementOf(APP2)).toBe(M2);
      // ...but BOTH machines retain the data (that is what --keep-source means).
      expect(await s.repoPresentOnBridge(s.w2, APP2)).toBe(true);
      expect(await s.repoPresentOnBridge(s.w1, APP2)).toBe(true);
    });

    test('7. `config reconcile` reports the keep-source duplicate WITHOUT silently picking a side', async () => {
      // Unfiltered, the scanner sees the declared copy (machine-12) PLUS the stray (machine-11): a "duplicate" conflict, and nothing accepted.
      const full = await reconcileJson();
      expect(full.conflicts).toContainEqual(
        expect.objectContaining({ kind: 'duplicate', repository: APP2 })
      );
      expect(full.placementsAccepted).toEqual([]);

      // A --machine filtered scan sees only machine-11's copy — the partial evidence surfaces as a "placement" conflict, still never a rewrite.
      const filtered = await reconcileJson('--machine', M1);
      expect(filtered.conflicts).toContainEqual(
        expect.objectContaining({ kind: 'placement', repository: APP2 })
      );

      // Reporting only: neither run touched the declaration.
      expect(await s.placementOf(APP2)).toBe(M2);
    });

    test('8. `--accept-observed` refuses the ambiguous duplicate, then resolves a real single-machine drift', async () => {
      // TRANSCRIPT-CONFIRMED live: --accept-observed must run UNFILTERED (no --machine). A partial scan cannot prove a placement is observed on exactly one machine, so the product refuses the combination (exit 2) rather than guess the rewrite direction.
      //
      // Phase 1 — ambiguity is never rewritten. With the keep-source copy on BOTH machines, --accept-observed keeps reporting the duplicate and leaves the declaration alone (spec/04 §4.3: ambiguity errors, never guesses). Only the "declared X, observed on exactly one different Y" drift class carries an acceptance.
      const ambiguous = await reconcileJson('--accept-observed');
      expect(ambiguous.placementsAccepted).toEqual([]);
      expect(ambiguous.conflicts).toContainEqual(
        expect.objectContaining({ kind: 'duplicate', repository: APP2 })
      );
      expect(await s.placementOf(APP2)).toBe(M2);

      // Phase 2 — manufacture that unambiguous drift: remove the DECLARED machine's copy (machine-12) OUT-OF-BAND via the bridge, as an interrupted migrate or manual renet surgery would (the CLI's config is not told). Only machine-11's copy survives.
      const guid = (await s.guidOf(APP2)) ?? s.guids[APP2];
      expect(guid, 'no GUID recorded for the drift setup').toBeTruthy();
      const del = await s.w2.executeViaBridge(
        `sudo renet repository delete --name ${guid} --force --stop-docker`
      );
      expect(del.code, `bridge delete on ${M2}: ${del.stderr.slice(-400)}`).toBe(0);
      expect(await s.repoPresentOnBridge(s.w2, APP2)).toBe(false);
      expect(await s.repoPresentOnBridge(s.w1, APP2)).toBe(true);

      // Phase 3 — the accept: the declaration is rewritten to the single observed machine, visible in the report AND in the config file itself.
      const accepted = await reconcileJson('--accept-observed');
      expect(accepted.placementsAccepted).toContainEqual({
        repository: APP2,
        from: M2,
        to: M1,
      });
      expect(accepted.conflicts).toEqual([]);
      expect(await s.placementOf(APP2)).toBe(M1);

      // Phase 4 — after acceptance, a plain unfiltered reconcile is clean.
      const after = await reconcileJson();
      expect(after.conflicts).toEqual([]);
      expect(after.placementsAccepted).toEqual([]);
    });

    test('9. teardown removes both repos with zero residue on either machine', async () => {
      const d1 = await s.cli.run(['repo', 'delete', APP, '-y']);
      expect(d1.code, `delete ${APP}: ${d1.stderr}`).toBe(0);
      const d2 = await s.cli.run(['repo', 'delete', APP2, '-y']);
      expect(d2.code, `delete ${APP2}: ${d2.stderr}`).toBe(0);
      for (const [runner, label] of s.workerPairs()) {
        expect(await s.repoPresentOnBridge(runner, APP), `${APP} residue on ${label}`).toBe(false);
        expect(await s.repoPresentOnBridge(runner, APP2), `${APP2} residue on ${label}`).toBe(
          false
        );
      }
    });
  });
