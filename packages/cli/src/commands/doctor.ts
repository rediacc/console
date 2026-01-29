import { Command } from 'commander';
import { execSync, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import chalk from 'chalk';
import { DEFAULTS } from '@rediacc/shared/config';
import { t } from '../i18n/index.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { isSEA as isSEAEmbedded, getEmbeddedMetadata } from '../services/embedded-assets.js';
import { isSEA } from '../utils/platform.js';
import { VERSION } from '../version.js';
import type { OutputFormat } from '../types/index.js';

// ============================================================================
// Types
// ============================================================================

type CheckStatus = 'ok' | 'warn' | 'fail';

interface CheckResult {
  name: string;
  value: string;
  status: CheckStatus;
  hint?: string;
}

interface CheckSection {
  title: string;
  checks: CheckResult[];
}

// ============================================================================
// Helpers
// ============================================================================

function commandExists(cmd: string): boolean {
  try {
    execSync(`which ${cmd}`, { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function runCommand(cmd: string, args: string[]): { ok: boolean; output: string } {
  try {
    const result = spawnSync(cmd, args, { encoding: 'utf-8', timeout: 10_000 });
    if (result.status === 0) {
      return { ok: true, output: (result.stdout ?? '').trim() };
    }
    return { ok: false, output: (result.stderr ?? result.stdout ?? '').trim() };
  } catch {
    return { ok: false, output: '' };
  }
}

function resolveRenetPath(contextRenetPath?: string): string | null {
  // Try context-configured path first
  if (contextRenetPath && contextRenetPath !== DEFAULTS.CONTEXT.RENET_BINARY) {
    if (existsSync(contextRenetPath)) {
      return contextRenetPath;
    }
  }

  // Fall back to PATH lookup
  try {
    return execSync('which renet', { encoding: 'utf-8' }).trim();
  } catch {
    return null;
  }
}

// ============================================================================
// Check Implementations
// ============================================================================

function checkEnvironment(): CheckSection {
  const checks: CheckResult[] = [];

  // Node.js version
  checks.push({
    name: t('commands.doctor.checks.nodeVersion'),
    value: process.version,
    status: 'ok',
  });

  // CLI version
  checks.push({
    name: t('commands.doctor.checks.cliVersion'),
    value: VERSION,
    status: 'ok',
  });

  // SEA mode
  const seaActive = isSEA();
  checks.push({
    name: t('commands.doctor.checks.seaMode'),
    value: seaActive ? t('commands.doctor.seaActive') : t('commands.doctor.devMode'),
    status: 'ok',
  });

  // Go installed
  if (commandExists('go')) {
    const goResult = runCommand('go', ['version']);
    const goVersion = goResult.ok
      ? goResult.output.replace(/^go version\s+/, '').split(/\s/)[0]
      : 'unknown';
    checks.push({
      name: t('commands.doctor.checks.goInstalled'),
      value: goVersion,
      status: 'ok',
    });
  } else {
    checks.push({
      name: t('commands.doctor.checks.goInstalled'),
      value: t('commands.doctor.notInstalled'),
      status: 'warn',
      hint: 'Install Go from https://go.dev/dl/',
    });
  }

  // Docker available
  if (commandExists('docker')) {
    const dockerResult = runCommand('docker', ['--version']);
    const dockerVersion = dockerResult.ok
      ? dockerResult.output.replace(/^Docker version\s+/, '').split(/,/)[0]
      : 'unknown';
    checks.push({
      name: t('commands.doctor.checks.dockerAvailable'),
      value: `Docker ${dockerVersion}`,
      status: 'ok',
    });
  } else {
    checks.push({
      name: t('commands.doctor.checks.dockerAvailable'),
      value: t('commands.doctor.notInstalled'),
      status: 'warn',
      hint: 'Install Docker from https://docs.docker.com/get-docker/',
    });
  }

  return {
    title: t('commands.doctor.sections.environment'),
    checks,
  };
}

async function checkRenet(): Promise<CheckSection> {
  const checks: CheckResult[] = [];

  // Resolve renet path from context or PATH
  let renetPath: string | null = null;
  try {
    const localConfig = await contextService.getLocalConfig();
    renetPath = resolveRenetPath(localConfig.renetPath);
  } catch {
    // Not in local mode or no config — fall back to PATH
    renetPath = resolveRenetPath();
  }

  // Binary found
  if (!renetPath) {
    checks.push({
      name: t('commands.doctor.checks.renetBinary'),
      value: t('commands.doctor.notInstalled'),
      status: 'fail',
      hint: 'Build renet with: ./run.sh build renet',
    });
  } else {
    checks.push({
      name: t('commands.doctor.checks.renetBinary'),
      value: renetPath,
      status: 'ok',
    });

    // Renet version
    const versionResult = runCommand(renetPath, ['version']);
    if (versionResult.ok) {
      checks.push({
        name: t('commands.doctor.checks.renetVersion'),
        value: versionResult.output,
        status: 'ok',
      });
    } else {
      checks.push({
        name: t('commands.doctor.checks.renetVersion'),
        value: 'failed to run',
        status: 'fail',
        hint: 'Renet binary found but could not be executed',
      });
    }
  }

  // Embedded assets check — always runs, independent of binary on PATH
  if (isSEA() && isSEAEmbedded()) {
    try {
      const metadata = getEmbeddedMetadata();
      const archs = Object.keys(metadata.binaries).join(', ');

      checks.push({
        name: t('commands.doctor.checks.renetCriu'),
        value: `yes (${archs})`,
        status: 'ok',
      });
      checks.push({
        name: t('commands.doctor.checks.renetRsync'),
        value: `yes (${archs})`,
        status: 'ok',
      });
    } catch {
      checks.push({
        name: t('commands.doctor.checks.renetCriu'),
        value: 'not available',
        status: 'warn',
      });
      checks.push({
        name: t('commands.doctor.checks.renetRsync'),
        value: 'not available',
        status: 'warn',
      });
    }
  } else if (!isSEA()) {
    // Dev mode — check for embed asset directories
    const embedAssetsDir = 'private/renet/pkg/embed/assets';
    const hasEmbedAssets = existsSync(embedAssetsDir);

    checks.push({
      name: t('commands.doctor.checks.renetCriu'),
      value: hasEmbedAssets ? 'yes (dev embed assets found)' : 'no (dev embed assets missing)',
      status: hasEmbedAssets ? 'ok' : 'warn',
      hint: hasEmbedAssets ? undefined : 'Build renet embed assets with: ./run.sh build renet',
    });
    checks.push({
      name: t('commands.doctor.checks.renetRsync'),
      value: hasEmbedAssets ? 'yes (dev embed assets found)' : 'no (dev embed assets missing)',
      status: hasEmbedAssets ? 'ok' : 'warn',
      hint: hasEmbedAssets ? undefined : 'Build renet embed assets with: ./run.sh build renet',
    });
  }

  return { title: t('commands.doctor.sections.renet'), checks };
}

async function checkConfiguration(): Promise<CheckSection> {
  const checks: CheckResult[] = [];

  // Active context
  const contextName = contextService.getCurrentName();
  const context = await contextService.getCurrent();

  if (context) {
    checks.push({
      name: t('commands.doctor.checks.activeContext'),
      value: contextName,
      status: 'ok',
    });
  } else {
    checks.push({
      name: t('commands.doctor.checks.activeContext'),
      value: t('commands.doctor.notConfigured'),
      status: 'warn',
      hint: 'Create a context with: rdc context create <name> or rdc login',
    });
  }

  // Context mode
  const mode = context?.mode ?? 'cloud';
  checks.push({
    name: t('commands.doctor.checks.contextMode'),
    value: mode,
    status: 'ok',
  });

  // Local mode extras
  if (mode === 'local') {
    const machineCount = context?.machines ? Object.keys(context.machines).length : 0;
    checks.push({
      name: t('commands.doctor.checks.machines'),
      value: `${machineCount} configured`,
      status: machineCount > 0 ? 'ok' : 'warn',
      hint: machineCount === 0 ? 'Add machines with: rdc context add-machine' : undefined,
    });

    const sshKeyPath = context?.ssh?.privateKeyPath;
    if (sshKeyPath && existsSync(sshKeyPath)) {
      checks.push({
        name: t('commands.doctor.checks.sshKey'),
        value: sshKeyPath,
        status: 'ok',
      });
    } else {
      checks.push({
        name: t('commands.doctor.checks.sshKey'),
        value: sshKeyPath ?? t('commands.doctor.notConfigured'),
        status: sshKeyPath ? 'fail' : 'warn',
        hint: sshKeyPath
          ? `SSH key not found at: ${sshKeyPath}`
          : 'Configure SSH with: rdc context set-ssh',
      });
    }
  }

  return { title: t('commands.doctor.sections.configuration'), checks };
}

async function checkAuthentication(): Promise<CheckSection> {
  const checks: CheckResult[] = [];

  const isAuth = await authService.isAuthenticated();
  const email = await authService.getStoredEmail();

  if (isAuth && email) {
    checks.push({
      name: t('commands.doctor.checks.authStatus'),
      value: `Authenticated as ${email}`,
      status: 'ok',
    });
  } else if (isAuth) {
    checks.push({
      name: t('commands.doctor.checks.authStatus'),
      value: 'Authenticated',
      status: 'ok',
    });
  } else {
    checks.push({
      name: t('commands.doctor.checks.authStatus'),
      value: t('commands.doctor.notAuthenticated'),
      status: 'warn',
      hint: 'Authenticate with: rdc login',
    });
  }

  return { title: t('commands.doctor.sections.authentication'), checks };
}

// ============================================================================
// Output Formatting
// ============================================================================

const STATUS_ICONS: Record<CheckStatus, string> = {
  ok: chalk.green('OK'),
  warn: chalk.yellow('WARN'),
  fail: chalk.red('FAIL'),
};

function formatSection(section: CheckSection): string {
  const lines: string[] = [];
  lines.push(`  ${chalk.bold(section.title)}`);

  for (const check of section.checks) {
    const name = check.name.padEnd(16);
    // Ensure at least 2 spaces between value and status
    const valueWidth = Math.max(38, check.value.length + 2);
    const value = check.value.padEnd(valueWidth);
    const status = STATUS_ICONS[check.status];
    lines.push(`    ${name}${value}${status}`);
    if (check.hint) {
      lines.push(`    ${' '.repeat(16)}${chalk.dim(check.hint)}`);
    }
  }

  return lines.join('\n');
}

function computeExitCode(sections: CheckSection[]): number {
  let worstStatus: CheckStatus = 'ok';

  for (const section of sections) {
    for (const check of section.checks) {
      if (check.status === 'fail') {
        worstStatus = 'fail';
      } else if (check.status === 'warn' && worstStatus !== 'fail') {
        worstStatus = 'warn';
      }
    }
  }

  if (worstStatus === 'fail') return 2;
  if (worstStatus === 'warn') return 1;
  return 0;
}

function formatSummary(sections: CheckSection[]): string {
  let warnings = 0;
  let errors = 0;

  for (const section of sections) {
    for (const check of section.checks) {
      if (check.status === 'warn') warnings++;
      if (check.status === 'fail') errors++;
    }
  }

  if (errors > 0) {
    return chalk.red(`  ${t('commands.doctor.hasErrors', { count: errors })}`);
  }
  if (warnings > 0) {
    return chalk.yellow(`  ${t('commands.doctor.hasWarnings', { count: warnings })}`);
  }
  return chalk.green(`  ${t('commands.doctor.allPassed')}`);
}

function formatJson(sections: CheckSection[]): string {
  const result: Record<string, CheckResult[]> = {};
  for (const section of sections) {
    result[section.title] = section.checks;
  }
  return JSON.stringify(result, null, 2);
}

// ============================================================================
// Command Registration
// ============================================================================

export function registerDoctorCommand(program: Command): void {
  program
    .command('doctor')
    .description(t('commands.doctor.description'))
    .option('--output <format>', t('options.outputFormat'))
    .action(async (options: { output?: string }) => {
      const outputFormat = (options.output ?? program.opts().output) as OutputFormat | undefined;

      // Run all checks
      const sections: CheckSection[] = [];
      sections.push(checkEnvironment());
      sections.push(await checkRenet());
      sections.push(await checkConfiguration());
      sections.push(await checkAuthentication());

      // Output results
      if (outputFormat === 'json') {
        console.log(formatJson(sections));
      } else {
        console.log();
        console.log(`  ${chalk.bold(t('commands.doctor.title'))}`);
        console.log();

        for (const section of sections) {
          console.log(formatSection(section));
          console.log();
        }

        console.log(formatSummary(sections));
        console.log();
      }

      const exitCode = computeExitCode(sections);
      if (exitCode !== 0) {
        process.exit(exitCode);
      }
    });
}
