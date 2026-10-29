/**
 * `rdc backup download` and `rdc backup upload`: copy a machine's encrypted repo image to a local
 * path or an external drive and send it back (agent/plans/PLAN-backup-local-image.md).
 *
 * The orchestration lives in services/backup-image/transfer.ts behind injectable deps; this file
 * wires the real ones (the pooled SSH connection, the renet export/import session, the client rsync,
 * the config) and registers the two verbs. Both are client-side transfers: not proxyable, not
 * detachable, MCP-excluded.
 */

import { createHash, randomUUID } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { resolve as resolvePath } from 'node:path';
import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import type { Placement } from '@rediacc/shared/config-schema';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import {
  createTempKnownHostsFile,
  createTempSSHKeyFile,
  removeTempKnownHostsFile,
  removeTempSSHKeyFile,
} from '../remote/ssh/index.js';
import { assertRsyncCapable, runImageRsync } from '../remote/sync/image-rsync.js';
import { getRsyncSSHCommand } from '../remote/sync/rsync.js';
import { bandwidthToBytesPerSecond } from '../services/backup/backup-strategy-validate.js';
import { warnIfConfigStorageUnenrolled } from '../services/backup/dr-nudge.js';
import { reconcileBackupSchedules } from '../services/backup/repo-change-hook.js';
import {
  buildExportCommand,
  buildImportCommand,
  type ExportSession,
  type ImportSession,
  type OpenSessionInput,
  startExportSession,
  startImportSession,
} from '../services/backup-image/session.js';
import {
  DEFAULT_RETRIES,
  type DownloadDeps,
  type ImageTarget,
  type ImportTarget,
  type RegisterEntry,
  runDownload,
  runUpload,
  type SourceRepo,
  type UploadDeps,
} from '../services/backup-image/transfer.js';
import { namedDatastoreMount } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import { targetFloor } from '../services/config/network-id-discovery.js';
import { setExitCode, writeStderr, writeStdout } from '../services/core/request-context.js';
import { machineConnections } from '../services/machine/machine-connection.js';
import { REMOTE_RENET_PATH } from '../services/renet/renet-provisioner.js';
import { assertAgentRepoCreate } from '../utils/agent-guard.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { assertResourceName, compositeKey } from '../utils/config-schema.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { postPushDeploy } from './repo-backup.js';

export { runDownload, runUpload };

const STDERR_TAIL = 8192;

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/** Streaming sha256 of a local file. */
export function hashFile(path: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const hash = createHash('sha256');
    createReadStream(path)
      .on('data', (chunk) => hash.update(chunk))
      .on('error', reject)
      .on('end', () => resolve(hash.digest('hex')));
  });
}

function kibps(rate: string | undefined): number | undefined {
  const bytes = bandwidthToBytesPerSecond(rate);
  return bytes ? Math.max(1, Math.floor(bytes / 1024)) : undefined;
}

function parseRetries(value: string | undefined): number {
  if (value === undefined) return DEFAULT_RETRIES;
  const n = Number(value);
  if (!Number.isInteger(n) || n < 0) {
    throw new ValidationError(t('errors.backupImage.retriesInvalid', { value }));
  }
  return n;
}

function hostSpec(ip: string): string {
  return ip.includes(':') ? `[${ip}]` : ip;
}

function progressLine(text: string): void {
  writeStderr(text);
}

/** Runs `fn` with an AbortSignal that Ctrl-C trips; the handler is removed afterwards. */
async function withInterrupt<T>(fn: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const ac = new AbortController();
  const onSigint = () => ac.abort();
  process.on('SIGINT', onSigint);
  try {
    return await fn(ac.signal);
  } finally {
    process.off('SIGINT', onSigint);
  }
}

/**
 * Opens one helper session on the machine's pooled connection, with the temp key and known_hosts
 * files the system ssh under rsync needs. Everything is released when the session ends.
 */
async function openHelperSession<S>(
  machineName: string,
  command: string,
  start: (input: OpenSessionInput) => Promise<S>
): Promise<S> {
  const lease = await machineConnections.acquire(machineName);
  const temp: string[] = [];
  let released = false;
  const cleanup = () => {
    if (released) return;
    released = true;
    lease.release();
    const [key, knownHosts] = temp;
    if (key) void removeTempSSHKeyFile(key).catch(() => undefined);
    if (knownHosts) void removeTempKnownHostsFile(knownHosts).catch(() => undefined);
  };
  try {
    const sftp = await lease.ensure();
    const machine = lease.machine;
    temp.push(await createTempSSHKeyFile(lease.sshPrivateKey));
    temp.push(await createTempKnownHostsFile(machine.knownHosts));
    const port = machine.port ?? 22;
    const sshCommand = await getRsyncSSHCommand(
      `-o StrictHostKeyChecking=yes -o UserKnownHostsFile="${temp[1]}" -p ${port} -i "${temp[0]}" ` +
        '-o BatchMode=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=4'
    );
    let stderr = '';
    const handle = await sftp.execSession(command, {
      onStderr: (data) => {
        stderr = (stderr + data.toString()).slice(-STDERR_TAIL);
      },
    });
    return await start({
      handle,
      stderrTail: () => stderr,
      transport: { sshCommand, userHost: `${machine.user}@${hostSpec(machine.ip)}` },
      onClosed: cleanup,
    });
  } catch (error) {
    cleanup();
    throw error;
  }
}

async function machineDatastorePath(machineName: string, datastore?: string): Promise<string> {
  if (datastore) return namedDatastoreMount(datastore);
  const machine = await configService.getLocalMachine(machineName);
  return machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
}

interface ListedRepo {
  key: string;
  family: string;
  tag: string;
  guid: string;
  grandGuid: string | null;
  credential?: string;
  networkId?: number;
  isGrand: boolean;
}

async function listedRepos(): Promise<ListedRepo[]> {
  const repos = await configService.listRepositories();
  return repos.map(({ name, config }) => {
    const [family, keyTag] = name.split(':');
    return {
      key: name,
      family,
      tag: config.tag ?? keyTag ?? 'latest',
      guid: config.repositoryGuid,
      grandGuid: config.grandGuid ?? null,
      credential: config.credential,
      networkId: config.networkId,
      isGrand: !config.grandGuid || config.grandGuid === config.repositoryGuid,
    };
  });
}

async function targetFor(ref: string, listed: ListedRepo[]): Promise<ImageTarget> {
  const resolved = await resolveRepoRef(ref, { readOnly: true });
  if (resolved.kubeCluster) {
    throw new ValidationError(t('errors.backupImage.clusterRepo', { ref }));
  }
  const repo = await configService.getRepository(resolved.repoKey);
  if (!repo) throw new ValidationError(t('errors.backupImage.repoUnknown', { ref }));
  await assertCommandPolicy(CMD.BACKUP_DOWNLOAD, resolved.repoKey);
  const entry = listed.find((r) => r.guid === repo.repositoryGuid);
  return {
    repo: resolved.name,
    tag: entry?.tag ?? resolved.tag,
    machine: resolved.machineName,
    guid: repo.repositoryGuid,
    grandGuid: repo.grandGuid ?? null,
    datastore:
      (await recordedDatastoreMount(resolved.repoKey)) ??
      (await machineDatastorePath(resolved.machineName)),
  };
}

async function resolveDownloadTargets(
  refs: string[],
  opts: { all?: string; includeForks?: boolean }
): Promise<ImageTarget[]> {
  const listed = await listedRepos();
  if (!opts.all) return Promise.all(refs.map((ref) => targetFor(ref, listed)));
  const out: ImageTarget[] = [];
  for (const repo of listed) {
    if (!repo.isGrand && !opts.includeForks) continue;
    try {
      const target = await targetFor(repo.key, listed);
      if (target.machine === opts.all) out.push(target);
    } catch {
      // A repo that resolves to no machine (detached datastore, cluster) is not on this machine.
    }
  }
  return out;
}

function realDownloadDeps(
  signal: AbortSignal,
  opts: { checkpoint?: boolean; json: boolean }
): DownloadDeps {
  const networkIds = new Map<string, number | undefined>();
  return {
    assertRsyncCapable: () => assertRsyncCapable(),
    resolveTargets: async (refs, o) => {
      const targets = await resolveDownloadTargets(refs, o);
      for (const r of await listedRepos()) networkIds.set(r.guid, r.networkId);
      return targets;
    },
    openSession: (target: ImageTarget): Promise<ExportSession> =>
      openHelperSession(
        target.machine,
        buildExportCommand({
          renetPath: REMOTE_RENET_PATH,
          guid: target.guid,
          datastore: target.datastore,
          checkpoint: opts.checkpoint,
          networkId: networkIds.get(target.guid),
        }),
        startExportSession
      ),
    runRsync: (req) =>
      runImageRsync({
        ...req,
        signal,
        onProgress: (p) =>
          progressLine(
            `\r${t('commands.backup.download.progress', { percent: String(p.percentage), speed: p.speed, eta: p.eta })}`
          ),
      }).then((outcome) => {
        progressLine('\n');
        return outcome;
      }),
    hashFile,
    sleep,
    now: () => new Date(),
    write: (text) => writeStdout(text),
    progress: opts.json ? undefined : progressLine,
    signal,
  };
}

function sourceOf(r: ListedRepo): SourceRepo {
  return {
    name: r.family,
    tag: r.tag,
    credential: r.credential,
    grandGuid: r.grandGuid,
    guid: r.guid,
  };
}

async function registerUploaded(entry: RegisterEntry): Promise<void> {
  assertResourceName(entry.name);
  const placement: Placement = entry.datastore
    ? { datastore: entry.datastore }
    : { machine: entry.machine };
  const networkId = await configService.allocateNetworkId({
    floor: await targetFloor({ machine: entry.machine }),
  });
  // A fresh GUID minted before the transfer (so a resume lands in the same staging), carrying the source's lineage as grandGuid, exactly as `backup restore` registers a restored image.
  await configService.addRepository(compositeKey(entry.name, 'latest'), {
    repositoryGuid: entry.guid,
    ...(entry.lineage ? { grandGuid: entry.lineage } : {}),
    tag: 'latest',
    // The image bytes are the source's ciphertext, so the copy unlocks with the source's credential under its new GUID.
    credential: entry.credential,
    networkId,
    placement,
  });
  await warnIfConfigStorageUnenrolled();
  await reconcileBackupSchedules(entry.machine);
}

async function realUploadDeps(opts: {
  datastore?: string;
  debug?: boolean;
  json: boolean;
}): Promise<UploadDeps> {
  const listed = await listedRepos();
  const byName = (name: string): ListedRepo | undefined => {
    const exact = listed.find((r) => r.key === name || compositeKey(r.family, r.tag) === name);
    if (exact) return exact;
    const family = listed.filter((r) => r.family === name);
    return family.find((r) => r.isGrand) ?? family[0];
  };
  return {
    assertRsyncCapable: () => assertRsyncCapable(),
    findRepoByGuid: (guid) => {
      const r = listed.find((x) => x.guid === guid);
      return r ? sourceOf(r) : undefined;
    },
    findRepoByName: (name) => {
      const r = byName(name);
      return r ? sourceOf(r) : undefined;
    },
    mintGuid: () => randomUUID(),
    openImportSession: (target: ImportTarget): Promise<ImportSession> =>
      openHelperSession(
        target.machine,
        buildImportCommand({
          renetPath: REMOTE_RENET_PATH,
          guid: target.guid,
          datastore: target.datastore,
          seedGuid: target.seedGuid,
          allocatedBytes: target.allocatedBytes,
        }),
        startImportSession
      ),
    runRsync: (req) =>
      runImageRsync({
        ...req,
        onProgress: (p) =>
          progressLine(
            `\r${t('commands.backup.download.progress', { percent: String(p.percentage), speed: p.speed, eta: p.eta })}`
          ),
      }).then((outcome) => {
        progressLine('\n');
        return outcome;
      }),
    hashFile,
    register: registerUploaded,
    sleep,
    now: () => new Date(),
    write: (text) => writeStdout(text),
    progress: opts.json ? undefined : progressLine,
    datastorePath: (machine, datastore) => machineDatastorePath(machine, datastore),
    assertCreate: async (name, machine) => {
      await assertCommandPolicy(CMD.BACKUP_UPLOAD, name);
      const placement: Placement = opts.datastore ? { datastore: opts.datastore } : { machine };
      await assertAgentRepoCreate(name, placement);
    },
    deploy: (name, machine) => postPushDeploy(name, machine, { debug: opts.debug }),
  };
}

interface DownloadCliOptions {
  to: string;
  all?: boolean;
  machine?: string;
  includeForks?: boolean;
  bwlimit?: string;
  checkpoint?: boolean;
  retries?: string;
  skipVerify?: boolean;
  skipSpaceCheck?: boolean;
}

/** Repositories by name, or `--all -m <machine>`; never both, never neither. */
function assertDownloadSelection(refs: string[], options: DownloadCliOptions): void {
  if (options.all && refs.length > 0) {
    throw new ValidationError(t('errors.backupImage.allWithRefs'));
  }
  if (options.all && !options.machine) {
    throw new ValidationError(t('errors.backupImage.allNeedsMachine'));
  }
  if (!options.all && refs.length === 0) {
    throw new ValidationError(t('errors.backupImage.refsRequired'));
  }
}

function registerDownload(backup: Command): void {
  backup
    .command('download')
    .argument('[refs...]', t('commands.backup.download.argRefs'))
    .description(t('commands.backup.download.description'))
    .requiredOption('--to <dir>', t('commands.backup.download.optionTo'))
    .option('--all', t('commands.backup.download.optionAll'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--include-forks', t('commands.backup.download.optionIncludeForks'))
    .option('--bwlimit <rate>', t('commands.backup.download.optionBwlimit'))
    .option('--checkpoint', t('commands.backup.download.optionCheckpoint'))
    .option('--retries <n>', t('commands.backup.download.optionRetries'))
    .option('--skip-verify', t('commands.backup.download.optionSkipVerify'))
    .option('--skip-space-check', t('commands.backup.download.optionSkipSpaceCheck'))
    .action(async (refs: string[], options: DownloadCliOptions) => {
      try {
        assertDownloadSelection(refs, options);
        const json = getOutputFormat() === 'json';
        const { exitCode } = await withInterrupt((signal) =>
          runDownload(
            {
              to: resolvePath(options.to),
              refs,
              config: configService.getEffectiveConfigName(),
              all: options.all ? options.machine : undefined,
              includeForks: options.includeForks,
              bwlimitKiBps: kibps(options.bwlimit),
              checkpoint: options.checkpoint,
              retries: parseRetries(options.retries),
              skipVerify: options.skipVerify,
              skipSpaceCheck: options.skipSpaceCheck,
              output: json ? 'json' : 'human',
            },
            realDownloadDeps(signal, { checkpoint: options.checkpoint, json })
          )
        );
        setExitCode(exitCode);
      } catch (error) {
        handleError(error);
      }
    });
}

interface UploadCliOptions {
  to: string;
  as?: string;
  datastore?: string;
  fromRepo?: string;
  bwlimit?: string;
  retries?: string;
  up?: boolean;
  skipVerify?: boolean;
  debug?: boolean;
}

function registerUpload(backup: Command): void {
  backup
    .command('upload')
    .argument('<image-file>', t('commands.backup.upload.argImage'))
    .description(t('commands.backup.upload.description'))
    .requiredOption('--to <machine>', t('commands.backup.upload.optionTo'))
    .option('--as <name>', t('commands.backup.upload.optionAs'))
    .option('--datastore <name>', t('commands.backup.upload.optionDatastore'))
    .option('--from-repo <name>', t('commands.backup.upload.optionFromRepo'))
    .option('--bwlimit <rate>', t('commands.backup.download.optionBwlimit'))
    .option('--retries <n>', t('commands.backup.download.optionRetries'))
    .option('--up', t('commands.backup.upload.optionUp'))
    .option('--skip-verify', t('commands.backup.upload.optionSkipVerify'))
    .option('--debug', t('options.debug'))
    .action(async (image: string, options: UploadCliOptions) => {
      try {
        const json = getOutputFormat() === 'json';
        const { exitCode } = await runUpload(
          {
            image: resolvePath(image),
            to: options.to,
            as: options.as,
            datastore: options.datastore,
            fromRepo: options.fromRepo,
            skipVerify: options.skipVerify,
            bwlimitKiBps: kibps(options.bwlimit),
            retries: parseRetries(options.retries),
            up: options.up,
            config: configService.getEffectiveConfigName(),
            output: json ? 'json' : 'human',
          },
          await realUploadDeps({ datastore: options.datastore, debug: options.debug, json })
        );
        setExitCode(exitCode);
      } catch (error) {
        handleError(error);
      }
    });
}

/** Registers `backup download` and `backup upload` under the `backup` noun. */
export function registerBackupImageCommands(backup: Command): void {
  registerDownload(backup);
  registerUpload(backup);
}
