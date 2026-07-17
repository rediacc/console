import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';
import { CliRunner } from '../src/utils/CliRunner';

// Suite 23 (`E2E Workers`, CLI_SUITE leg): the FIRST rdc-driven e2e. The two-VM
// `repo migrate` routing family is CLI logic — config placement rewrite +
// `config reconcile` — that renet-side tests structurally cannot cover (07 §1-9).
// This suite drives the real `rdc` binary via CliRunner and cross-checks the
// CLI's claims against the bridge (SSH → renet) so the CLI asserts are
// falsifiable, not self-referential.
//
// NOT YET ON CI: the ct-tests.yml ubuntu leg does not set CLI_SUITE=1 yet. Before
// enabling it, the exact create/datastore argv + the machine-registration/SSH
// wiring in beforeAll must be transcribed from the wave round-log transcript and
// validated on a local two-worker fleet (plan phase 5; README "Deliberately not
// in CI"). The scenario SHAPE and the falsifiable asserts below are final; the
// argv marked TRANSCRIPT-CONFIRM is the best-derived form from the CLI source.
//
// Gated on TWO worker VMs (machine-11 / machine-12).
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
const canRun = workers.length >= 2;

const NET_BASE = process.env.VM_NET_BASE ?? '192.168.111';
const M1 = 'machine-11';
const M2 = 'machine-12';
const M1_IP = `${NET_BASE}.${workers[0] ?? '11'}`;
const M2_IP = `${NET_BASE}.${workers[1] ?? '12'}`;
// SSH into the ops VMs: same key the bridge harness's outer hop uses
// (RENET_DATA_DIR/staging/.ssh/id_rsa), overridable for a non-default layout.
const SSH_KEY =
  process.env.E2E_SSH_KEY ??
  `${process.env.RENET_DATA_DIR ?? `${process.env.HOME}/.rediacc`}/staging/.ssh/id_rsa`;
// The ops VMs are cloud-inited with the INVOKING user (the whole bridge
// harness connects as process.env.USER — see BridgeTestRunner/
// InfrastructureManager), and the staged key authenticates that user, not
// root. TRANSCRIPT-CONFIRMED live: as root, auth fails ("all configured
// authentication methods failed") before anything else can run.
const SSH_USER = process.env.E2E_SSH_USER ?? process.env.USER ?? 'root';

const APP = 'e2ecli-app';
const APP2 = 'e2ecli-keep';

interface RepoListEntry {
  name: string;
  machine?: string;
  guid?: string;
}

test.describe
  .serial('rdc migrate routing (CLI-driven) @cli @migrate', () => {
    test.skip(!canRun, 'Requires two worker VMs (machine-11 / machine-12)');
    test.setTimeout(600_000);

    let cli: CliRunner;
    let w1: BridgeTestRunner;
    let w2: BridgeTestRunner;

    // Placement the config resolves for a repo, read from the CLI's own JSON
    // output — this is the "placement rewrite" the migrate routing must produce.
    const placementOf = async (name: string): Promise<string | undefined> => {
      const { json } = await cli.runJson<RepoListEntry[]>(['repo', 'list']);
      const entry = Array.isArray(json) ? json.find((r) => r.name === name) : undefined;
      return entry?.machine;
    };

    // Bridge-side cross-check: does renet on <runner> report the repo present?
    // The CLI claims placement; the bridge is ground truth (07 §9).
    const repoPresentOnBridge = async (
      runner: BridgeTestRunner,
      name: string
    ): Promise<boolean> => {
      const res = await runner.executeViaBridge(
        'renet functions once --test-mode --debug --function repository_list'
      );
      return res.code === 0 && res.stdout.includes(name);
    };

    const deleteAppQuietly = async (name: string): Promise<void> => {
      await cli.run(['repo', 'delete', name, '-y']).catch(() => undefined);
    };

    test.beforeAll(async () => {
      cli = CliRunner.create();
      w1 = BridgeTestRunner.forWorker(1);
      w2 = BridgeTestRunner.forWorker(2);

      // Isolated e2e-cli config (NEVER the default) + register both machines.
      // Recreated from SCRATCH each run: the config records the fleet's host
      // keys, and a config that outlives an ops down/up carries the PREVIOUS
      // fleet's keys — every connection then fails host-key verification
      // (found live: preflight red while the bridge probes were green).
      // TRANSCRIPT-CONFIRM: SSH key/user + whether a datastore attach step is
      // needed before repo create in the config-v3 model.
      await CliRunner.resetConfig();
      await cli.initConfig(SSH_KEY);
      await cli.addMachine(M1, M1_IP, SSH_USER);
      await cli.addMachine(M2, M2_IP, SSH_USER);

      // Clean any residue from a prior aborted run.
      await deleteAppQuietly(APP);
      await deleteAppQuietly(APP2);
    });

    test.afterAll(async () => {
      await deleteAppQuietly(APP);
      await deleteAppQuietly(APP2);
      // Zero-residue: neither machine keeps a repo the suite created.
      const onW1 = await repoPresentOnBridge(w1, APP).catch(() => false);
      const onW2 = await repoPresentOnBridge(w2, APP).catch(() => false);
      expect(onW1 || onW2, 'e2ecli-app residue survived teardown').toBe(false);
    });

    test('1. preflight: both machines respond to `rdc machine status` (CliRunner + config wired)', async () => {
      const s1 = await cli.run(['machine', 'status', M1]);
      expect(s1.code, `machine status ${M1}: ${s1.stderr}`).toBe(0);
      const s2 = await cli.run(['machine', 'status', M2]);
      expect(s2.code, `machine status ${M2}: ${s2.stderr}`).toBe(0);
    });

    test('2. create e2ecli-app on machine-11, bring it up, seed a marker', async () => {
      // TRANSCRIPT-CONFIRMED live: create takes EXACTLY ONE placement flag —
      // -m for a docker repo on the default datastore (this suite), or
      // --datastore for a named one. Passing both is a validation error.
      const create = await cli.run(['repo', 'create', APP, '-m', M1, '--size', '1G']);
      expect(create.code, `repo create: ${create.stderr}`).toBe(0);
      const up = await cli.run(['repo', 'up', `${APP}@${M1}`]);
      expect(up.code, `repo up: ${up.stderr}`).toBe(0);
      // The repo is really on machine-11 (bridge ground truth).
      expect(await repoPresentOnBridge(w1, APP)).toBe(true);
      expect(await placementOf(APP)).toBe(M1);
    });

    test('3. migrate to machine-12 rewrites the config placement', async () => {
      const mig = await cli.run(['repo', 'migrate', `${APP}@${M1}`, '--to', M2]);
      expect(mig.code, `migrate: ${(mig.stdout + mig.stderr).slice(-600)}`).toBe(0);
      // The whole point: config now resolves the repo to machine-12.
      expect(await placementOf(APP)).toBe(M2);
    });

    test('4. `repo up` with NO machine flag derives machine-12 from the ref and lands there', async () => {
      // Derivation from the ref is the point — no -m flag.
      const up = await cli.run(['repo', 'up', APP]);
      expect(up.code, `repo up (derived): ${up.stderr}`).toBe(0);
      expect(await repoPresentOnBridge(w2, APP)).toBe(true);
    });

    test('5. default migrate left NO repo on the source (machine-11), cross-checked on the bridge', async () => {
      // The CLI removed the source copy; the bridge is ground truth so this is a
      // real absence, not a config-only claim.
      expect(await repoPresentOnBridge(w1, APP)).toBe(false);
    });

    test('6. `--keep-source` retains both copies; config still points at the target', async () => {
      const create = await cli.run(['repo', 'create', APP2, '-m', M1, '--size', '1G']);
      expect(create.code, `repo create keep: ${create.stderr}`).toBe(0);
      await cli.run(['repo', 'up', `${APP2}@${M1}`]);

      const mig = await cli.run(['repo', 'migrate', `${APP2}@${M1}`, '--to', M2, '--keep-source']);
      expect(mig.code, `migrate --keep-source: ${(mig.stdout + mig.stderr).slice(-600)}`).toBe(0);
      // Config points at the target...
      expect(await placementOf(APP2)).toBe(M2);
      // ...but BOTH machines retain the data (that is what --keep-source means).
      expect(await repoPresentOnBridge(w2, APP2)).toBe(true);
      expect(await repoPresentOnBridge(w1, APP2)).toBe(true);
    });

    test('7. `config reconcile` reports the keep-source duplicate WITHOUT silently picking a side', async () => {
      const rec = await cli.run(['config', 'reconcile', '--machine', M1]);
      // The duplicate must surface (the source copy from test 6 still exists).
      // A silent success that picked a side is the failure mode we guard against.
      expect((rec.stdout + rec.stderr).toLowerCase()).toMatch(/duplicat|conflict|observed on/);
    });

    test('8. `--accept-observed` resolves the duplicate in the observed direction', async () => {
      const rec = await cli.run(['config', 'reconcile', '--machine', M1, '--accept-observed']);
      expect(rec.code, `reconcile --accept-observed: ${rec.stderr}`).toBe(0);
      // After acceptance a plain reconcile no longer reports the duplicate.
      const again = await cli.run(['config', 'reconcile', '--machine', M1]);
      expect((again.stdout + again.stderr).toLowerCase()).not.toMatch(/duplicat|conflict/);
    });

    test('9. teardown removes both repos with zero residue on either machine', async () => {
      const d1 = await cli.run(['repo', 'delete', APP, '-y']);
      expect(d1.code, `delete ${APP}: ${d1.stderr}`).toBe(0);
      const d2 = await cli.run(['repo', 'delete', APP2, '-y']);
      expect(d2.code, `delete ${APP2}: ${d2.stderr}`).toBe(0);
      for (const [runner, label] of [
        [w1, M1],
        [w2, M2],
      ] as const) {
        expect(await repoPresentOnBridge(runner, APP), `${APP} residue on ${label}`).toBe(false);
        expect(await repoPresentOnBridge(runner, APP2), `${APP2} residue on ${label}`).toBe(false);
      }
    });
  });
