import { spawnSync } from 'node:child_process';
import { t } from '../i18n/index.js';
import { findVSCode, isRemoteSSHExtensionInstalled } from '../remote/vscode/index.js';
import { findOnPath } from '../services/tools/path-lookup.js';
import type { CheckResult } from './doctor.js';

export interface WindowsClientDeps {
  /** The VS Code that `rdc vscode check` finds, or null. */
  findVSCode?: () => Promise<{ path: string; version?: string } | null>;
  /** The Remote-SSH extension probe `rdc vscode check` uses. */
  hasRemoteSsh?: () => Promise<boolean>;
  /** The OpenSSH client's `ssh -V` banner, or null when no ssh runs. */
  sshVersion?: () => string | null;
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

/** The Windows-only client checks: VS Code with Remote-SSH, and the OpenSSH client. */
export async function checkWindowsClient(deps: WindowsClientDeps = {}): Promise<CheckResult[]> {
  return [...(await checkVsCode(deps)), checkSshClient(deps)];
}
