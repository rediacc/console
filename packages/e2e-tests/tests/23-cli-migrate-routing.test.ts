import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { expect, test } from '@playwright/test';
import { getSSHPrivateKeyPath } from '@rediacc/provisioning';
import { DS } from '../src/utils/backup/chunkCliHarness';
import { CliRunner } from '../src/utils/CliRunner';
import { loginCliToAccount } from '../src/utils/licence';
import { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';

// Suite 23 (`E2E Workers`, CLI_SUITE leg): the FIRST rdc-driven e2e. The two-VM `repo migrate` routing family is CLI logic — config placement rewrite + `config reconcile` — that renet-side tests structurally cannot cover (07 §1-9). This suite drives the real `rdc` binary via CliRunner and cross-checks the CLI's claims against the bridge (SSH → renet) so the CLI asserts are
// falsifiable, not self-referential.
//
// NOT YET ON CI: the ct-tests.yml ubuntu leg does not set CLI_SUITE=1 yet. Before
// enabling it, the exact create/datastore argv + the machine-registration/SSH wiring in beforeAll must be transcribed from the wave round-log transcript and validated on a local two-worker fleet (plan phase 5; README "Deliberately not in CI"). The scenario SHAPE and the falsifiable asserts below are final; the argv marked TRANSCRIPT-CONFIRM is the best-derived form from the CLI
// source.
//
// Gated on TWO worker VMs (machine-11 / machine-12).
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
const canRun = workers.length >= 2;

const NET_BASE = process.env.VM_NET_BASE ?? '192.168.111';
const M1 = 'machine-11';
const M2 = 'machine-12';
const M1_IP = `${NET_BASE}.${workers[0] ?? '11'}`;
const M2_IP = `${NET_BASE}.${workers[1] ?? '12'}`;
// SSH into the ops VMs: the key the bridge harness's outer hop uses, resolved by the same function (RENET_DATA_DIR, then $RUNNER_TEMP/renet under CI, then ~/.renet), overridable for a non-default layout.
const SSH_KEY = process.env.E2E_SSH_KEY ?? getSSHPrivateKeyPath();
// The ops VMs are cloud-inited with the INVOKING user (the whole bridge harness connects as process.env.USER — see RenetFunctionsTestRunner/ InfrastructureManager), and the staged key authenticates that user, not root. TRANSCRIPT-CONFIRMED live: as root, auth fails ("all configured authentication methods failed") before anything else can run.
const SSH_USER = process.env.E2E_SSH_USER ?? process.env.USER ?? 'root';

const APP = 'e2ecli-app';
const APP2 = 'e2ecli-keep';
// Box M1 of agent/plans/PLAN-jobs-backup-real-machine-tests.md: one repo per scenario (ordering, failed target, gc race).
const APP_ORDER = 'e2ecli-order';
const APP_FAIL = 'e2ecli-fail';
const APP_GC = 'e2ecli-gc';
const EXTRA_APPS = [APP_ORDER, APP_FAIL, APP_GC];

// The slice of rdc's config-v3 file these helpers read (placement + GUID).
interface CliConfigFile {
  resources?: {
    repositories?: Record<
      string,
      {
        grand?: string;
        placement?: { machine?: string };
        tags?: Record<string, { repositoryGuid?: string }>;
      }
    >;
  };
}

// renet writes one JSON object per line on stdout ({"gc_result": {...}} per candidate, {"gc_summary": {...}} last; private/renet cmd/renet/repository_gc.go runGC). Logrus output rides stderr, so only stdout lines that parse as those objects count.
interface GcResult {
  guid: string;
  status: string;
  reason?: string;
}
interface GcSummary {
  total: number;
  deleted: number;
  skipped: number;
  failed: number;
}
interface GcRun {
  code: number;
  raw: string;
  results: GcResult[];
  summary?: GcSummary;
}

const parseGcLine = (line: string): { gc_result?: GcResult; gc_summary?: GcSummary } => {
  if (!line.trim().startsWith('{')) return {};
  try {
    return JSON.parse(line) as { gc_result?: GcResult; gc_summary?: GcSummary };
  } catch {
    return {};
  }
};

const parseGcOutput = (stdout: string, stderr: string): Omit<GcRun, 'code'> => {
  const parsed = stdout.split('\n').map(parseGcLine);
  return {
    raw: `${stdout}\n${stderr}`.slice(-600),
    results: parsed.flatMap((p) => (p.gc_result ? [p.gc_result] : [])),
    summary: parsed.find((p) => p.gc_summary)?.gc_summary,
  };
};

test.describe
  .serial('rdc migrate routing (CLI-driven) @cli @migrate', () => {
    test.skip(!canRun, 'Requires two worker VMs (machine-11 / machine-12)');
    test.setTimeout(600_000);

    let cli: CliRunner;
    let w1: RenetFunctionsTestRunner;
    let w2: RenetFunctionsTestRunner;

    // Placement the config claims for a repo, read from rdc's OWN config file — the exact artifact migrate mutates. TRANSCRIPT-CONFIRMED live: `repo list` requires -m (it queries a machine, merging live state), so the file read is both the only bare surface and the honest one for a pure config-placement assert.
    const readCliConfig = async (): Promise<CliConfigFile> =>
      JSON.parse(
        await readFile(path.join(os.homedir(), '.config', 'rediacc', 'e2e-cli.json'), 'utf8')
      ) as CliConfigFile;

    const placementOf = async (name: string): Promise<string | undefined> =>
      (await readCliConfig()).resources?.repositories?.[name]?.placement?.machine;

    const guidOf = async (name: string): Promise<string | undefined> => {
      const fam = (await readCliConfig()).resources?.repositories?.[name];
      if (!fam) return undefined;
      return fam.tags?.[fam.grand ?? 'latest']?.repositoryGuid;
    };

    // GUIDs remembered at create time, so the residue check still works if a config entry is ever archived away.
    const guids: Record<string, string | undefined> = {};
    // Every GUID the M1 cases create (repos and the gc commit), swept by GUID in afterAll.
    const extraGuids = new Set<string>();

    // Bridge-side cross-check: does renet on <runner> report the repo present? The CLI claims placement; the bridge is ground truth (07 §9). TRANSCRIPT-CONFIRMED live: storage speaks GUID (#93) — the raw repository_list carries the GUID as the repo's name, never the config name — and with --debug the listing rides the logrus stream (stderr), so both channels are grepped.
    const repoPresentOnBridge = async (
      runner: RenetFunctionsTestRunner,
      name: string
    ): Promise<boolean> => {
      const guid = (await guidOf(name).catch(() => undefined)) ?? guids[name];
      if (!guid) return false;
      const res = await runner.executeViaBridge(
        'renet functions once --test-mode --debug --function repository_list'
      );
      return res.code === 0 && (res.stdout + res.stderr).includes(guid);
    };

    const deleteAppQuietly = async (name: string): Promise<void> => {
      await cli.run(['repo', 'delete', name, '-y']).catch(() => undefined);
    };

    // Shape of `config reconcile -o json` (the ReconcileReport the command prints — see packages/cli/src/commands/config.ts runReconcileInner).
    interface ReconcileJson {
      conflicts: { kind: 'placement' | 'duplicate'; repository: string; message: string }[];
      placementsAccepted: { repository: string; from: string; to: string }[];
    }

    // Run `config reconcile` with `-o json` and hand back the parsed report. Asserting on the conflicts ARRAY is the honest surface: the old regex (`.not.toMatch(/duplicat|conflict/)`) false-matched the JSON field name "conflicts" even when the array was empty.
    //
    // `-o json` wraps the payload in the standard CLI envelope
    // ({ success, command, data, errors, warnings, metrics } — output.ts
    // formatJson), so the ReconcileReport lives under `.data`, not at top level.
    const reconcileJson = async (...args: string[]): Promise<ReconcileJson> => {
      const { result, json } = await cli.runJson<{ data: ReconcileJson }>([
        'config',
        'reconcile',
        ...args,
      ]);
      expect(result.code, `config reconcile ${args.join(' ')}: ${result.stderr}`).toBe(0);
      expect(json?.data, `non-JSON reconcile output: ${result.stdout.slice(0, 400)}`).toBeDefined();
      return json!.data;
    };

    test.beforeAll(async () => {
      cli = CliRunner.create();
      w1 = RenetFunctionsTestRunner.forWorker(1);
      w2 = RenetFunctionsTestRunner.forWorker(2);

      // Isolated e2e-cli config (NEVER the default) + register both machines. Recreated from SCRATCH each run: the config records the fleet's host keys, and a config that outlives an ops down/up carries the PREVIOUS fleet's keys — every connection then fails host-key verification (found live: preflight red while the bridge probes were green). TRANSCRIPT-CONFIRM: SSH key/user +
      // whether a datastore attach step is needed before repo create in the config-v3 model.
      await CliRunner.resetConfig();
      await cli.initConfig(SSH_KEY);
      // renet enforces licensing, so `repo create` must issue a licence: the config logs in to the account server first.
      const login = await loginCliToAccount(cli);
      expect(login.code, `subscription login: ${login.stderr.slice(-600)}`).toBe(0);
      await cli.addMachine(M1, M1_IP, SSH_USER);
      await cli.addMachine(M2, M2_IP, SSH_USER);

      // Clean any residue from a prior aborted run.
      await deleteAppQuietly(APP);
      await deleteAppQuietly(APP2);
      for (const extra of EXTRA_APPS) await deleteAppQuietly(extra);
    });

    const workerPairs = (): (readonly [RenetFunctionsTestRunner, string])[] => [
      [w1, M1],
      [w2, M2],
    ];

    // Every repo name and every GUID the suite created, on both machines. A probe that throws counts as residue: an unreadable machine proves nothing.
    const residueOn = async (
      runner: RenetFunctionsTestRunner,
      label: string
    ): Promise<string[]> => {
      const residue: string[] = [];
      for (const name of [APP, APP2, ...EXTRA_APPS]) {
        if (await repoPresentOnBridge(runner, name).catch(() => true)) {
          residue.push(`${name} on ${label}`);
        }
      }
      for (const guid of extraGuids) {
        if (await imageExists(runner, guid).catch(() => true)) {
          residue.push(`image ${guid} on ${label}`);
        }
      }
      return residue;
    };
    const residueAfterTeardown = async (): Promise<string[]> => [
      ...(await residueOn(w1, M1)),
      ...(await residueOn(w2, M2)),
    ];

    test.afterAll(async () => {
      for (const name of [APP, APP2, ...EXTRA_APPS]) await deleteAppQuietly(name);
      // The M1 cases can leave a stray source copy or a mounted commit the CLI delete never sees: remove them by GUID on both machines.
      for (const guid of extraGuids) {
        for (const [runner] of workerPairs()) {
          await runner
            .executeViaBridge(
              `sudo renet repository unmount --name ${guid} --datastore ${DS}; sudo renet repository delete --name ${guid} --force --stop-docker --datastore ${DS}`
            )
            .catch(() => undefined);
        }
      }
      expect(await residueAfterTeardown(), 'residue survived teardown').toEqual([]);
    });

    test('1. preflight: both machines respond to `rdc machine status` (CliRunner + config wired)', async () => {
      const s1 = await cli.run(['machine', 'status', M1]);
      expect(s1.code, `machine status ${M1}: ${s1.stderr}`).toBe(0);
      const s2 = await cli.run(['machine', 'status', M2]);
      expect(s2.code, `machine status ${M2}: ${s2.stderr}`).toBe(0);
    });

    test('2. create e2ecli-app on machine-11, bring it up, seed a marker', async () => {
      // TRANSCRIPT-CONFIRMED live: create takes EXACTLY ONE placement flag — -m for a docker repo on the default datastore (this suite), or --datastore for a named one. Passing both is a validation error.
      const create = await cli.run(['repo', 'create', APP, '-m', M1, '--size', '1G']);
      expect(create.code, `repo create: ${create.stderr}`).toBe(0);
      guids[APP] = await guidOf(APP);
      expect(guids[APP], 'create registered no GUID in the config').toBeTruthy();
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
      // The CLI removed the source copy; the bridge is ground truth so this is a real absence, not a config-only claim.
      expect(await repoPresentOnBridge(w1, APP)).toBe(false);
    });

    test('6. `--keep-source` retains both copies; config still points at the target', async () => {
      const create = await cli.run(['repo', 'create', APP2, '-m', M1, '--size', '1G']);
      expect(create.code, `repo create keep: ${create.stderr}`).toBe(0);
      guids[APP2] = await guidOf(APP2);
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
      expect(await placementOf(APP2)).toBe(M2);
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
      expect(await placementOf(APP2)).toBe(M2);

      // Phase 2 — manufacture that unambiguous drift: remove the DECLARED machine's copy (machine-12) OUT-OF-BAND via the bridge, as an interrupted migrate or manual renet surgery would (the CLI's config is not told). Only machine-11's copy survives.
      const guid = (await guidOf(APP2)) ?? guids[APP2];
      expect(guid, 'no GUID recorded for the drift setup').toBeTruthy();
      const del = await w2.executeViaBridge(
        `sudo renet repository delete --name ${guid} --force --stop-docker`
      );
      expect(del.code, `bridge delete on ${M2}: ${del.stderr.slice(-400)}`).toBe(0);
      expect(await repoPresentOnBridge(w2, APP2)).toBe(false);
      expect(await repoPresentOnBridge(w1, APP2)).toBe(true);

      // Phase 3 — the accept: the declaration is rewritten to the single observed machine, visible in the report AND in the config file itself.
      const accepted = await reconcileJson('--accept-observed');
      expect(accepted.placementsAccepted).toContainEqual({
        repository: APP2,
        from: M2,
        to: M1,
      });
      expect(accepted.conflicts).toEqual([]);
      expect(await placementOf(APP2)).toBe(M1);

      // Phase 4 — after acceptance, a plain unfiltered reconcile is clean.
      const after = await reconcileJson();
      expect(after.conflicts).toEqual([]);
      expect(after.placementsAccepted).toEqual([]);
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

    // ---- Box M1: ordering of the migrate job path, and the gc re-check ----

    const imagePath = (guid: string): string => `${DS}/repositories/${guid}`;
    const imageExists = async (runner: RenetFunctionsTestRunner, guid: string): Promise<boolean> =>
      (await runner.executeViaBridge(`sudo test -e ${imagePath(guid)}`)).code === 0;
    const nowNs = async (runner: RenetFunctionsTestRunner): Promise<bigint> => {
      const res = await runner.executeViaBridge('date +%s%N');
      expect(res.code, `date on a worker: ${res.stderr}`).toBe(0);
      return BigInt(res.stdout.trim().split('\n').pop() ?? '0');
    };
    // Rediaccfile functions run under the sandbox, whose write access is the repository, so the stamp lives there: `up()` starts in the repository root.
    const UP_STAMP_FILE = '.e2e-m1-up';
    const upStamp = (guid: string): string => `${DS}/mounts/${guid}/${UP_STAMP_FILE}`;
    const stopFile = (guid: string): string => `/var/tmp/e2e-m1-stop-${guid}`;
    const goneFile = (guid: string): string => `/var/tmp/e2e-m1-gone-${guid}`;
    // How long up() holds after its first stamp. The last stamp marks the END of the target's bring-up, so a source delete that overlaps the bring-up lands before it.
    const UP_HOLD_S = 5;

    // Create a repo on machine-11, bring it up and install a Rediaccfile whose `up()` runs the body `upBody(guid)` returns, on whichever machine brings the repo up. The file lives in the repo image, so migrate carries it to the target.
    const seedRepo = async (name: string, upBody: (guid: string) => string): Promise<string> => {
      const create = await cli.run(['repo', 'create', name, '-m', M1, '--size', '1G']);
      expect(create.code, `repo create ${name}: ${create.stderr}`).toBe(0);
      const guid = await guidOf(name);
      expect(guid, `create registered no GUID for ${name}`).toBeTruthy();
      guids[name] = guid;
      extraGuids.add(guid!);
      const up = await cli.run(['repo', 'up', `${name}@${M1}`]);
      expect(up.code, `repo up ${name}: ${up.stderr}`).toBe(0);
      const file = `up() {\n${upBody(guid!)}\n}\n\ndown() {\n    true\n}\n`;
      const wrote = await w1.writeFileToRepository(guid!, 'Rediaccfile', file, DS);
      expect(wrote.code, `Rediaccfile write: ${wrote.stderr}`).toBe(0);
      return guid!;
    };

    test('10. migrate deletes the source only AFTER the target is up (observed on both machines)', async () => {
      // The CLI migrate dispatches the `repository_migrate` job verb on the source machine: that machine's renet must register it, or the job path under test cannot exist there.
      const registry = await w1.executeViaBridge('renet functions list-functions --internal');
      expect(registry.code, `functions list: ${registry.stderr.slice(-400)}`).toBe(0);
      expect(registry.stdout, 'machine-11 renet does not register repository_migrate').toContain(
        'repository_migrate'
      );

      // `up()` appends a nanosecond timestamp to a host file, holds, then appends another: the last stamp is the end of the target's bring-up, read off the target itself.
      const guid = await seedRepo(
        APP_ORDER,
        () =>
          `    date +%s%N >> ${UP_STAMP_FILE}\n    sleep ${UP_HOLD_S}\n    date +%s%N >> ${UP_STAMP_FILE}`
      );

      // Clock offset between the workers, so both timestamps compare on one scale. Reading machine-12 between two machine-11 reads brackets it: the offset is b minus the midpoint, and the measured error is half the bracket (one SSH round trip), subtracted from the margin below.
      const a = await nowNs(w1);
      const b = await nowNs(w2);
      const c = await nowNs(w1);
      const offsetNs = b - (a + c) / 2n;
      const errNs = (c - a) / 2n + 1n;

      // Watch the SOURCE image from the machine while the migrate runs: the first moment it is gone. The poll lag (about 0.1 s) only delays the reading, so it can hide a violation by that much; up() holds ${UP_HOLD_S} s, far above it. The loop ends at the stop file, which the finally below writes, so a failed assertion never leaves it running.
      await w1.executeViaBridge(`sudo rm -f ${stopFile(guid)} ${goneFile(guid)}`);
      // Base64, because the bridge's shell expands `$(...)` before the worker sees the command.
      const watchScript = `for i in $(seq 1 3000); do sudo test -e ${imagePath(guid)} || { date +%s%N > ${goneFile(guid)}; exit 0; }; [ -e ${stopFile(guid)} ] && { echo stopped; exit 0; }; sleep 0.1; done; echo timeout`;
      const watcher = w1.executeViaBridge(
        `echo ${Buffer.from(watchScript).toString('base64')} | base64 -d | bash`
      );
      let gone = '';
      let watcherOutput = '';
      try {
        const mig = await cli.run(['repo', 'migrate', `${APP_ORDER}@${M1}`, '--to', M2]);
        expect(mig.code, `migrate: ${(mig.stdout + mig.stderr).slice(-800)}`).toBe(0);
      } finally {
        await w1.executeViaBridge(`touch ${stopFile(guid)}`);
        const watched = await watcher;
        watcherOutput = `code ${watched.code}: ${watched.stdout} ${watched.stderr}`.slice(-400);
        gone = (await w1.executeViaBridge(`cat ${goneFile(guid)}`)).stdout.trim();
        await w1.executeViaBridge(`rm -f ${stopFile(guid)} ${goneFile(guid)}`);
      }
      expect(
        gone,
        `the source image never disappeared during the migrate (watcher ${watcherOutput})`
      ).toMatch(/^\d+$/);
      const sourceGoneNs = BigInt(gone) + offsetNs;

      const stamps = await w2.executeViaBridge(`sudo cat ${upStamp(guid)}`);
      expect(stamps.code, 'the target never ran up() (no stamp on machine-12)').toBe(0);
      const stampLines = stamps.stdout.trim().split('\n');
      const targetUpNs = BigInt(stampLines.at(-1) ?? '0');
      expect(
        stampLines.length,
        'up() on machine-12 did not run to its end stamp'
      ).toBeGreaterThanOrEqual(2);
      expect(targetUpNs > 0n).toBe(true);

      expect(
        sourceGoneNs - errNs > targetUpNs,
        `source deleted at ${sourceGoneNs} (machine-12 clock, error ${errNs} ns) before the target finished coming up at ${targetUpNs}`
      ).toBe(true);
      // End state: the target holds the repo, the source does not.
      expect(await imageExists(w2, guid)).toBe(true);
      expect(await imageExists(w1, guid)).toBe(false);
    });

    test('11. a migrate whose target fails to come up keeps the source intact', async () => {
      const w1Host = (await w1.executeViaBridge('hostname')).stdout.trim();
      const w2Host = (await w2.executeViaBridge('hostname')).stdout.trim();
      expect(w2Host, 'machine-12 reported no hostname').not.toBe('');
      expect(
        w2Host,
        'machine-11 and machine-12 share a hostname, so the failure cannot be targeted'
      ).not.toBe(w1Host);
      // `up()` fails on machine-12 only, so the source job and the source bring-up succeed and the target's repo up is the step that fails.
      const guid = await seedRepo(
        APP_FAIL,
        () =>
          `    if [ "$(hostname)" = "${w2Host}" ]; then echo "e2e: forced target failure" >&2; return 1; fi`
      );
      expect(await imageExists(w1, guid)).toBe(true);

      const mig = await cli.run(['repo', 'migrate', `${APP_FAIL}@${M1}`, '--to', M2]);
      expect(mig.code, 'migrate reported success though the target could not come up').not.toBe(0);

      // The machine, not the CLI's message, is the evidence: the source copy was never deleted, and the data did reach the target.
      expect(await imageExists(w1, guid), 'source deleted although the target never came up').toBe(
        true
      );
      expect(await repoPresentOnBridge(w1, APP_FAIL)).toBe(true);
      expect(await imageExists(w2, guid)).toBe(true);
    });

    test('12. repository_gc keeps a candidate that was mounted between the list and the delete', async () => {
      const fork = await seedRepo(APP_GC, () => '    true');
      const commit = randomUUID();
      extraGuids.add(commit);
      const committed = await w1.repositoryCommit(fork, commit, 'e2e gc race', DS);
      expect(committed.code, `commit: ${w1.getCombinedOutput(committed).slice(-600)}`).toBe(0);

      const gcRun = async (): Promise<GcRun> => {
        const res = await w1.executeViaBridge(
          `sudo renet repository gc --candidates ${commit}@${DS} --datastore ${DS}`
        );
        return { code: res.code, ...parseGcOutput(res.stdout, res.stderr) };
      };

      // The list step: the commit is present and unmapped, so a client building its candidate set now includes it.
      expect(await imageExists(w1, commit), 'the commit image is absent before the race').toBe(
        true
      );
      const mapped = await w1.executeViaBridge(`test -e /dev/mapper/${commit}`);
      expect(mapped.code, 'the commit is already mapped before the race').not.toBe(0);

      // The race: a device-mapper entry appears AFTER the candidate list was taken and BEFORE gc runs, and `repository gc --candidates` re-checks the machine rather than trusting the list. renet refuses to mount an immutable commit, so a real mapping cannot be made through `repository_mount`: a zero-target entry under the commit's name is the state gc reads, and it holds no data.
      const map = await w1.executeViaBridge(`sudo dmsetup create ${commit} --table '0 8 zero'`);
      expect(map.code, `dmsetup create: ${w1.getCombinedOutput(map).slice(-600)}`).toBe(0);

      const kept = await gcRun();
      expect(kept.code, `gc failed instead of skipping: ${kept.raw}`).toBe(0);
      expect(kept.results, kept.raw).toEqual([
        expect.objectContaining({ guid: commit, status: 'skipped', reason: 'mounted' }),
      ]);
      expect(kept.summary, kept.raw).toMatchObject({ total: 1, deleted: 0, skipped: 1, failed: 0 });
      expect(await imageExists(w1, commit), 'gc deleted a mounted commit').toBe(true);

      // Control: with the entry gone, the same call deletes it, so the skip above came from the mapping and from nothing else.
      const unmap = await w1.executeViaBridge(`sudo dmsetup remove ${commit}`);
      expect(unmap.code, `dmsetup remove: ${w1.getCombinedOutput(unmap).slice(-600)}`).toBe(0);
      const deleted = await gcRun();
      expect(deleted.code, deleted.raw).toBe(0);
      expect(deleted.results, deleted.raw).toEqual([
        expect.objectContaining({ guid: commit, status: 'deleted' }),
      ]);
      expect(deleted.summary, deleted.raw).toMatchObject({ total: 1, deleted: 1, failed: 0 });
      expect(await imageExists(w1, commit)).toBe(false);
    });
  });
