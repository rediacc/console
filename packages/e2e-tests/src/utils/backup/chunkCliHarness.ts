import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { expect } from '@playwright/test';
import { getSSHPrivateKeyPath } from '@rediacc/provisioning';
import { DEFAULT_DATASTORE_PATH } from '../../constants';
import {
  type BackupUsage,
  chunkVerbs,
  type SnapshotRecord,
  verbIsRegistered,
} from '../backupStorage';
import { CliRunner } from '../CliRunner';
import { RenetFunctionsTestRunner } from '../renet-functions/RenetFunctionsTestRunner';

// Shared by suites 26 and 27: the account-server and fleet wiring, the CLI login, and the repository provisioning both chunk-store CLI suites build on.

export const ACCOUNT_SERVER = (process.env.REDIACC_ACCOUNT_SERVER ?? '').trim();
const ACCOUNT_TOKEN = (process.env.E2E_ACCOUNT_API_TOKEN ?? '').trim();
export const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
export const DS = DEFAULT_DATASTORE_PATH;

// The key `ops up` stages for the fleet. getSSHPrivateKeyPath resolves the renet data dir exactly as the bridge's SSH executor does (RENET_DATA_DIR, then $RUNNER_TEMP/renet under CI, then ~/.renet), so the CLI config names the same key the bridge calls use. A hand-built `~/.renet` fallback ignored the CI autodetect: the browse-at job stages the key under $RUNNER_TEMP/renet, `config init --ssh-key` pointed at a missing file, and `repo create` failed with "has no SSH key configured" (run 39673666688). Suites 23 and 24 use the same resolver.
const SSH_KEY = process.env.E2E_SSH_KEY ?? getSSHPrivateKeyPath();

// Machine registration for the CLI, same wiring suite 23 uses. The CLI needs its own machine entries: the bridge runners SSH straight through, but `rdc repo create` (the only thing that installs a repository license) addresses a machine BY NAME out of the config.
const NET_BASE = process.env.VM_NET_BASE ?? '192.168.111';
export const M1 = 'machine-11';
export const M2 = 'machine-12';
const M1_IP = `${NET_BASE}.${workers[0] ?? '11'}`;
const M2_IP = `${NET_BASE}.${workers[1] ?? '12'}`;
const SSH_USER = process.env.E2E_SSH_USER ?? process.env.USER ?? 'root';

/** The `-o json` envelope every rdc command prints (output.ts formatJson). */
export interface CliEnvelope<T> {
  success: boolean;
  data: T | null;
}

/** The slice of rdc's config-v3 file this suite reads back after a create. */
interface CliConfigFile {
  resources?: {
    repositories?: Record<
      string,
      {
        grand?: string;
        tags?: Record<string, { repositoryGuid?: string; credential?: string }>;
      }
    >;
  };
  state?: { repos?: Record<string, Record<string, { networkId?: number }>> };
}

/** Everything a bridge-side call needs about a repo the CLI just created. */
export interface ProvisionedRepo {
  readonly name: string;
  readonly guid: string;
  /** The LUKS passphrase, minted by the CLI and stored in the config. */
  readonly credential: string;
  /** Required by `repository mount`; without it the mount starts on the wrong net. */
  readonly networkId: string;
}

export const accountPrereqs = [
  {
    name: 'REDIACC_ACCOUNT_SERVER',
    satisfied: ACCOUNT_SERVER.length > 0,
    how: 'run `./run.sh account dev` and export the gateway URL it prints (the port is dynamic; re-read .account-state)',
  },
  {
    name: 'E2E_ACCOUNT_API_TOKEN',
    satisfied: ACCOUNT_TOKEN.length > 0,
    how: 'mint an api token carrying the `backup:read` scope and export it',
  },
];

/**
 * Does the renet this harness deploys actually register the run verb?
 *
 * A REAL probe, run synchronously at module load against the same binary
 * `CliRunner` pins into the config and the infrastructure manager pushes to the
 * fleet. It replaces the env-var CLAIM this tier used before the verb existed:
 * a tier that switches on because someone exported a variable is a tier that
 * can go green on a fleet that cannot run it. Test 0 re-verifies on the MACHINE,
 * which is where it has to be true.
 *
 * Any failure to resolve or execute reads as "absent", which is the fail-closed
 * direction.
 */
function localRenetHelp(): string {
  const candidates = [process.env.RENET_BINARY_PATH].filter((c): c is string => !!c);
  for (const start of [process.cwd(), __dirname]) {
    let dir = start;
    for (let i = 0; i < 8; i++) {
      candidates.push(path.join(dir, 'private', 'renet', 'bin', 'renet'));
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  const binary = candidates.find((c) => existsSync(c));
  if (!binary) return '';
  try {
    return execFileSync(binary, ['backup', '--help'], {
      encoding: 'utf8',
      timeout: 30_000,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch {
    return '';
  }
}

export const localHelp = localRenetHelp();
export const engineVerbPresent = verbIsRegistered(localHelp, chunkVerbs().run);

/** Parse a JSON envelope, failing with an assertion that names the raw output rather than a bare SyntaxError. */
export const parseEnvelope = (raw: string, stderr = ''): Partial<CliEnvelope<unknown>> => {
  try {
    return JSON.parse(raw.trim() || '{}') as Partial<CliEnvelope<unknown>>;
  } catch {
    throw new Error(
      `stdout is not a JSON envelope: ${raw.slice(0, 800)}${stderr ? `\nstderr: ${stderr.slice(0, 800)}` : ''}`
    );
  }
};

/** Both channels: the CLI's refusals arrive on stderr. */
export const bothChannels = (r: { stdout: string; stderr: string }): string => r.stdout + r.stderr;

/**
 * Stand a CLI up against this account server, in its own config namespace.
 *
 * `licensing: true` is load-bearing, not tidiness: CliRunner's default exports
 * `REDIACC_SKIP_MACHINE_ACTIVATION=1`, which makes
 * `ensureRepoLicenseForProvisioning` return immediately — so `repo create`
 * would produce exactly the unlicensed repo the bridge produced, and the
 * snapshot verb would refuse it again.
 */
export const loginCli = async (cfg: string): Promise<CliRunner> => {
  await CliRunner.resetConfig(cfg);
  const cli = CliRunner.create({
    configName: cfg,
    licensing: true,
    env: { REDIACC_ACCOUNT_SERVER: ACCOUNT_SERVER },
  });
  await cli.initConfig(SSH_KEY);
  const login = await cli.run([
    'subscription',
    'login',
    '--server',
    ACCOUNT_SERVER,
    '--token',
    ACCOUNT_TOKEN,
  ]);
  expect(login.code, `subscription login: ${login.stderr.slice(-600)}`).toBe(0);
  return cli;
};

/** Read rdc's own config file — the artifact `repo create` just wrote. */
const readCliConfig = (cli: CliRunner): CliConfigFile =>
  JSON.parse(readFileSync(cli.configPath, 'utf8')) as CliConfigFile;

/**
 * What the CLI's config holds for one repository tag: its GUID, LUKS credential and network id.
 * A restored repo and a fork mint their own GUID, so the suites read it back instead of assuming
 * the source's. The credential falls back to the grand tag's, which is what a fork and a restore inherit.
 */
export const repoIdentity = (cli: CliRunner, name: string, tag?: string): ProvisionedRepo => {
  const cfg = readCliConfig(cli);
  const family = cfg.resources?.repositories?.[name];
  const useTag = tag ?? family?.grand ?? 'latest';
  const entry = family?.tags?.[useTag];
  const grandEntry = family?.tags?.[family?.grand ?? 'latest'];
  const guid = entry?.repositoryGuid ?? '';
  expect(guid, `the config registered no guid for ${name}:${useTag}`).toMatch(/^[0-9a-f-]{36}$/);
  const networkId = cfg.state?.repos?.[name]?.[useTag]?.networkId;
  expect(networkId, `the config recorded no network id for ${name}:${useTag}`).toBeDefined();
  return {
    name,
    guid,
    credential: entry?.credential ?? grandEntry?.credential ?? '',
    networkId: String(networkId),
  };
};

/** Every repository GUID the CLI config holds, across all names and tags. */
const allRepoGuids = (cli: CliRunner): string[] =>
  Object.values(readCliConfig(cli).resources?.repositories ?? {}).flatMap((family) =>
    Object.values(family.tags ?? {}).flatMap((t) => (t.repositoryGuid ? [t.repositoryGuid] : []))
  );

/**
 * Every GUID the config holds apart from ONE occurrence of `own`: a second entry carrying `own`
 * stays in the result, which is what lets `newGuidViolations` see a collision.
 */
export const guidsBesides = (cli: CliRunner, own: string): string[] => {
  const all = allRepoGuids(cli);
  const at = all.indexOf(own);
  return at < 0 ? all : all.filter((_, i) => i !== at);
};

/**
 * Lay down the base datastore pool on a worker, WITHOUT destroying one.
 *
 * The obvious call — `datastoreInitPool(size, path, true)` — passes `--force`,
 * and force means `ds.Cleanup()`: it deletes every repository image on the
 * machine (datastore_init.go:106-120). On a fleet that other sessions and
 * suites share, that is not setup, it is collateral. So probe first and only
 * init when there is genuinely nothing there.
 */
export const ensureDatastore = async (
  runner: RenetFunctionsTestRunner,
  label: string
): Promise<void> => {
  const init = await runner.datastoreInitPool('10G', DS, false);
  if (init.code === 0) return;
  // Without --force, renet REFUSES an existing BTRFS datastore by name ("datastore already exists", datastore_init.go:106-111). That refusal is the answer this function wants, so it is the success case, not a failure — and it is a more reliable probe than a shell test, whose `&&`/`||` has to survive two levels of SSH quoting to mean anything.
  const output = runner.getCombinedOutput(init);
  expect(
    /already exists/i.test(output),
    `datastore init on ${label} failed for a reason other than one already being there: ${output.slice(-800)}`
  ).toBe(true);
};

/** Register both workers in the CLI config (idempotent per fresh config). */
export const registerMachines = async (cli: CliRunner): Promise<void> => {
  for (const [name, ip] of [
    [M1, M1_IP],
    [M2, M2_IP],
  ] as const) {
    const added = await cli.addMachine(name, ip, SSH_USER);
    expect(added.code, `machine add ${name}: ${bothChannels(added).slice(-600)}`).toBe(0);
  }
};

/**
 * Create a repository THROUGH THE CLI and prove it came out licensed.
 *
 * The proof is the point. `repo create` exits 0 on a fleet whose license
 * issuance quietly no-opped (that is exactly what
 * `REDIACC_SKIP_MACHINE_ACTIVATION=1` does), and the failure would then surface
 * three tests later as a snapshot refusing on "no license data" — read as a
 * broken uploader. So the license is read back off the MACHINE, where it has to
 * be true, before the caller relies on it.
 */
export const provisionRepo = async (
  cli: CliRunner,
  runner: RenetFunctionsTestRunner,
  name: string,
  machine: string
): Promise<ProvisionedRepo> => {
  const create = await cli.run(['repo', 'create', name, '-m', machine, '--size', '1G']);
  expect(create.code, `repo create ${name}: ${bothChannels(create).slice(-1200)}`).toBe(0);

  const cfg = readCliConfig(cli);
  const family = cfg.resources?.repositories?.[name];
  const tag = family?.grand ?? 'latest';
  const guid = family?.tags?.[tag]?.repositoryGuid ?? '';
  const credential = family?.tags?.[tag]?.credential ?? '';
  const networkId = cfg.state?.repos?.[name]?.[tag]?.networkId;
  expect(guid, `repo create ${name} registered no guid in ${cli.configPath}`).toMatch(
    /^[0-9a-f-]{36}$/
  );
  expect(credential, `repo create ${name} registered no LUKS credential`).not.toBe('');
  expect(networkId, `repo create ${name} recorded no network id`).toBeDefined();

  const status = await runner.executeViaBridge(
    `sudo renet repository license-status --output json 2>&1 || true`
  );
  // The RAW streams, not `getCombinedOutput`: that helper lowercases what it returns (TestHelpers.ts:15), which is harmless for a keyword grep and fatal
  // for JSON — every key comes back as `repositoryguid`, the lookup misses, and
  // a license that is right there reads as absent.
  const rawStatus = status.stdout + status.stderr;
  const installed = (
    JSON.parse((/\[.*\]/s.exec(rawStatus) ?? ['[]'])[0]) as {
      repositoryGuid: string;
      status?: string;
      installed?: boolean;
    }[]
  ).find((row) => row.repositoryGuid === guid);
  expect(
    installed,
    `no license row for ${guid} on ${machine}; the CLI created the repo without licensing it:\n${rawStatus.slice(-800)}`
  ).toBeDefined();
  expect(installed?.status, `license for ${guid} is not valid`).toBe('valid');
  // `installed` means a blob sits under the BAKED key's fingerprint (/var/lib/rediacc/license/repos/<guid>/<fingerprint>.json). The CLI files it under the SIGNER's fingerprint, so a signer the renet build does not bake reads as issued-but-not-installed, and every snapshot or restore verb after it refuses the repo.
  expect(
    installed?.installed,
    `license for ${guid} was issued but not installed. The likely cause is a key mismatch: the account server signed with a key the deployed renet does not bake. ` +
      `Compare the blob names under /var/lib/rediacc/license/repos/${guid}/ on ${machine} with the baked key ` +
      '(`go version -m private/renet/bin/renet-linux-amd64 | grep ProductionPublicKey`), or run ' +
      '`PYTHONPATH=.ci python3 -m rediacc_ci.testrun.start_backup_plane --verify-renet private/renet/bin/renet-linux-amd64` ' +
      'with ACCOUNT_ED25519_PUBLIC_KEY set to the server key; rebuild renet with that key exported if they differ.'
  ).toBe(true);

  // `repo create` leaves the repo MOUNTED with its docker daemon up. The snapshot verb reads the image underneath, so bring it down first.
  await runner.repositoryUnmount(guid, DS).catch(() => undefined);
  return { name, guid, credential, networkId: String(networkId) };
};

export const seam = async (route: string, body: unknown): Promise<Response> =>
  fetch(`${ACCOUNT_SERVER}/account/api/v1/test/${route}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

/**
 * Undo the planted aggregate by RECOMPUTING it from the per-lineage rows.
 *
 * The quota tests plant byte counts on a subscription shared with whoever else
 * is driving this account server, and the over-limit flag they plant refuses
 * every upload on the account until it is cleared — the next tier's own seed
 * included. The seam overwrites the aggregate row and has no delete, so
 * something has to write the true value back.
 *
 * "The value captured before the first seed" is NOT that true value, and using
 * it corrupts the ledger for the next run: real uploads land BETWEEN the
 * capture and the restore (this tier's own seed and incremental do), so the
 * stale aggregate ends up smaller than the lineage rows underneath it, and the
 * very next `usageViolations` reports the parts exceeding the whole. Found
 * exactly that way — the run after the first restore opened red on test 1.
 *
 * The per-lineage rows are the ledger's own breakdown and the uploader keeps
 * them current, so their sum is the aggregate at whatever moment this runs.
 */
export const restoreLedger = async (cli: CliRunner, subscriptionId: string): Promise<void> => {
  if (!subscriptionId) return;
  const { json } = await cli.runJson<CliEnvelope<BackupUsage>>(['backup', 'usage']);
  const lineages = json?.data?.lineages;
  if (!lineages) return;
  await seam('seed-backup-ledger', {
    subscriptionId,
    storedBytes: lineages.reduce((sum, l) => sum + l.storedBytes, 0),
    chunkCount: lineages.reduce((sum, l) => sum + l.chunkCount, 0),
    overLimit: false,
  }).catch(() => undefined);
};

/** One stdout line as a snapshot record, or undefined for any other line. */
export function parseSnapshotRecord(line: string): SnapshotRecord | undefined {
  const trimmed = line.trim();
  if (!trimmed.startsWith('{') || !trimmed.includes('"chunksAsked"')) return undefined;
  try {
    return JSON.parse(trimmed) as SnapshotRecord;
  } catch {
    // the dispatcher's own debug JSON shares this stream
    return undefined;
  }
}
