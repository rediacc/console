import { spawnSync } from 'node:child_process';
import { t } from '../i18n/index.js';
import { findVSCode, isRemoteSSHExtensionInstalled } from '../remote/vscode/index.js';
import { findOnPath } from '../services/tools/path-lookup.js';
import type { CheckResult } from './doctor.js';

/** The state of the Win32-OpenSSH `ssh-agent` service; `missing` when the service does not exist. */
export type SshAgentState = 'running' | 'stopped' | 'disabled' | 'missing';

export interface WindowsClientDeps {
  /** The VS Code that `rdc vscode check` finds, or null. */
  findVSCode?: () => Promise<{ path: string; version?: string } | null>;
  /** The Remote-SSH extension probe `rdc vscode check` uses. */
  hasRemoteSsh?: () => Promise<boolean>;
  /** The ssh-agent service state, or null when it cannot be read. */
  sshAgentState?: () => SshAgentState | null;
  /** The OpenSSH client's `ssh -V` banner, or null when no ssh runs. */
  sshVersion?: () => string | null;
}

const STOPPED_STATUSES = new Set([
  'stopped',
  'paused',
  'startpending',
  'stoppending',
  'pausepending',
  'continuepending',
]);

/**
 * Parse the probe's output: `<Status>|<StartType>` from `Get-Service`, or `missing` when the service does not exist.
 * Empty or unrecognised output is null (unknown), never a guess at a stopped agent.
 */
export function parseSshAgentState(output: string): SshAgentState | null {
  const text = output.trim();
  if (text.toLowerCase() === 'missing') return 'missing';
  const [status = '', startType = ''] = text.split('|').map((part) => part.trim().toLowerCase());
  if (startType === 'disabled') return 'disabled';
  if (status === 'running') return 'running';
  return STOPPED_STATUSES.has(status) ? 'stopped' : null;
}

/** Only a service that does not exist is `missing`; a policy block or any other PowerShell error leaves the state unknown. */
const SSH_AGENT_PROBE =
  'try { $s = Get-Service ssh-agent -ErrorAction Stop; "$($s.Status)|$($s.StartType)" } catch [Microsoft.PowerShell.Commands.ServiceCommandException] { "missing" }';

function defaultSshAgentState(): SshAgentState | null {
  try {
    const result = spawnSync(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-Command', SSH_AGENT_PROBE],
      { encoding: 'utf-8', timeout: 10_000 }
    );
    if (result.error || result.status !== 0) return null;
    return parseSshAgentState(result.stdout);
  } catch {
    return null;
  }
}

function defaultSshVersion(): string | null {
  const ssh = findOnPath('ssh');
  if (!ssh) return null;
  try {
    // `ssh -V` writes its banner to stderr.
    const result = spawnSync(ssh, ['-V'], { encoding: 'utf-8', timeout: 10_000 });
    const banner = `${result.stderr ?? ''}${result.stdout ?? ''}`.trim();
    return banner || null;
  } catch {
    return null;
  }
}

async function checkVsCode(deps: WindowsClientDeps): Promise<CheckResult[]> {
  const name = t('commands.doctor.checks.vscode');
  const vscode = await (deps.findVSCode ?? findVSCode)();
  if (!vscode) {
    return [
      {
        name,
        value: t('commands.doctor.notInstalled'),
        status: 'warn',
        hint: t('commands.doctor.vscodeInstallHint'),
      },
    ];
  }
  const checks: CheckResult[] = [{ name, value: vscode.version ?? vscode.path, status: 'ok' }];
  const remoteName = t('commands.doctor.checks.remoteSsh');
  checks.push(
    (await (deps.hasRemoteSsh ?? isRemoteSSHExtensionInstalled)())
      ? { name: remoteName, value: t('commands.doctor.installedValue'), status: 'ok' }
      : {
          name: remoteName,
          value: t('commands.doctor.notDetectedValue'),
          status: 'warn',
          hint: t('commands.doctor.remoteSshInstallHint'),
        }
  );
  return checks;
}

function checkSshAgent(deps: WindowsClientDeps): CheckResult {
  const name = t('commands.doctor.checks.sshAgent');
  const state = (deps.sshAgentState ?? defaultSshAgentState)();
  if (state === 'running') return { name, value: t('commands.doctor.agentRunning'), status: 'ok' };
  if (state === null) return { name, value: t('commands.doctor.unknownValue'), status: 'warn' };
  if (state === 'missing') {
    return {
      name,
      value: t('commands.doctor.agentMissing'),
      status: 'warn',
      hint: t('commands.doctor.sshClientMissingHint'),
    };
  }
  return {
    name,
    value: t(
      state === 'disabled' ? 'commands.doctor.agentDisabled' : 'commands.doctor.agentStopped'
    ),
    status: 'warn',
    hint: t('commands.doctor.sshAgentEnableHint'),
  };
}

function checkSshClient(deps: WindowsClientDeps): CheckResult {
  const name = t('commands.doctor.checks.opensshClient');
  const banner = (deps.sshVersion ?? defaultSshVersion)();
  if (!banner) {
    return {
      name,
      value: t('commands.doctor.notInstalled'),
      status: 'warn',
      hint: t('commands.doctor.sshClientMissingHint'),
    };
  }
  return { name, value: banner.split(',')[0], status: 'ok' };
}

/** The Windows-only client checks: VS Code with Remote-SSH, the OpenSSH client, the ssh-agent service. */
export async function checkWindowsClient(deps: WindowsClientDeps = {}): Promise<CheckResult[]> {
  return [...(await checkVsCode(deps)), checkSshClient(deps), checkSshAgent(deps)];
}
