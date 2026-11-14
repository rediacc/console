import { readFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { expect } from '@playwright/test';
import { getSSHPrivateKeyPath } from '@rediacc/provisioning';
import { DS } from './backup/chunkCliHarness';
import { CliRunner } from './CliRunner';
import { skipWithoutLandlock } from './landlock';
import { loginCliToAccount } from './licence';
import { RenetFunctionsTestRunner } from './renet-functions/RenetFunctionsTestRunner';

// Shared by suites 23a (migrate routing, keep-source, reconcile) and 23b (migrate ordering, failed target, gc race): the two-worker fleet wiring, the isolated e2e-cli config, the config and bridge probes, and a teardown that removes exactly the repositories one suite names.
//
// Both suites write the same e2e-cli config and 23a asserts that an UNFILTERED `config reconcile` reports no conflict, so the two must never run at the same time against one fleet. CI runs them in separate jobs, each on its own fleet; one local playwright run takes them in turn (the test-23 project, one worker).

export const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
export const canRun = workers.length >= 2;

const NET_BASE = process.env.VM_NET_BASE ?? '192.168.111';
export const M1 = 'machine-11';
export const M2 = 'machine-12';
const M1_IP = `${NET_BASE}.${workers[0] ?? '11'}`;
const M2_IP = `${NET_BASE}.${workers[1] ?? '12'}`;
// SSH into the ops VMs: the key the bridge harness's outer hop uses, resolved by the same function (RENET_DATA_DIR, then $RUNNER_TEMP/renet under CI, then ~/.renet), overridable for a non-default layout.
const SSH_KEY = process.env.E2E_SSH_KEY ?? getSSHPrivateKeyPath();
// The ops VMs are cloud-inited with the INVOKING user (the whole bridge harness connects as process.env.USER — see RenetFunctionsTestRunner/ InfrastructureManager), and the staged key authenticates that user, not root. TRANSCRIPT-CONFIRMED live: as root, auth fails ("all configured authentication methods failed") before anything else can run.
const SSH_USER = process.env.E2E_SSH_USER ?? process.env.USER ?? 'root';

export { DS };

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

export const imagePath = (guid: string): string => `${DS}/repositories/${guid}`;

/** One suite's fleet, config and probes. `apps` are the repository names the suite creates; its teardown removes those and nothing else. */
export class CliMigrateSuite {
  cli!: CliRunner;
  w1!: RenetFunctionsTestRunner;
  w2!: RenetFunctionsTestRunner;
  // GUIDs remembered at create time, so the residue check still works if a config entry is ever archived away.
  readonly guids: Record<string, string | undefined> = {};
  // Every GUID that can outlive a CLI delete (seeded repos and commits), swept by GUID in teardown.
  readonly extraGuids = new Set<string>();

  constructor(private readonly apps: readonly string[]) {}

  // Placement the config claims for a repo, read from rdc's OWN config file — the exact artifact migrate mutates. TRANSCRIPT-CONFIRMED live: `repo list` requires -m (it queries a machine, merging live state), so the file read is both the only bare surface and the honest one for a pure config-placement assert.
  readonly readCliConfig = async (): Promise<CliConfigFile> =>
    JSON.parse(
      await readFile(path.join(os.homedir(), '.config', 'rediacc', 'e2e-cli.json'), 'utf8')
    ) as CliConfigFile;

  readonly placementOf = async (name: string): Promise<string | undefined> =>
    (await this.readCliConfig()).resources?.repositories?.[name]?.placement?.machine;

  readonly guidOf = async (name: string): Promise<string | undefined> => {
    const fam = (await this.readCliConfig()).resources?.repositories?.[name];
    if (!fam) return undefined;
    return fam.tags?.[fam.grand ?? 'latest']?.repositoryGuid;
  };

  // Bridge-side cross-check: does renet on <runner> report the repo present? The CLI claims placement; the bridge is ground truth (07 §9). TRANSCRIPT-CONFIRMED live: storage speaks GUID (#93) — the raw repository_list carries the GUID as the repo's name, never the config name — and with --debug the listing rides the logrus stream (stderr), so both channels are grepped.
  readonly repoPresentOnBridge = async (
    runner: RenetFunctionsTestRunner,
    name: string
  ): Promise<boolean> => {
    const guid = (await this.guidOf(name).catch(() => undefined)) ?? this.guids[name];
    if (!guid) return false;
    const res = await runner.executeViaBridge(
      'renet functions once --test-mode --debug --function repository_list'
    );
    return res.code === 0 && (res.stdout + res.stderr).includes(guid);
  };

  readonly imageExists = async (runner: RenetFunctionsTestRunner, guid: string): Promise<boolean> =>
    (await runner.executeViaBridge(`sudo test -e ${imagePath(guid)}`)).code === 0;

  readonly deleteAppQuietly = async (name: string): Promise<void> => {
    await this.cli.run(['repo', 'delete', name, '-y']).catch(() => undefined);
  };

  // Deletes in parallel across the machines the config places the repos on, and one at a time on any one machine. Config writes are safe either way (the CLI's config store takes a file lock around each read-modify-write); keeping each machine's deletes serial means no two deletes on one machine contend for its repositories or its router.
  readonly deleteAppsQuietly = async (names: readonly string[]): Promise<void> => {
    const byMachine = new Map<string, string[]>();
    for (const name of names) {
      const machine = (await this.placementOf(name).catch(() => undefined)) ?? '';
      byMachine.set(machine, [...(byMachine.get(machine) ?? []), name]);
    }
    await Promise.all(
      [...byMachine.values()].map(async (group) => {
        for (const name of group) await this.deleteAppQuietly(name);
      })
    );
  };

  readonly workerPairs = (): (readonly [RenetFunctionsTestRunner, string])[] => [
    [this.w1, M1],
    [this.w2, M2],
  ];

  // Create a repo on machine-11, bring it up and install a Rediaccfile whose `up()` runs the body `upBody(guid)` returns, on whichever machine brings the repo up. The file lives in the repo image, so migrate carries it to the target.
  readonly seedRepo = async (name: string, upBody: (guid: string) => string): Promise<string> => {
    const create = await this.cli.run(['repo', 'create', name, '-m', M1, '--size', '1G']);
    expect(create.code, `repo create ${name}: ${create.stderr}`).toBe(0);
    const guid = await this.guidOf(name);
    expect(guid, `create registered no GUID for ${name}`).toBeTruthy();
    this.guids[name] = guid;
    this.extraGuids.add(guid!);
    const up = await this.cli.run(['repo', 'up', `${name}@${M1}`]);
    expect(up.code, `repo up ${name}: ${up.stderr}`).toBe(0);
    const file = `up() {\n${upBody(guid!)}\n}\n\ndown() {\n    true\n}\n`;
    const wrote = await this.w1.writeFileToRepository(guid!, 'Rediaccfile', file, DS);
    expect(wrote.code, `Rediaccfile write: ${wrote.stderr}`).toBe(0);
    return guid!;
  };

  readonly setup = async (): Promise<void> => {
    this.cli = CliRunner.create();
    this.w1 = RenetFunctionsTestRunner.forWorker(1);
    this.w2 = RenetFunctionsTestRunner.forWorker(2);
    await skipWithoutLandlock(this.w1);

    // Isolated e2e-cli config (NEVER the default) + register both machines. Recreated from SCRATCH each run: the config records the fleet's host keys, and a config that outlives an ops down/up carries the PREVIOUS fleet's keys — every connection then fails host-key verification (found live: preflight red while the bridge probes were green).
    await CliRunner.resetConfig();
    await this.cli.initConfig(SSH_KEY);
    // renet enforces licensing, so `repo create` must issue a licence: the config logs in to the account server first.
    const login = await loginCliToAccount(this.cli);
    expect(login.code, `subscription login: ${login.stderr.slice(-600)}`).toBe(0);
    await this.cli.addMachine(M1, M1_IP, SSH_USER);
    await this.cli.addMachine(M2, M2_IP, SSH_USER);

    // Clean any residue from a prior aborted run.
    await this.deleteAppsQuietly(this.apps);
  };

  // Every repo name and every GUID this suite created, on one machine. A probe that throws counts as residue: an unreadable machine proves nothing.
  private readonly residueOn = async (
    runner: RenetFunctionsTestRunner,
    label: string
  ): Promise<string[]> => {
    const residue: string[] = [];
    for (const name of this.apps) {
      if (await this.repoPresentOnBridge(runner, name).catch(() => true)) {
        residue.push(`${name} on ${label}`);
      }
    }
    for (const guid of this.extraGuids) {
      if (await this.imageExists(runner, guid).catch(() => true)) {
        residue.push(`image ${guid} on ${label}`);
      }
    }
    return residue;
  };

  readonly teardown = async (): Promise<void> => {
    await this.deleteAppsQuietly(this.apps);
    // A seeded case can leave a stray source copy or a mounted commit the CLI delete never sees: remove them by GUID, the two machines in parallel and each machine's GUIDs in turn.
    await Promise.all(
      this.workerPairs().map(async ([runner]) => {
        for (const guid of this.extraGuids) {
          await runner
            .executeViaBridge(
              `sudo renet repository unmount --name ${guid} --datastore ${DS}; sudo renet repository delete --name ${guid} --force --stop-docker --datastore ${DS}`
            )
            .catch(() => undefined);
        }
      })
    );
    const residue = await Promise.all(
      this.workerPairs().map(([runner, label]) => this.residueOn(runner, label))
    );
    expect(residue.flat(), 'residue survived teardown').toEqual([]);
  };
}
