/**
 * The real effects behind `rdc preview use`, `leave` and the banner (PLAN-preview-signer.md D6, D8-D10):
 * the network, the binary on disk, the machines over SSH and the activation path. `switch.ts` and
 * `licences.ts` take these as `deps`, so their tests drive the order of events without any of it.
 */
import { spawn } from 'node:child_process';
import { UPDATE_DEFAULTS } from '@rediacc/shared/config/defaults';
import { WK_RELEASES_ORIGIN } from '@rediacc/shared/config/well-known.generated';
import { t } from '../../i18n/index.js';
import type { UpdateManifest } from '../../types/index.js';
import { getInstallMethod, getPlatformKey } from '../../utils/platform.js';
import { askConfirm } from '../../utils/prompt.js';
import { VERSION } from '../../version.js';
import { fetchServerInfo } from '../account/account-client.js';
import { readAccountPointer } from '../account/account-pointer.js';
import { getEffectiveConfigName } from '../config/config-name.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { writeStderr } from '../core/request-context.js';
import { sftpConfigForMachine, withSharedOrPooledSftp } from '../machine/machine-connection.js';
import { readSSHKey } from '../renet/renet-execution.js';
import { REMOTE_RENET_PATH, renetProvisioner } from '../renet/renet-provisioner.js';
import { getRemoteHashAndVersion } from '../renet/renet-remote-probe.js';
import { installBinaryAtPath, keepCurrentBinary, restoreKeptBinary } from './install-binary.js';
import { type LicenceDeps, licenceReportLines, releaseLicencesOnLeave } from './licences.js';
import type { SwitchBackOutcome } from './slot.js';
import { readPreviewOverlay, readRealAccountServer, readRealReleasesBase } from './state.js';
import {
  type PreviewLeaveDeps,
  type PreviewUseDeps,
  previewKeptBinaryPath,
  type SwitchBackResult,
} from './switch.js';

const FETCH_TIMEOUT_MS = 10_000;

async function fetchManifestAt(url: string): Promise<UpdateManifest> {
  const res = await fetch(url, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) });
  if (!res.ok) throw new Error(`HTTP ${res.status} from ${url}`);
  return (await res.json()) as UpdateManifest;
}

function onProgress(downloaded: number, total: number): void {
  if (total > 0) {
    writeStderr(
      `\r${t('commands.update.progress', { percent: Math.round((downloaded / total) * 100).toString() })}`
    );
  }
}

export function realPreviewUseDeps(): PreviewUseDeps {
  return {
    fetchServerInfo: (host) => fetchServerInfo(host) as Promise<{ previewBuild?: unknown }>,
    fetchManifest: (name) => fetchManifestAt(`${WK_RELEASES_ORIGIN}/cli/${name}/manifest.json`),
    platformKey: getPlatformKey,
    canReplaceBinary: () => getInstallMethod() === 'sea',
    keepCurrentBinary: (dest) => keepCurrentBinary(dest),
    installBinary: (binary) => installBinaryAtPath(process.execPath, binary, onProgress),
    confirmFormatChange: (formatChange) =>
      askConfirm(
        t('commands.preview.msg.formatChangeConfirm', { formats: formatChange.formats.join(', ') })
      ),
    current: () => ({ version: VERSION, updateChannel: readAccountPointer().updateChannel }),
    realServer: () => readRealAccountServer(),
    now: () => new Date(),
  };
}

/** Run `binary` (the restored CLI) with `args`, resolving its exit status and the last line of its stderr. */
function runCli(
  binary: string,
  args: string[],
  env: NodeJS.ProcessEnv = {}
): Promise<{ code: number | null; stderrTail: string }> {
  return new Promise((resolve) => {
    const child = spawn(binary, args, {
      env: { ...process.env, ...env },
      stdio: ['ignore', 'ignore', 'pipe'],
    });
    let stderr = '';
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on('error', (error) => resolve({ code: null, stderrTail: error.message }));
    child.on('close', (code) => {
      const lines = stderr.trim().split('\n');
      resolve({ code, stderrTail: lines.at(-1) ?? '' });
    });
  });
}

/** A machine's SSH context from the config, the way the subscription commands resolve it. */
async function withMachineSftp<T>(
  machineName: string,
  fn: (sftp: Parameters<typeof renetProvisioner.switchBackToPinnedSlot>[0]) => Promise<T>
): Promise<T> {
  const localConfig = await configService.getLocalConfig();
  const machine = await configService.getLocalMachine(machineName);
  const key = localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
  return withSharedOrPooledSftp(undefined, sftpConfigForMachine(machine, key), fn);
}

function licenceDeps(restoredCli: string, names: Map<string, string>): LicenceDeps {
  return {
    exec: (machine, command) => withMachineSftp(machine, (sftp) => sftp.exec(command)),
    relicense: async (machine, guid) => {
      const repo = names.get(guid) ?? guid;
      const result = await runCli(restoredCli, [
        '--config',
        getEffectiveConfigName(),
        'subscription',
        'refresh',
        '--repo',
        `${repo}@${machine}`,
        '--adopt-origin',
      ]);
      return result.code === 0
        ? { ok: true }
        : { ok: false, reason: result.stderrTail || `exit ${result.code}` };
    },
    repoName: (guid) => names.get(guid) ?? guid,
  };
}

/** The renet version a touched server runs now, or `null` when it cannot be reached (the list only shows it). */
async function probeRenetVersion(machine: string): Promise<string | null> {
  try {
    return await withMachineSftp(machine, async (sftp) => {
      const probe = await getRemoteHashAndVersion(sftp, REMOTE_RENET_PATH);
      return probe.version;
    });
  } catch {
    return null;
  }
}

/**
 * Point one server back at its pinned slot. A gone or changed slot is re-provisioned with the CLI that embeds
 * the pre-preview renet (the kept copy, still on disk), allowing the downgrade from the preview renet; a
 * server that cannot be reached, or whose re-provision fails, stays listed.
 */
async function switchBackServer(
  machine: string,
  entry: { slot: string; sha256: string }
): Promise<SwitchBackResult> {
  let outcome: SwitchBackOutcome;
  try {
    outcome = await withMachineSftp(machine, (sftp) =>
      renetProvisioner.switchBackToPinnedSlot(sftp, { slotDir: entry.slot, sha256: entry.sha256 })
    );
  } catch (error) {
    return {
      status: 'unreachable',
      detail: error instanceof Error ? error.message : String(error),
    };
  }
  if (outcome === 'switched') return { status: 'switched' };
  const reprovision = await runCli(
    previewKeptBinaryPath(),
    ['--config', getEffectiveConfigName(), 'machine', 'setup', machine],
    { REDIACC_ALLOW_DOWNGRADE: '1' }
  );
  if (reprovision.code === 0) return { status: 'switched' };
  return {
    status: 'unreachable',
    detail: t('commands.preview.msg.reprovisionFailed', {
      slot: outcome === 'slot_missing' ? 'missing' : 'changed',
      detail: reprovision.stderrTail,
    }),
  };
}

/** Move the switched servers' licences to the real account and print what happened, per server. */
async function relicenseServers(restoredCli: string, machines: string[]): Promise<void> {
  const server = readRealAccountServer();
  const names = new Map<string, string>();
  for (const repo of await configService.listRepositories()) {
    names.set(repo.config.repositoryGuid, repo.name);
  }
  for (const machine of machines) {
    try {
      const report = await releaseLicencesOnLeave(machine, licenceDeps(restoredCli, names));
      for (const line of licenceReportLines(report, server)) outputService.info(line);
    } catch (error) {
      outputService.warn(
        t('commands.preview.msg.licencesFailed', {
          machine,
          detail: error instanceof Error ? error.message : String(error),
        })
      );
    }
  }
}

export function realPreviewLeaveDeps(): PreviewLeaveDeps {
  const restoredCli = readPreviewOverlay()?.previous.binaryPath ?? process.execPath;
  return {
    confirm: (message) => askConfirm(message),
    currentRenetVersion: probeRenetVersion,
    switchBack: switchBackServer,
    fetchPreviousManifest: (channel) =>
      fetchManifestAt(
        `${readRealReleasesBase()}/${channel ?? UPDATE_DEFAULTS.CHANNEL}/manifest.json`
      ),
    platformKey: getPlatformKey,
    installBinaryAt: (target, binary) =>
      installBinaryAtPath(target ?? process.execPath, binary, onProgress),
    restoreKeptCopy: (target, sha256) =>
      restoreKeptBinary(previewKeptBinaryPath(), target ?? process.execPath, sha256),
    relicense: (machines) => relicenseServers(restoredCli, machines),
    realServer: () => readRealAccountServer(),
  };
}
