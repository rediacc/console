import { execSync, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import chalk from 'chalk';
import { Command } from 'commander';
import { DEFAULTS } from '@rediacc/shared/config';
import { t } from '../i18n/index.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { getEmbeddedMetadata, isSEA as isSEAEmbedded } from '../services/embedded-assets.js';
import { outputService } from '../services/output.js';
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
      return { ok: true, output: result.stdout.trim() };
    }
    return { ok: false, output: (result.stderr || result.stdout).trim() };
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

  checks.push(
    { name: t('commands.doctor.checks.nodeVersion'), value: process.version, status: 'ok' },
    { name: t('commands.doctor.checks.cliVersion'), value: VERSION, status: 'ok' },
    {
      name: t('commands.doctor.checks.seaMode'),
      value: isSEA() ? t('commands.doctor.seaActive') : t('commands.doctor.devMode'),
      status: 'ok',
    }
  );

  // Go installed
  if (commandExists('go')) {
    const goResult = runCommand('go', ['version']);
    const goVersion = goResult.ok
      ? goResult.output.replace(/^go version\s+/, '').split(/\s/)[0]
      : 'unknown';
    checks.push({ name: t('commands.doctor.checks.goInstalled'), value: goVersion, status: 'ok' });
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

  return { title: t('commands.doctor.sections.environment'), checks };
}

function checkRenetBinary(checks: CheckResult[], renetPath: string | null): void {
  if (renetPath) {
    checks.push({ name: t('commands.doctor.checks.renetBinary'), value: renetPath, status: 'ok' });

    const versionResult = runCommand(renetPath, ['version']);
    checks.push(
      versionResult.ok
        ? {
            name: t('commands.doctor.checks.renetVersion'),
            value: versionResult.output,
            status: 'ok',
          }
        : {
            name: t('commands.doctor.checks.renetVersion'),
            value: 'failed to run',
            status: 'fail',
            hint: 'Renet binary found but could not be executed',
          }
    );
  } else {
    checks.push({
      name: t('commands.doctor.checks.renetBinary'),
      value: t('commands.doctor.notInstalled'),
      status: 'fail',
      hint: 'Build renet with: ./run.sh build renet',
    });
  }
}

function checkSEAEmbeddedAssets(checks: CheckResult[]): void {
  try {
    const metadata = getEmbeddedMetadata();
    const archs = Object.keys(metadata.binaries).join(', ');
    checks.push(
      { name: t('commands.doctor.checks.renetCriu'), value: `yes (${archs})`, status: 'ok' },
      { name: t('commands.doctor.checks.renetRsync'), value: `yes (${archs})`, status: 'ok' }
    );
  } catch {
    checks.push(
      { name: t('commands.doctor.checks.renetCriu'), value: 'not available', status: 'warn' },
      { name: t('commands.doctor.checks.renetRsync'), value: 'not available', status: 'warn' }
    );
  }
}

function checkRenetEmbeddedAssets(checks: CheckResult[]): void {
  if (isSEA() && isSEAEmbedded()) {
    checkSEAEmbeddedAssets(checks);
    return;
  }

  if (!isSEA()) {
    const hasEmbedAssets = existsSync('private/renet/pkg/embed/assets');
    const value = hasEmbedAssets ? 'yes (dev embed assets found)' : 'no (dev embed assets missing)';
    const status: CheckStatus = hasEmbedAssets ? 'ok' : 'warn';
    const hint = hasEmbedAssets ? undefined : 'Build renet embed assets with: ./run.sh build renet';

    checks.push(
      { name: t('commands.doctor.checks.renetCriu'), value, status, hint },
      { name: t('commands.doctor.checks.renetRsync'), value, status, hint }
    );
  }
}

async function checkRenet(): Promise<CheckSection> {
  const checks: CheckResult[] = [];

  let renetPath: string | null = null;
  try {
    const localConfig = await contextService.getLocalConfig();
    renetPath = resolveRenetPath(localConfig.renetPath);
  } catch {
    renetPath = resolveRenetPath();
  }

  checkRenetBinary(checks, renetPath);
  checkRenetEmbeddedAssets(checks);

  return { title: t('commands.doctor.sections.renet'), checks };
}

async function checkConfiguration(): Promise<CheckSection> {
  const checks: CheckResult[] = [];

  const contextName = contextService.getCurrentName();
  const context = await contextService.getCurrent();

  checks.push(
    context
      ? { name: t('commands.doctor.checks.activeContext'), value: contextName, status: 'ok' }
      : {
          name: t('commands.doctor.checks.activeContext'),
          value: t('commands.doctor.notConfigured'),
          status: 'warn',
          hint: 'Create a context with: rdc context create <name> or rdc auth login',
        }
  );

  const mode = context?.mode ?? DEFAULTS.CONTEXT.MODE;
  checks.push({ name: t('commands.doctor.checks.contextMode'), value: mode, status: 'ok' });

  if (mode !== 'cloud') {
    await addSelfHostedModeChecks(checks, context);
  }

  return { title: t('commands.doctor.sections.configuration'), checks };
}

async function addSelfHostedModeChecks(
  checks: CheckResult[],
  context: Awaited<ReturnType<typeof contextService.getCurrent>>
): Promise<void> {
  try {
    const state = await contextService.getResourceState();
    const machineCount = Object.keys(state.getMachines()).length;
    checks.push({
      name: t('commands.doctor.checks.machines'),
      value: `${machineCount} configured`,
      status: machineCount > 0 ? 'ok' : 'warn',
      hint: machineCount === 0 ? 'Add machines with: rdc context add-machine' : undefined,
    });
  } catch {
    checks.push({
      name: t('commands.doctor.checks.machines'),
      value: '[unable to load]',
      status: 'warn',
      hint: 'Could not load resource state (encrypted or S3 unreachable)',
    });
  }

  const sshKeyPath = context?.ssh?.privateKeyPath;
  if (sshKeyPath && existsSync(sshKeyPath)) {
    checks.push({ name: t('commands.doctor.checks.sshKey'), value: sshKeyPath, status: 'ok' });
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

async function checkVirtualization(): Promise<CheckSection> {
  const checks: CheckResult[] = [];

  // Windows: skip with a note
  if (process.platform === 'win32') {
    checks.push({
      name: t('commands.doctor.checks.opsPrereqs'),
      value: t('commands.doctor.opsNotSupported', { platform: process.platform }),
      status: 'warn',
    });
    return { title: t('commands.doctor.sections.virtualization'), checks };
  }

  // Try to find renet
  let renetPath: string | null = null;
  try {
    const localConfig = await contextService.getLocalConfig();
    renetPath = resolveRenetPath(localConfig.renetPath);
  } catch {
    renetPath = resolveRenetPath();
  }

  if (!renetPath) {
    checks.push({
      name: t('commands.doctor.checks.opsPrereqs'),
      value: t('commands.doctor.opsSkipped'),
      status: 'warn',
      hint: 'Build renet or install it in PATH to enable checks',
    });
    return { title: t('commands.doctor.sections.virtualization'), checks };
  }

  // Run renet ops host check --json
  const result = runCommand(renetPath, ['ops', 'host', 'check', '--json']);
  if (!result.ok) {
    checks.push({
      name: t('commands.doctor.checks.opsPrereqs'),
      value: 'check failed',
      status: 'warn',
      hint: result.output.split('\n')[0] || 'Run renet ops host check for details',
    });
    return { title: t('commands.doctor.sections.virtualization'), checks };
  }

  // Parse and map results — cap status at 'warn' (ops is optional)
  try {
    const response = JSON.parse(result.output);
    for (const check of response.checks) {
      checks.push({
        name: check.name,
        value: check.value,
        status: check.status === 'fail' ? 'warn' : check.status,
        hint: check.hint ?? undefined,
      });
    }
  } catch {
    checks.push({
      name: t('commands.doctor.checks.opsPrereqs'),
      value: 'invalid response',
      status: 'warn',
    });
  }

  return { title: t('commands.doctor.sections.virtualization'), checks };
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
      hint: 'Authenticate with: rdc auth login',
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

  const nameWidth = Math.max(16, ...section.checks.map((c) => c.name.length + 2));

  for (const check of section.checks) {
    const name = check.name.padEnd(nameWidth);
    const valueWidth = Math.max(38, check.value.length + 2);
    const value = check.value.padEnd(valueWidth);
    const status = STATUS_ICONS[check.status];
    lines.push(`    ${name}${value}${status}`);
    if (check.hint) {
      lines.push(`    ${' '.repeat(nameWidth)}${chalk.dim(check.hint)}`);
    }
  }

  return lines.join('\n');
}

function countByStatus(sections: CheckSection[]): { warnings: number; errors: number } {
  let warnings = 0;
  let errors = 0;

  for (const section of sections) {
    for (const check of section.checks) {
      if (check.status === 'warn') warnings++;
      if (check.status === 'fail') errors++;
    }
  }

  return { warnings, errors };
}

function computeExitCode(sections: CheckSection[]): number {
  const { warnings, errors } = countByStatus(sections);
  if (errors > 0) return 2;
  if (warnings > 0) return 1;
  return 0;
}

function formatSummary(sections: CheckSection[]): string {
  const { warnings, errors } = countByStatus(sections);

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

      const context = await contextService.getCurrent();
      const mode = context?.mode ?? DEFAULTS.CONTEXT.MODE;

      const sections: CheckSection[] = [
        checkEnvironment(),
        await checkRenet(),
        await checkConfiguration(),
        ...(mode === 'cloud' ? [await checkAuthentication()] : []),
        await checkVirtualization(),
      ];

      if (outputFormat === 'json') {
        outputService.print(formatJson(sections));
      } else {
        outputService.print('');
        outputService.print(`  ${chalk.bold(t('commands.doctor.title'))}`);
        outputService.print('');

        for (const section of sections) {
          outputService.print(formatSection(section));
          outputService.print('');
        }

        outputService.print(formatSummary(sections));
        outputService.print('');
      }

      const exitCode = computeExitCode(sections);
      if (exitCode !== 0) {
        process.exit(exitCode);
      }
    });
}
