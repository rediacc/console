/**
 * Client rsync for one repo image (`rdc backup download` / `rdc backup upload`,
 * agent/plans/PLAN-backup-local-image.md Design 3 and 6).
 *
 * The argv is fixed by the convergence argument: `--inplace --partial --no-whole-file
 * --ignore-times` makes every run a delta pass whose result is byte-identical to the source
 * whatever the destination held before (a prefix, an older copy, garbage). `--sparse` is added only
 * for a destination that does not exist yet, because `--sparse --inplace` over an existing file
 * leaves old bytes in zero runs on some rsync versions. Neither direction passes `-a`, `--times`
 * or `--chown`.
 */

import { spawn } from 'node:child_process';
import { t } from '../../i18n/index.js';
import { getMsys2Environment } from '../msys2/paths.js';
import { prepareRsyncPaths } from './pathConverter.js';
import { getRsyncCommand, getRsyncVersionText } from './rsync.js';

export interface ImageRsyncArgsOptions {
  direction: 'download' | 'upload';
  /** The destination file does not exist yet (download: the local image; upload: a fresh staging). */
  freshDest: boolean;
  /** The `-e` remote shell command. */
  sshCommand: string;
  /** `--bwlimit` in KiB/s; omitted or 0 is unlimited. */
  bwlimitKiBps?: number;
  /** `--rsync-path` for the machine side (`sudo -n <prefix...> <rsync>`). */
  remoteRsyncPath?: string;
}

/** Exit codes worth a retry: socket I/O, protocol stream, timeouts, and ssh's own 255. */
export const RETRYABLE_RSYNC_EXITS: ReadonlySet<number> = new Set([10, 12, 30, 35, 255]);

/** The first rsync that accepts `--sparse` together with `--inplace`. */
const MIN_RSYNC: readonly [number, number, number] = [3, 1, 3] as const;

export function buildImageRsyncArgs(opts: ImageRsyncArgsOptions): string[] {
  const args = [
    '--inplace',
    '--partial',
    '--no-whole-file',
    '--ignore-times',
    '--stats',
    '--progress',
    '--chmod=F600',
    '--timeout=120',
  ];
  if (opts.freshDest) args.push('--sparse');
  // The import helper sets the owner and mode of the finalized image.
  if (opts.direction === 'upload') args.push('--no-owner', '--no-group', '--no-perms');
  if (opts.bwlimitKiBps && opts.bwlimitKiBps > 0) {
    args.push(`--bwlimit=${Math.max(1, Math.floor(opts.bwlimitKiBps))}`);
  }
  if (opts.remoteRsyncPath) args.push(`--rsync-path=${opts.remoteRsyncPath}`);
  args.push('-e', opts.sshCommand);
  return args;
}

function installHint(platform: NodeJS.Platform): string {
  if (platform === 'darwin') return t('errors.backupImage.rsyncHintDarwin');
  if (platform === 'win32') return t('errors.backupImage.rsyncHintWindows');
  return t('errors.backupImage.rsyncHintLinux');
}

function parseVersion(text: string): [number, number, number] | null {
  const m = /\bversion\s+(\d+)\.(\d+)\.(\d+)/.exec(text);
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}

function versionAtLeast(v: readonly number[], min: readonly number[]): boolean {
  for (let i = 0; i < min.length; i++) {
    if (v[i] !== min[i]) return v[i] > min[i];
  }
  return true;
}

/**
 * Refuses a client rsync that cannot run the image argv: a missing binary, openrsync (its banner
 * names it), or anything older than 3.1.3. The refusal carries a per-platform install hint.
 */
export async function assertRsyncCapable(
  deps: { versionText?: () => Promise<string>; platform?: NodeJS.Platform } = {}
): Promise<void> {
  const platform = deps.platform ?? process.platform;
  const hint = installHint(platform);
  let text: string;
  try {
    text = await (deps.versionText ?? getRsyncVersionText)();
  } catch {
    throw new Error(t('errors.backupImage.rsyncMissing', { hint }));
  }
  if (/openrsync/i.test(text)) {
    throw new Error(t('errors.backupImage.rsyncOpenrsync', { hint }));
  }
  const version = parseVersion(text);
  if (!version) {
    throw new Error(t('errors.backupImage.rsyncVersionUnknown', { hint }));
  }
  if (!versionAtLeast(version, MIN_RSYNC)) {
    throw new Error(
      t('errors.backupImage.rsyncTooOld', {
        version: version.join('.'),
        min: MIN_RSYNC.join('.'),
        hint,
      })
    );
  }
}

function statNumber(text: string, label: string): number {
  const m = new RegExp(`${label}:\\s*([\\d,]+)`).exec(text);
  return m ? Number(m[1].replaceAll(',', '')) : 0;
}

/** Literal (sent) and matched (reused from the basis) bytes from `--stats` output. */
export function parseRsyncStats(text: string): { literalBytes: number; matchedBytes: number } {
  return {
    literalBytes: statNumber(text, 'Literal data'),
    matchedBytes: statNumber(text, 'Matched data'),
  };
}

export interface ImageRsyncProgress {
  bytes: number;
  percentage: number;
  speed: string;
  eta: string;
}

export interface RunImageRsyncOptions {
  args: string[];
  source: string;
  dest: string;
  onProgress?: (p: ImageRsyncProgress) => void;
  /** Aborting sends SIGINT to rsync; the outcome then carries rsync's own exit code. */
  signal?: AbortSignal;
}

export interface ImageRsyncOutcome {
  exitCode: number;
  literalBytes: number;
  matchedBytes: number;
  stderr: string;
}

const PROGRESS_RE = /(\d[\d,]*)\s+(\d+)%\s+([\d.]+\w+\/s)\s+([\d:]+)/g;
const TAIL_LIMIT = 64 * 1024;

/** Runs the client rsync once with the image argv plus source and destination. */
export async function runImageRsync(opts: RunImageRsyncOptions): Promise<ImageRsyncOutcome> {
  const command = await getRsyncCommand();
  const [source, dest] = prepareRsyncPaths(opts.source, opts.dest);
  const env = { ...process.env, ...getMsys2Environment() };
  return new Promise((resolve) => {
    const child = spawn(command, [...opts.args, source, dest], { stdio: 'pipe', env });
    // --progress repaints many times a second for hours, so only a tail is kept; --stats is at the end.
    let tail = '';
    let stderr = '';
    const onAbort = () => child.kill('SIGINT');
    opts.signal?.addEventListener('abort', onAbort, { once: true });
    child.stdout.on('data', (data: Buffer) => {
      const chunk = data.toString();
      tail = (tail + chunk).slice(-TAIL_LIMIT);
      if (!opts.onProgress) return;
      let last: RegExpExecArray | null = null;
      for (const m of chunk.matchAll(PROGRESS_RE)) last = m;
      if (last) {
        opts.onProgress({
          bytes: Number(last[1].replaceAll(',', '')),
          percentage: Number(last[2]),
          speed: last[3],
          eta: last[4],
        });
      }
    });
    child.stderr.on('data', (data: Buffer) => {
      stderr = (stderr + data.toString()).slice(-TAIL_LIMIT);
    });
    let done = false;
    const finish = (exitCode: number) => {
      if (done) return;
      done = true;
      opts.signal?.removeEventListener('abort', onAbort);
      resolve({ exitCode, ...parseRsyncStats(tail), stderr });
    };
    child.on('close', (code, signal) => finish(code ?? (signal === 'SIGINT' ? 20 : 1)));
    child.on('error', (err) => {
      stderr += err.message;
      finish(127);
    });
  });
}
