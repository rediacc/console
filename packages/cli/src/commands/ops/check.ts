import { execSync, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import chalk from 'chalk';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { opsExecutorService } from '../../services/ops-executor.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';
import type { OutputFormat } from '../../types/index.js';

type CheckStatus = 'ok' | 'warn' | 'fail';

interface CheckResult {
  name: string;
  value: string;
  status: CheckStatus;
  hint?: string;
}

interface HostCheckResponse {
  platform: string;
  arch: string;
  backend: string;
  checks: CheckResult[];
}

// ============================================================================
// Helpers
// ============================================================================

function buildToolCheck(cmd: string, hint: string): CheckResult {
  const exists = commandExists(cmd);
  return {
    name: cmd,
    value: exists ? getCommandVersion(cmd) : 'not found',
    status: exists ? 'ok' : 'fail',
    hint: exists ? undefined : hint,
  };
}

// ============================================================================
// Fallback checks (used when renet is not available)
// ============================================================================

function commandExists(cmd: string): boolean {
  try {
    const whichCmd = process.platform === 'win32' ? `where.exe ${cmd}` : `which ${cmd}`;
    execSync(whichCmd, { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function getCommandVersion(cmd: string, args: string[] = ['--version']): string {
  try {
    const result = spawnSync(cmd, args, { encoding: 'utf-8', timeout: 10_000 });
    if (result.status === 0) return result.stdout.trim().split('\n')[0];
    return 'unknown';
  } catch {
    return 'not found';
  }
}

function checkLibvirtdStatus(): CheckResult {
  try {
    const result = spawnSync('systemctl', ['is-active', 'libvirtd'], {
      encoding: 'utf-8',
      timeout: 5000,
    });
    const active = result.stdout.trim() === 'active';
    return {
      name: 'libvirtd',
      value: active ? 'active' : 'inactive',
      status: active ? 'ok' : 'warn',
      hint: active ? undefined : 'Start libvirtd: sudo systemctl enable --now libvirtd',
    };
  } catch {
    return {
      name: 'libvirtd',
      value: 'unknown',
      status: 'warn',
      hint: 'Could not check libvirtd status',
    };
  }
}

function checkLinuxPrereqs(): CheckResult[] {
  const kvmExists = existsSync('/dev/kvm');

  return [
    {
      name: '/dev/kvm',
      value: kvmExists ? 'available' : 'not found',
      status: kvmExists ? 'ok' : 'fail',
      hint: kvmExists ? undefined : 'Enable KVM in BIOS/UEFI or check kernel module',
    },
    buildToolCheck('docker', 'Install Docker: curl -fsSL https://get.docker.com | sh'),
    buildToolCheck('virsh', 'Install libvirt: sudo apt install libvirt-daemon-system'),
    buildToolCheck('virt-install', 'Install virt-install: sudo apt install virtinst'),
    buildToolCheck('qemu-img', 'Install qemu-img: sudo apt install qemu-utils'),
    buildToolCheck(
      'cloud-localds',
      'Install cloud-image-utils: sudo apt install cloud-image-utils'
    ),
    checkLibvirtdStatus(),
  ];
}

function checkMacOSPrereqs(): CheckResult[] {
  const qemuCmd = process.arch === 'arm64' ? 'qemu-system-aarch64' : 'qemu-system-x86_64';
  const brewExists = commandExists('brew');

  return [
    buildToolCheck(qemuCmd, 'Install QEMU: brew install qemu'),
    buildToolCheck('qemu-img', 'Install QEMU: brew install qemu'),
    buildToolCheck('mkisofs', 'Install cdrtools: brew install cdrtools'),
    {
      name: 'brew',
      value: brewExists ? 'available' : 'not found',
      status: brewExists ? 'ok' : 'warn',
      hint: brewExists ? undefined : 'Install Homebrew: https://brew.sh',
    },
  ];
}

function checkWindowsPrereqs(): CheckResult[] {
  // Hyper-V check
  let hypervStatus: CheckResult;
  try {
    const result = spawnSync(
      'powershell.exe',
      [
        '-NoProfile',
        '-NonInteractive',
        '-Command',
        '(Get-WindowsOptionalFeature -FeatureName Microsoft-Hyper-V-All -Online).State',
      ],
      { encoding: 'utf-8', timeout: 15_000 }
    );
    const state = (result.stdout || '').trim().toLowerCase();
    hypervStatus = {
      name: 'Hyper-V',
      value: state === 'enabled' ? 'enabled' : state || 'unknown',
      status: state === 'enabled' ? 'ok' : 'fail',
      hint:
        state === 'enabled'
          ? undefined
          : 'Enable Hyper-V: Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All',
    };
  } catch {
    hypervStatus = {
      name: 'Hyper-V',
      value: 'unknown',
      status: 'fail',
      hint: 'Could not check Hyper-V status',
    };
  }

  return [
    hypervStatus,
    buildToolCheck('qemu-img', 'Install QEMU: winget install SoftwareFreedomConservancy.QEMU'),
    buildToolCheck('ssh', 'Install OpenSSH: Settings > Apps > Optional Features > OpenSSH Client'),
  ];
}

// ============================================================================
// Output Formatting
// ============================================================================

function getStatusIcons(useColor: boolean) {
  return {
    ok: useColor ? chalk.green('\u2713') : '[OK]',
    warn: useColor ? chalk.yellow('!') : '[WARN]',
    fail: useColor ? chalk.red('\u2717') : '[FAIL]',
  };
}

function formatCheckLine(
  check: CheckResult,
  icons: ReturnType<typeof getStatusIcons>,
  useColor: boolean
): string[] {
  const lines = [`  ${icons[check.status]} ${check.name}: ${check.value}`];
  if (check.hint) {
    const prefix = useColor ? '     ' : '       ';
    lines.push(`${prefix}${useColor ? chalk.dim(check.hint) : check.hint}`);
  }
  return lines;
}

function formatCheckTable(checks: CheckResult[], useColor: boolean): string {
  const icons = getStatusIcons(useColor);
  return checks.flatMap((c) => formatCheckLine(c, icons, useColor)).join('\n');
}

// ============================================================================
// Display helpers
// ============================================================================

function displayChecksTable(
  platformLabel: string,
  backend: string,
  arch: string,
  checks: CheckResult[]
): void {
  const useColor = process.stdout.isTTY !== false;
  const title = t('commands.ops.check.title');
  outputService.info(`${title} (${platformLabel}, ${backend}, ${arch})`);
  outputService.print(formatCheckTable(checks, useColor));

  const failCount = checks.filter((c) => c.status === 'fail').length;
  outputService.print('');
  if (failCount === 0) {
    outputService.success(t('commands.ops.check.allPassed'));
  } else {
    outputService.warn(t('commands.ops.check.hasMissing', { count: failCount }));
  }
}

function getLocalCheckData(): HostCheckResponse {
  if (process.platform === 'darwin') {
    return { platform: 'macOS', backend: 'qemu', arch: process.arch, checks: checkMacOSPrereqs() };
  }
  if (process.platform === 'win32') {
    return {
      platform: 'Windows',
      backend: 'hyperv',
      arch: process.arch,
      checks: checkWindowsPrereqs(),
    };
  }
  return { platform: 'Linux', backend: 'kvm', arch: process.arch, checks: checkLinuxPrereqs() };
}

// ============================================================================
// Command Registration
// ============================================================================

export function registerOpsCheckCommand(ops: Command, program: Command): void {
  ops
    .command('check')
    .description(t('commands.ops.check.description'))
    .action(async () => {
      try {
        const format = program.opts().output as OutputFormat;

        // Try renet first (authoritative source)
        let response: HostCheckResponse | null = null;
        try {
          response = await opsExecutorService.runOpsJSON<HostCheckResponse>('host', ['check']);
        } catch {
          // renet unavailable — fall back to local TypeScript checks
        }

        const data = response ?? getLocalCheckData();

        if (format === 'json') {
          outputService.print(data, format);
          return;
        }

        if (!response) {
          outputService.warn(t('commands.ops.check.localFallback'));
        }

        const platformLabel = data.platform === 'darwin' ? 'macOS' : data.platform;
        displayChecksTable(platformLabel, data.backend, data.arch, data.checks);
      } catch (error) {
        handleError(error);
      }
    });
}
