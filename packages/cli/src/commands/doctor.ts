import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { DEFAULTS } from '@rediacc/shared/config';
import { WK_DOCKER_INSTALL_DOCS, WK_GO_DL_BASE } from '@rediacc/shared/config/well-known.generated';
import chalk from 'chalk';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getRsyncPath } from '../remote/msys2/paths.js';
import { getSubscriptionServerUrl } from '../services/account/subscription-auth.js';
import { configService } from '../services/config/config-resources.js';
import {
  getEmbeddedMetadata,
  isSEA as isSEAEmbedded,
  verifyEmbeddedRenetIntegrity,
} from '../services/core/embedded-assets.js';
import { outputService, terminalWidth } from '../services/core/output.js';
import {
  describeTofuFailure,
  resolveTofu,
  type TofuResolution,
} from '../services/tofu/executor.js';
import { findOnPath, type PathLookupOptions } from '../services/tools/path-lookup.js';
import { resolveChannel } from '../services/update/updater.js';
import type { OutputFormat } from '../types/index.js';
import { getInstallMethod, isSEA } from '../utils/platform.js';
import { VERSION } from '../version.js';
import { checkSubscription } from './doctor-subscription.js';
import { toolSourceLabel } from './tools.js';

export type CheckStatus = 'ok' | 'warn' | 'fail';

export interface CheckResult {
  name: string;
  value: string;
  status: CheckStatus;
  hint?: string;
}

export interface CheckSection {
  title: string;
  checks: CheckResult[];
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
  return findOnPath('renet');
}

function checkToolVersion(
  cmd: string,
  args: string[],
  extractVersion: (output: string) => string,
  nameKey: string,
  hint: string
): CheckResult {
  const resolved = findOnPath(cmd);
  if (!resolved) {
    return { name: t(nameKey), value: t('commands.doctor.notInstalled'), status: 'warn', hint };
  }
  const result = runCommand(resolved, args);
  const version = result.ok ? extractVersion(result.output) : 'unknown';
  return { name: t(nameKey), value: version, status: 'ok' };
}

function checkEnvironment(): CheckSection {
  const isDev = getInstallMethod() === 'dev';
  const checks: CheckResult[] = [
    { name: t('commands.doctor.checks.nodeVersion'), value: process.version, status: 'ok' },
    { name: t('commands.doctor.checks.cliVersion'), value: VERSION, status: 'ok' },
    {
      name: 'Install method',
      value: (() => {
        const m = getInstallMethod();
        if (m === 'sea') return 'SEA binary';
        if (m === 'npm') return 'npm (global)';
        return 'dev mode';
      })(),
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
  ];

  // Go and Docker are only relevant for development (building renet from source)
  if (isDev) {
    checks.push(
      checkToolVersion(
        'go',
        ['version'],
        (o) => o.replace(/^go version\s+/, '').split(/\s/)[0],
        'commands.doctor.checks.goInstalled',
        `Install Go from ${WK_GO_DL_BASE}/`
      ),
      checkToolVersion(
        'docker',
        ['--version'],
        (o) => `Docker ${o.replace(/^Docker version\s+/, '').split(/,/)[0]}`,
        'commands.doctor.checks.dockerAvailable',
        `Install Docker from ${WK_DOCKER_INSTALL_DOCS}/`
      )
    );
  }

  return { title: t('commands.doctor.sections.environment'), checks };
}

export interface ToolsCheckDeps {
  resolveTofu?: () => Promise<TofuResolution>;
  /** PATH lookup options for rsync (env, platform); the real environment by default. */
  pathLookup?: PathLookupOptions;
  /** Output of `rsync --version`, or null when it does not run. */
  rsyncVersion?: (path: string) => string | null;
}

/** A local rsync: the MSYS2 one rdc's sync uses on Windows, else the first on PATH. */
function findRsync(lookup?: PathLookupOptions): string | null {
  if (!lookup && process.platform === 'win32') {
    const msys = getRsyncPath();
    if (msys !== 'rsync' && existsSync(msys)) return msys;
  }
  return findOnPath('rsync', lookup);
}

function defaultRsyncVersion(path: string): string | null {
  const result = runCommand(path, ['--version']);
  return result.ok ? result.output : null;
}

async function checkTofu(resolve: () => Promise<TofuResolution>): Promise<CheckResult> {
  const name = t('commands.doctor.checks.tofu');
  const hint = t('commands.doctor.tofuInstallHint');
  const result = await resolve();
  if (result.ok) {
    const { engine } = result;
    const label = engine.engine === 'tofu' ? engine.version : `terraform ${engine.version}`;
    return { name, value: `${label} (${toolSourceLabel(engine.source)})`, status: 'ok' };
  }
  if (result.reason === 'missing') {
    return { name, value: t('commands.doctor.notInstalled'), status: 'warn', hint };
  }
  return { name, value: describeTofuFailure(result), status: 'warn', hint };
}

/** Local tools rdc runs itself: the provisioning engine and rsync. */
export async function checkTools(deps: ToolsCheckDeps = {}): Promise<CheckSection> {
  const checks: CheckResult[] = [await checkTofu(deps.resolveTofu ?? (() => resolveTofu()))];

  const rsyncName = t('commands.doctor.checks.rsync');
  const rsyncPath = findRsync(deps.pathLookup);
  if (rsyncPath) {
    const out = (deps.rsyncVersion ?? defaultRsyncVersion)(rsyncPath);
    const version = out ? (/version\s+(\S+)/.exec(out)?.[1] ?? 'unknown') : 'unknown';
    checks.push({ name: rsyncName, value: version, status: 'ok' });
  } else {
    checks.push({
      name: rsyncName,
      value: t('commands.doctor.notInstalled'),
      status: 'warn',
      hint: t('commands.doctor.rsyncInstallHint'),
    });
  }
  return { title: t('commands.doctor.sections.tools'), checks };
}

function checkRenetBinary(checks: CheckResult[], renetPath: string | null): void {
  if (!renetPath) {
    checks.push({
      name: t('commands.doctor.checks.renetBinary'),
      value: t('commands.doctor.notInstalled'),
      status: isSEA() ? 'warn' : 'fail',
      hint: isSEA()
        ? 'Renet is optional on workstations (only needed for local VM ops). It is auto-provisioned to remote machines.'
        : 'Build renet with: cd private/renet && ./build.sh dev',
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
    hasEmbedAssets ? undefined : 'Build renet embed assets with: cd private/renet && ./build.sh dev'
  );
}

function checkRenetEmbeddedAssets(checks: CheckResult[]): void {
  if (isSEA() && isSEAEmbedded()) {
    try {
      const archs = Object.keys(getEmbeddedMetadata().binaries).join(', ');
      // Read the host's embedded renet binary back out and verify its sha256 against the build-time metadata: proves the SEA asset lookup returns the exact injected bytes, not just that the metadata asset parses.
      const integrity = verifyEmbeddedRenetIntegrity();
      if (integrity.ok) {
        pushEmbedAssetChecks(checks, `yes (${archs})`, 'ok');
      } else {
        pushEmbedAssetChecks(checks, `corrupt: ${integrity.detail}`, 'fail');
      }
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
      hint: machineCount === 0 ? 'Add machines with: rdc machine add <name>' : undefined,
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

function checkSshKey(checks: CheckResult[], hasInlineKey: boolean): void {
  // Keys live inline in the config (credentials.ssh.privateKey), written by `config init --ssh-key` / `config ssh set`. There is no path to stat.
  if (hasInlineKey) {
    checks.push({ name: t('commands.doctor.checks.sshKey'), value: '(inline)', status: 'ok' });
    return;
  }
  checks.push({
    name: t('commands.doctor.checks.sshKey'),
    value: t('commands.doctor.notConfigured'),
    status: 'warn',
    hint: 'Set SSH key during config init: rdc config init <name> --ssh-key <path>',
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
  await checkMachineCount(checks);
  checkSshKey(checks, Boolean(context?.credentials?.ssh?.privateKey));
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

const STATUS_ICONS: Record<CheckStatus, string> = {
  ok: chalk.green('OK'),
  warn: chalk.yellow('WARN'),
  fail: chalk.red('FAIL'),
};

/** Visible width of the widest status label ('WARN'/'FAIL'), chalk excluded. */
const STATUS_LABEL_WIDTH = 4;
/** Never squeeze the value column below this, however narrow the terminal is. */
const MIN_VALUE_WIDTH = 12;

function formatSection(section: CheckSection): string {
  const width = terminalWidth();
  const nameWidth = Math.max(16, ...section.checks.map((c) => c.name.length + 2));
  // The value column takes whatever is left after the 4-space indent, the name column and the status label. Sizing it from the VALUE instead is what put a 232-column line on screen: `curl --version` answers with a full banner ("curl 8.5.0 (x86_64-pc-linux-gnu) libcurl/8.5.0 OpenSSL/3.0.13 ..."), and padEnd(value.length + 2) simply grew the row to fit it.
  const valueWidth = Math.max(MIN_VALUE_WIDTH, width - 4 - nameWidth - STATUS_LABEL_WIDTH);
  const lines = [`  ${chalk.bold(section.title)}`];
  for (const check of section.checks) {
    const value =
      check.value.length > valueWidth ? `${check.value.slice(0, valueWidth - 1)}…` : check.value;
    lines.push(
      `    ${check.name.padEnd(nameWidth)}${value.padEnd(valueWidth)}${STATUS_ICONS[check.status]}`
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
  const { errors } = countByStatus(sections);
  if (errors > 0) return 2;
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
      const sections: CheckSection[] = [
        checkEnvironment(),
        await checkTools(),
        await checkRenet(),
        await checkConfiguration(),
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
