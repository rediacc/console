import chalk from 'chalk';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { type LocalExecuteResult, localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';

interface DiffEntry {
  status: 'A' | 'M' | 'D' | 'R';
  path: string;
  old_path?: string;
  type: string;
  old_size?: number;
  size: number;
  bytes_changed?: number;
  blocks_changed?: number;
  inode?: number;
  content_changed: boolean;
  mode_changed?: boolean;
  uid_changed?: boolean;
  gid_changed?: boolean;
  old_mode?: string;
  new_mode?: string;
}

interface DiffResult {
  base: string;
  target: string;
  entries: DiffEntry[];
  added: number;
  modified: number;
  deleted: number;
  renamed: number;
  strategy: string;
  fast: boolean;
  degraded: boolean;
  block_size: number;
  total_bytes_changed: number;
}

interface ContentDiffResult {
  base: string;
  target: string;
  path: string;
  binary: boolean;
  truncated: boolean;
  old_size: number;
  new_size: number;
  unified?: string;
  identical: boolean;
}

interface DiffOptions {
  name: string;
  base?: string;
  machine: string;
  nameOnly?: boolean;
  stat?: boolean;
  content?: string | boolean;
  json?: boolean;
  fast?: boolean;
  debug?: boolean;
  skipRouterRestart?: boolean;
}

function tryParse<T>(s: string): T | undefined {
  try {
    return JSON.parse(s) as T;
  } catch {
    return undefined;
  }
}

/** Accumulate a renet command's indented JSON from captured stdout, skipping
 * interleaved bridge log lines (mirrors repo-backup-list's extractor). */
function extractJson<T>(stdout: string): T | undefined {
  let buf = '';
  for (const rawLine of stdout.trim().split('\n')) {
    const line = rawLine.replace(/^\[[^\]]+\]\s?/, '');
    if (buf) {
      buf += `\n${line}`;
    } else {
      const brace = line.indexOf('{');
      if (brace < 0) continue;
      buf = line.slice(brace);
    }
    const parsed = tryParse<T>(buf);
    if (parsed !== undefined) return parsed;
  }
  return undefined;
}

function statusColor(status: DiffEntry['status'], text: string): string {
  switch (status) {
    case 'A':
      return chalk.green(text);
    case 'M':
      return chalk.yellow(text);
    case 'D':
      return chalk.red(text);
    case 'R':
      return chalk.cyan(text);
    default:
      return text;
  }
}

function humanBytes(n: number): string {
  const sign = n < 0 ? '-' : '+';
  let v = Math.abs(n);
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${sign}${i === 0 ? v : v.toFixed(1)} ${units[i]}`;
}

function summaryLine(d: DiffResult): string {
  const total = d.added + d.modified + d.deleted + d.renamed;
  const noun = total === 1 ? 'file' : 'files';
  const base = `${total} ${noun} changed: ${d.added} added, ${d.modified} modified, ${d.deleted} deleted, ${d.renamed} renamed`;
  return d.degraded ? `${base} (degraded: full-hash fallback)` : base;
}

function renderNameStatus(d: DiffResult): void {
  for (const e of d.entries) {
    if (e.status === 'R') {
      process.stdout.write(`${statusColor('R', 'R ')} ${e.old_path} -> ${e.path}\n`);
    } else {
      process.stdout.write(`${statusColor(e.status, `${e.status} `)} ${e.path}\n`);
    }
  }
  // Summary on stderr so stdout stays a clean A/M/D/R stream.
  outputService.info(d.entries.length === 0 ? 'No differences.' : summaryLine(d));
}

function renderNameOnly(d: DiffResult): void {
  for (const e of d.entries) {
    process.stdout.write(`${e.path}\n`);
  }
}

function statDetail(e: DiffEntry): string {
  switch (e.status) {
    case 'A':
      return `${chalk.green('new')}  ${humanBytes(e.size)}`;
    case 'D':
      return `${chalk.red('gone')} ${humanBytes(-(e.old_size ?? 0))}`;
    case 'R':
      return `${chalk.cyan('renamed')} from ${e.old_path}`;
    default: {
      const blocks = e.blocks_changed ?? 0;
      return `${blocks} block${blocks === 1 ? '' : 's'}  ${humanBytes(e.size - (e.old_size ?? 0))}`;
    }
  }
}

function renderStat(d: DiffResult): void {
  const width = d.entries.reduce((m, e) => Math.max(m, e.path.length), 0);
  for (const e of d.entries) {
    process.stdout.write(
      `${statusColor(e.status, e.status)}  ${e.path.padEnd(width)}  ${statDetail(e)}\n`
    );
  }
  const blocks = Math.ceil(d.total_bytes_changed / (d.block_size || 4096));
  process.stdout.write(
    `\n${summaryLine(d)}; ${humanBytes(d.total_bytes_changed).replace('+', '')} across ${blocks} blocks\n`
  );
}

function colorizeDiffLine(line: string): string {
  if (line.startsWith('+++') || line.startsWith('---')) return chalk.bold(line);
  if (line.startsWith('@@')) return chalk.cyan(line);
  if (line.startsWith('+')) return chalk.green(line);
  if (line.startsWith('-')) return chalk.red(line);
  return line;
}

function renderContent(c: ContentDiffResult): void {
  if (c.binary) {
    const p = c.path.replace(/^\//, '');
    process.stdout.write(`Binary files a/${p} and b/${p} differ\n`);
    return;
  }
  if (c.identical) {
    outputService.info(`${c.path}: identical`);
    return;
  }
  for (const line of (c.unified ?? '').split('\n')) {
    process.stdout.write(`${colorizeDiffLine(line)}\n`);
  }
  if (c.truncated) {
    outputService.warn(t('commands.repo.diff.truncated'));
  }
}

/** Resolve the (base, target) GUID pair. --name is the target (new side);
 * --base is the old side, defaulting to the parent of --name. */
async function resolveBaseTarget(
  name: string,
  baseOpt: string | undefined
): Promise<{ baseGuid: string; targetGuid: string }> {
  const targetCfg = await configService.getRepository(name);
  if (!targetCfg) throw new ValidationError(t('commands.repo.diff.notFound', { name }));

  if (baseOpt) {
    const baseCfg = await configService.getRepository(baseOpt);
    if (!baseCfg) throw new ValidationError(t('commands.repo.diff.notFound', { name: baseOpt }));
    return { baseGuid: baseCfg.repositoryGuid, targetGuid: targetCfg.repositoryGuid };
  }

  if (!targetCfg.parentGuid) {
    throw new ValidationError(t('commands.repo.diff.notAFork', { name }));
  }
  const guidMap = await configService.getRepositoryGuidMap();
  if (!guidMap[targetCfg.parentGuid]) {
    throw new ValidationError(t('commands.repo.diff.parentMissing', { name }));
  }
  return { baseGuid: targetCfg.parentGuid, targetGuid: targetCfg.repositoryGuid };
}

type DiffMode =
  | { kind: 'content'; path: string }
  | { kind: 'render'; render: (d: DiffResult) => void };

function pickRenderer(options: DiffOptions): (d: DiffResult) => void {
  if (options.json) return (d) => outputService.print(d, 'json');
  if (options.nameOnly) return renderNameOnly;
  if (options.stat) return renderStat;
  return renderNameStatus;
}

/** Pick the single output mode, enforcing mutual exclusivity. */
function selectMode(options: DiffOptions): DiffMode {
  const contentMode = options.content !== undefined;
  const formats = [options.nameOnly, options.stat, contentMode, options.json].filter(
    Boolean
  ).length;
  if (formats > 1) {
    throw new ValidationError(t('commands.repo.diff.conflictingFormat'));
  }
  if (contentMode) {
    if (typeof options.content !== 'string') {
      throw new ValidationError(t('commands.repo.diff.contentNeedsPath'));
    }
    return { kind: 'content', path: options.content };
  }
  return { kind: 'render', render: pickRenderer(options) };
}

async function runDiff(options: DiffOptions): Promise<void> {
  const mode = selectMode(options);
  const { baseGuid, targetGuid } = await resolveBaseTarget(options.name, options.base);
  if (baseGuid === targetGuid) {
    throw new ValidationError(t('commands.repo.diff.sameRepo'));
  }
  await configService.ensureRepositoryNetworkId(options.name);

  const params: Record<string, unknown> = { base: baseGuid, target: targetGuid };
  if (options.fast) params.fast = true;
  if (mode.kind === 'content') params.content = mode.path;

  outputService.info(
    t('commands.repo.diff.starting', {
      base: baseGuid,
      target: targetGuid,
      machine: options.machine,
    })
  );

  const result: LocalExecuteResult = await localExecutorService.execute({
    functionName: 'repository_diff',
    machineName: options.machine,
    params: { repository: options.name, ...params },
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
    captureOutput: true,
  });

  if (!result.success) {
    renderLocalExecutionFailure(result, result.error ?? t('commands.repo.diff.failed'));
    process.exitCode = 1;
    return;
  }
  renderResult(mode, result.stdout ?? '', options.json ?? false);
}

/** Parse the renet JSON payload and render it per the selected mode. */
function renderResult(mode: DiffMode, stdout: string, asJson: boolean): void {
  if (mode.kind === 'content') {
    const c = extractJson<ContentDiffResult>(stdout);
    if (!c) throw new Error(t('commands.repo.diff.failed'));
    if (asJson) outputService.print(c, 'json');
    else renderContent(c);
    return;
  }
  const d = extractJson<DiffResult>(stdout);
  if (!d) throw new Error(t('commands.repo.diff.failed'));
  mode.render(d);
}

/**
 * repo diff — git-style file-level diff between two copy-on-write forks.
 * Stdout carries the diff data; progress/diagnostics go to stderr so
 * `rdc repo diff … --json | jq` and `… --name-only | xargs` stay clean.
 */
export function registerRepoDiffCommand(repo: Command): void {
  repo
    .command('diff')
    .summary(t('commands.repo.diff.descriptionShort'))
    .description(t('commands.repo.diff.description'))
    .requiredOption('--name <name>', t('commands.repo.diff.nameOption'))
    .option('--base <name>', t('commands.repo.diff.baseOption'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--name-only', t('commands.repo.diff.nameOnlyOption'))
    .option('--stat', t('commands.repo.diff.statOption'))
    .option('--content [path]', t('commands.repo.diff.contentOption'))
    .option('--json', t('commands.repo.diff.jsonOption'))
    .option('--fast', t('commands.repo.diff.fastOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options: DiffOptions) => {
      try {
        await runDiff(options);
      } catch (error) {
        handleError(error);
      }
    });
}
