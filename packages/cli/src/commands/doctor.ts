import { execSync, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { DEFAULTS } from '@rediacc/shared/config';
import { isSubscriptionActive, type SubscriptionStatus } from '@rediacc/shared/subscription';
import chalk from 'chalk';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { authService } from '../services/auth.js';
import { configService } from '../services/config-resources.js';
import { getEmbeddedMetadata, isSEA as isSEAEmbedded } from '../services/embedded-assets.js';
import { fetchSubscriptionLicenseReport } from '../services/license.js';
import { outputService } from '../services/output.js';
import { getSubscriptionServerUrl, getSubscriptionTokenState } from '../services/subscription-auth.js';
import { resolveChannel } from '../services/updater.js';
import type { OutputFormat } from '../types/index.js';
import { hasCloudCredentials } from '../types/index.js';
import { isSEA } from '../utils/platform.js';
import { VERSION } from '../version.js';

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
  if (contextRenetPath && contextRenetPath !== DEFAULTS.CONTEXT.RENET_BINARY) {
    if (existsSync(contextRenetPath)) return contextRenetPath;
  }
  try {
    const whichCmd = process.platform === 'win32' ? 'where.exe renet' : 'which renet';
    return execSync(whichCmd, { encoding: 'utf-8' }).trim().split('\n')[0];
  } catch {
    return null;
  }
}

function checkToolVersion(
  cmd: string,
  args: string[],
  extractVersion: (output: string) => string,
  nameKey: string,
  hint: string
): CheckResult {
  if (!commandExists(cmd)) {
    return { name: t(nameKey), value: t('commands.doctor.notInstalled'), status: 'warn', hint };
  }
  const result = runCommand(cmd, args);
  const version = result.ok ? extractVersion(result.output) : 'unknown';
  return { name: t(nameKey), value: version, status: 'ok' };
}

function checkEnvironment(): CheckSection {
  const checks: CheckResult[] = [
    { name: t('commands.doctor.checks.nodeVersion'), value: process.version, status: 'ok' },
    { name: t('commands.doctor.checks.cliVersion'), value: VERSION, status: 'ok' },
    {
      name: t('commands.doctor.checks.seaMode'),
      value: isSEA() ? t('commands.doctor.seaActive') : t('commands.doctor.devMode'),
      status: 'ok',
    },
    { name: 'Update channel', value: resolveChannel(), status: 'ok' },
    (() => {
      try {
        return { name: 'Account server', value: getSubscriptionServerUrl(), status: 'ok' as const };
      } catch {
        return { name: 'Account server', value: 'not configured', status: 'warn' as const };
      }
    })(),
    checkToolVersion(
      'go',
      ['version'],
      (o) => o.replace(/^go version\s+/, '').split(/\s/)[0],
      'commands.doctor.checks.goInstalled',
      'Install Go from https://go.dev/dl/'
    ),
    checkToolVersion(
      'docker',
      ['--version'],
      (o) => `Docker ${o.replace(/^Docker version\s+/, '').split(/,/)[0]}`,
      'commands.doctor.checks.dockerAvailable',
      'Install Docker from https://docs.docker.com/get-docker/'
    ),
  ];
  return { title: t('commands.doctor.sections.environment'), checks };
}

function checkRenetBinary(checks: CheckResult[], renetPath: string | null): void {
  if (!renetPath) {
    checks.push({
      name: t('commands.doctor.checks.renetBinary'),
      value: t('commands.doctor.notInstalled'),
      status: isSEA() ? 'warn' : 'fail',
      hint: isSEA()
        ? 'Renet is optional on workstations (only needed for local VM ops). It is auto-provisioned to remote machines.'
        : 'Build renet with: ./run.sh build renet',
    });
    return;
  }
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
}

function pushEmbedAssetChecks(
  checks: CheckResult[],
  value: string,
  status: CheckStatus,
  hint?: string
): void {
  checks.push(
    { name: t('commands.doctor.checks.renetCriu'), value, status, hint },
    { name: t('commands.doctor.checks.renetRsync'), value, status, hint }
  );
}

function checkDevEmbedAssets(checks: CheckResult[]): void {
  const hasEmbedAssets = existsSync('private/renet/pkg/embed/assets');
  pushEmbedAssetChecks(
    checks,
    hasEmbedAssets ? 'yes (dev embed assets found)' : 'no (dev embed assets missing)',
    hasEmbedAssets ? 'ok' : 'warn',
    hasEmbedAssets ? undefined : 'Build renet embed assets with: ./run.sh build renet'
  );
}

function checkRenetEmbeddedAssets(checks: CheckResult[]): void {
  if (isSEA() && isSEAEmbedded()) {
    try {
      const archs = Object.keys(getEmbeddedMetadata().binaries).join(', ');
      pushEmbedAssetChecks(checks, `yes (${archs})`, 'ok');
    } catch {
      pushEmbedAssetChecks(checks, 'not available', 'warn');
    }
    return;
  }
  if (!isSEA()) checkDevEmbedAssets(checks);
}

async function findRenetPath(): Promise<string | null> {
  try {
    const localConfig = await configService.getLocalConfig();
    return resolveRenetPath(localConfig.renetPath);
  } catch {
    return resolveRenetPath();
  }
}

async function checkRenet(): Promise<CheckSection> {
  const checks: CheckResult[] = [];
  const renetPath = await findRenetPath();
  checkRenetBinary(checks, renetPath);
  checkRenetEmbeddedAssets(checks);
  return { title: t('commands.doctor.sections.renet'), checks };
}

async function checkMachineCount(checks: CheckResult[]): Promise<void> {
  try {
    const state = await configService.getResourceState();
    const machineCount = Object.keys(state.getMachines()).length;
    checks.push({
      name: t('commands.doctor.checks.machines'),
      value: `${machineCount} configured`,
      status: machineCount > 0 ? 'ok' : 'warn',
      hint: machineCount === 0 ? 'Add machines with: rdc config machine add' : undefined,
    });
  } catch {
    checks.push({
      name: t('commands.doctor.checks.machines'),
      value: '[unable to load]',
      status: 'warn',
      hint: 'Could not load resource state (encrypted or S3 unreachable)',
    });
  }
}

function checkSshKey(checks: CheckResult[], sshKeyPath: string | undefined): void {
  if (sshKeyPath && existsSync(sshKeyPath)) {
    checks.push({ name: t('commands.doctor.checks.sshKey'), value: sshKeyPath, status: 'ok' });
    return;
  }
  checks.push({
    name: t('commands.doctor.checks.sshKey'),
    value: sshKeyPath ?? t('commands.doctor.notConfigured'),
    status: sshKeyPath ? 'fail' : 'warn',
    hint: sshKeyPath
      ? `SSH key not found at: ${sshKeyPath}`
      : 'Set SSH key during config init: rdc config init <name> --ssh-key <path>',
  });
}

async function checkConfiguration(): Promise<CheckSection> {
  const checks: CheckResult[] = [];
  const contextName = configService.getCurrentName();
  const context = await configService.getCurrent();
  checks.push(
    context
      ? { name: t('commands.doctor.checks.activeConfig'), value: contextName, status: 'ok' }
      : {
          name: t('commands.doctor.checks.activeConfig'),
          value: t('commands.doctor.notConfigured'),
          status: 'warn',
          hint: 'Default config is created automatically. For named configs: rdc config init <name>',
        }
  );
  const isCloud = hasCloudCredentials(context);
  checks.push({
    name: t('commands.doctor.checks.contextMode'),
    value: isCloud ? 'cloud' : 'local',
    status: 'ok',
  });
  if (!isCloud) {
    await checkMachineCount(checks);
    checkSshKey(checks, context?.ssh?.privateKeyPath);
  }
  return { title: t('commands.doctor.sections.configuration'), checks };
}

async function checkVirtualization(): Promise<CheckSection> {
  const checks: CheckResult[] = [];
  const renetPath = await findRenetPath();
  if (!renetPath) {
    checks.push({
      name: t('commands.doctor.checks.opsPrereqs'),
      value: t('commands.doctor.opsSkipped'),
      status: 'warn',
      hint: 'Build renet or install it in PATH to enable checks',
    });
    return { title: t('commands.doctor.sections.virtualization'), checks };
  }

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
  const isAuth = await authService.isAuthenticated();
  const email = await authService.getStoredEmail();
  let check: CheckResult;
  if (isAuth) {
    const value = email ? `Authenticated as ${email}` : 'Authenticated';
    check = { name: t('commands.doctor.checks.authStatus'), value, status: 'ok' };
  } else {
    check = {
      name: t('commands.doctor.checks.authStatus'),
      value: t('commands.doctor.notAuthenticated'),
      status: 'warn',
      hint: 'Authenticate with: rdc auth login',
    };
  }
  return { title: t('commands.doctor.sections.authentication'), checks: [check] };
}

const SUBSCRIPTION_CHECK_TIMEOUT_MS = 8000;
const TIMEOUT_SENTINEL = Symbol('timeout');
type LicenseReport = Awaited<ReturnType<typeof fetchSubscriptionLicenseReport>> & object;

function getInactiveStatusHint(status: string): string {
  if (status === 'EXPIRED') return 'Subscription expired. Renew at https://www.rediacc.com/account';
  if (status === 'SUSPENDED') return 'Subscription suspended. Contact support or check billing';
  return 'Subscription inactive. Activate at https://www.rediacc.com/account';
}

function checkSubscriptionStatus(checks: CheckResult[], report: LicenseReport): void {
  const status = report.status as SubscriptionStatus;
  if (!isSubscriptionActive(status)) {
    checks.push({
      name: t('commands.doctor.checks.subscriptionStatus'),
      value: `${report.planCode} (${report.status})`,
      status: 'fail',
      hint: getInactiveStatusHint(report.status),
    });
    return;
  }
  if (status === 'GRACE') {
    checks.push({
      name: t('commands.doctor.checks.subscriptionStatus'),
      value: `${report.planCode} (GRACE)`,
      status: 'warn',
      hint: 'Subscription is in grace period. Renew at https://www.rediacc.com/account',
    });
  } else {
    checks.push({
      name: t('commands.doctor.checks.subscriptionStatus'),
      value: `${report.planCode} (ACTIVE)`,
      status: 'ok',
    });
  }
}

function checkMachineSlots(checks: CheckResult[], report: LicenseReport): void {
  const { active, max } = report.machineSlots;
  const value = `${active}/${max}`;
  let status: CheckStatus = 'ok';
  let hint: string | undefined;
  if (active >= max && max > 0) {
    status = 'fail';
    hint = 'All machine slots used. Upgrade plan or deactivate unused machines';
  } else if (max > 0 && active >= max * 0.8) {
    status = 'warn';
    hint = 'Machine slots nearly full. Upgrade plan or deactivate unused machines';
  }
  checks.push({ name: t('commands.doctor.checks.subscriptionMachineSlots'), value, status, hint });
}

function checkRepoLicenses(checks: CheckResult[], report: LicenseReport): void {
  const { totalTrackedRepos, validCount, refreshRecommendedCount, hardExpiredCount } =
    report.repoLicenses;
  const name = t('commands.doctor.checks.subscriptionRepoLicenses');
  let value: string, status: CheckStatus, hint: string | undefined;
  if (totalTrackedRepos === 0) {
    value = 'no tracked repos';
    status = 'ok';
  } else if (hardExpiredCount > 0) {
    value = `${validCount} valid, ${refreshRecommendedCount} need refresh, ${hardExpiredCount} expired`;
    status = 'fail';
    hint = 'Run: rdc subscription refresh -m <machine> to fix expired repo licenses';
  } else if (refreshRecommendedCount > 0) {
    value = `${validCount} valid, ${refreshRecommendedCount} need refresh`;
    status = 'warn';
    hint = 'Run: rdc subscription refresh -m <machine> to refresh repo licenses';
  } else {
    value = `${validCount}/${totalTrackedRepos} valid`;
    status = 'ok';
  }
  checks.push({ name, value, status, hint });
}

async function checkSubscription(): Promise<CheckSection> {
  const checks: CheckResult[] = [];
  const tokenState = getSubscriptionTokenState();

  if (tokenState.kind === 'missing') {
    checks.push({
      name: t('commands.doctor.checks.subscriptionToken'),
      value: t('commands.doctor.notLoggedIn'),
      status: 'warn',
      hint: 'Run: rdc subscription login',
    });
    return { title: t('commands.doctor.sections.subscription'), checks };
  }

  if (tokenState.kind === 'server_mismatch') {
    checks.push({
      name: t('commands.doctor.checks.subscriptionToken'),
      value: t('commands.doctor.serverMismatch'),
      status: 'fail',
      hint: `Token bound to ${tokenState.actualServerUrl}, expected ${tokenState.expectedServerUrl}. Run: rdc subscription login`,
    });
    return { title: t('commands.doctor.sections.subscription'), checks };
  }

  const { token } = tokenState;
  const scopeParts = [token.orgName, token.teamName].filter(Boolean).join(' / ');
  checks.push({
    name: t('commands.doctor.checks.subscriptionToken'),
    value: scopeParts ? `authenticated (${scopeParts})` : 'authenticated',
    status: 'ok',
  });

  const result = await Promise.race([
    fetchSubscriptionLicenseReport(),
    new Promise<typeof TIMEOUT_SENTINEL>((resolve) =>
      setTimeout(() => resolve(TIMEOUT_SENTINEL), SUBSCRIPTION_CHECK_TIMEOUT_MS)
    ),
  ]);

  if (!result || result === TIMEOUT_SENTINEL) {
    const hint =
      result === TIMEOUT_SENTINEL
        ? 'Subscription server did not respond in time. Check network connectivity'
        : 'Check network connectivity or try again later';
    checks.push({
      name: t('commands.doctor.checks.subscriptionStatus'),
      value: t('commands.doctor.subscriptionUnreachable'),
      status: 'warn',
      hint,
    });
    return { title: t('commands.doctor.sections.subscription'), checks };
  }

  checkSubscriptionStatus(checks, result);
  checkMachineSlots(checks, result);
  checkRepoLicenses(checks, result);

  return { title: t('commands.doctor.sections.subscription'), checks };
}

const STATUS_ICONS: Record<CheckStatus, string> = {
  ok: chalk.green('OK'),
  warn: chalk.yellow('WARN'),
  fail: chalk.red('FAIL'),
};

function formatSection(section: CheckSection): string {
  const nameWidth = Math.max(16, ...section.checks.map((c) => c.name.length + 2));
  const lines = [`  ${chalk.bold(section.title)}`];
  for (const check of section.checks) {
    const valueWidth = Math.max(38, check.value.length + 2);
    lines.push(
      `    ${check.name.padEnd(nameWidth)}${check.value.padEnd(valueWidth)}${STATUS_ICONS[check.status]}`
    );
    if (check.hint) lines.push(`    ${' '.repeat(nameWidth)}${chalk.dim(check.hint)}`);
  }
  return lines.join('\n');
}

function countByStatus(sections: CheckSection[]): { warnings: number; errors: number } {
  const allChecks = sections.flatMap((s) => s.checks);
  return {
    warnings: allChecks.filter((c) => c.status === 'warn').length,
    errors: allChecks.filter((c) => c.status === 'fail').length,
  };
}

function computeExitCode(sections: CheckSection[]): number {
  const { warnings, errors } = countByStatus(sections);
  if (errors > 0) return 2;
  if (warnings > 0) return 1;
  return 0;
}

function formatSummary(sections: CheckSection[]): string {
  const { warnings, errors } = countByStatus(sections);
  if (errors > 0) return chalk.red(`  ${t('commands.doctor.hasErrors', { count: errors })}`);
  if (warnings > 0)
    return chalk.yellow(`  ${t('commands.doctor.hasWarnings', { count: warnings })}`);
  return chalk.green(`  ${t('commands.doctor.allPassed')}`);
}

function formatJson(sections: CheckSection[]): string {
  return JSON.stringify(Object.fromEntries(sections.map((s) => [s.title, s.checks])), null, 2);
}

export function registerDoctorCommand(program: Command): void {
  program
    .command('doctor')
    .summary(t('commands.doctor.descriptionShort'))
    .description(t('commands.doctor.description'))
    .option('--output <format>', t('options.outputFormat'))
    .action(async (options: { output?: string }) => {
      const outputFormat = (options.output ?? program.opts().output) as OutputFormat | undefined;
      const context = await configService.getCurrent();
      const isCloud = hasCloudCredentials(context);
      const sections: CheckSection[] = [
        checkEnvironment(),
        await checkRenet(),
        await checkConfiguration(),
        ...(isCloud ? [await checkAuthentication()] : []),
        await checkSubscription(),
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
      if (exitCode !== 0) process.exit(exitCode);
    });
}
