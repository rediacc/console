import { execFile, spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { t } from '../../i18n/index.js';
import { writeProgress } from '../../services/core/progress-output.js';
import { getMsys2Environment, getRsyncPath, getSshPath } from '../msys2/paths.js';
import type { SyncProgress, SyncResult } from '../types/index.js';
import { commandExists, getPlatform } from '../utils/platform.js';
import { prepareRsyncPaths } from './pathConverter.js';
import {
  newRsyncBytesState,
  newRsyncCountState,
  updateRsyncBytes,
  updateRsyncCount,
} from './rsync-count.js';
import { createDeleteCounter } from './rsync-deleted.js';
import { createSkipLineScan, parseSkippedEntries } from './rsync-skipped.js';

/**
 * Gets the rsync command/path for the current platform
 *
 * On Windows, checks for:
 * 1. Bundled MSYS2 binaries (Electron app)
 * 2. System-wide MSYS2 installation
 *
 * @returns Path to rsync executable
 * @throws Error if rsync is not found
 */
export async function getRsyncCommand(): Promise<string> {
  if (getPlatform() === 'windows') {
    const rsyncPath = getRsyncPath();
    // If we got an actual path (not just 'rsync'), it exists
    if (rsyncPath !== 'rsync' && existsSync(rsyncPath)) {
      return rsyncPath;
    }
    // The leading "rsync not found" is matched by isRsyncNotFoundError to fall back to SFTP; keep it verbatim.
    throw new Error(`rsync not found. ${t('commands.doctor.rsyncInstallHintWin32')}`);
  }

  if (await commandExists('rsync')) {
    return 'rsync';
  }

  throw new Error('rsync not found. Please install rsync.');
}

let rsyncVersionTextPromise: Promise<string> | undefined;

/**
 * Text of `rsync --version` (banner included), run once per process and cached.
 * Rejects when rsync is missing; a failed lookup is not cached.
 */
export function getRsyncVersionText(): Promise<string> {
  rsyncVersionTextPromise ??= getRsyncCommand()
    .then(
      (cmd) =>
        new Promise<string>((resolve, reject) => {
          execFile(cmd, ['--version'], { encoding: 'utf8' }, (err, stdout) => {
            if (err) reject(err);
            else resolve(stdout);
          });
        })
    )
    .catch((error: unknown) => {
      rsyncVersionTextPromise = undefined;
      throw error;
    });
  return rsyncVersionTextPromise;
}

/** An rsync exit status as shown to the user: a Windows loader failure (0xC0000135) reads as hex beside the decimal. */
export function formatRsyncExitCode(code: number): string {
  return code > 255 ? `${code} (0x${code.toString(16).toUpperCase()})` : String(code);
}

/** Last lines of a stderr text, for an error line that names why a process failed. */
function stderrTail(text: string, maxLines = 5): string {
  return text.trim().split(/\r?\n/).slice(-maxLines).join('\n').trim();
}

/** The first run of an extracted MSYS2 binary on Windows can take seconds under load, so the probe gets headroom. */
const RSYNC_PROBE_TIMEOUT_MS = 15_000;
const RSYNC_BANNER = /^\s*rsync\s+version\s+\d/m;

/** rsync prints its banner before it exits; the MSYS2 build exits non-zero after it when its root lacks directories, yet carries a transfer. */
function printedBanner(stdout: unknown): boolean {
  return RSYNC_BANNER.test(String(stdout ?? ''));
}

function probeFailureStatus(failure: NodeJS.ErrnoException & { killed?: boolean }): string {
  if (failure.killed) return `timed out after ${RSYNC_PROBE_TIMEOUT_MS / 1000}s`;
  if (typeof failure.code === 'number') return `exit code ${formatRsyncExitCode(failure.code)}`;
  return String(failure.code ?? failure.message);
}

let rsyncProbePromise: Promise<string | undefined> | undefined;

/**
 * Why an installed rsync cannot start, or undefined when it runs (or is not installed at all, which getRsyncCommand reports on its own).
 * Runs `rsync --version` once per process: a binary that exists but fails there (MSYS2 exit 0xC0000135 after a partial pacman upgrade)
 * cannot carry a transfer, so the caller falls back to SFTP and names this reason.
 */
export function rsyncUnusableReason(): Promise<string | undefined> {
  rsyncProbePromise ??= (async () => {
    let cmd: string;
    try {
      cmd = await getRsyncCommand();
    } catch {
      return undefined;
    }
    return new Promise<string | undefined>((resolve) => {
      execFile(
        cmd,
        ['--version'],
        {
          encoding: 'utf8',
          timeout: RSYNC_PROBE_TIMEOUT_MS,
          env: { ...process.env, ...getMsys2Environment() },
        },
        (err, stdout, stderr) => {
          if (!err || (!(err as { killed?: boolean }).killed && printedBanner(stdout))) {
            resolve(undefined);
            return;
          }
          const status = probeFailureStatus(err as NodeJS.ErrnoException & { killed?: boolean });
          const tail = stderrTail(String(stderr ?? ''));
          resolve(tail ? `${cmd} --version: ${status}: ${tail}` : `${cmd} --version: ${status}`);
        }
      );
    });
  })();
  return rsyncProbePromise;
}

/** Test seam: forget the cached probe. */
export function resetRsyncProbe(): void {
  rsyncProbePromise = undefined;
}

/**
 * The `user@host` an rsync remote path (`user@host:path`) starts with. An IPv6 literal is
 * bracketed, since rsync would otherwise split the address at its first colon and read the rest
 * as the path (a machine whose address is its IPv6, eu-bench's hostinger since 2026-11-27).
 */
export function rsyncUserHost(user: string, host: string): string {
  const bare = host.startsWith('[') && host.endsWith(']') ? host.slice(1, -1) : host;
  return `${user}@${bare.includes(':') ? `[${bare}]` : bare}`;
}

/**
 * Gets the SSH command for rsync with options
 *
 * On Windows, uses bundled or system MSYS2 SSH for compatibility.
 *
 * @param sshOptions - SSH options string
 * @returns SSH command string for rsync -e option
 */
export async function getRsyncSSHCommand(sshOptions: string): Promise<string> {
  if (getPlatform() !== 'windows') {
    return `ssh ${sshOptions}`;
  }

  // On Windows, prefer bundled or MSYS2 SSH for compatibility
  const sshPath = getSshPath();
  if (sshPath !== 'ssh' && existsSync(sshPath)) {
    // Convert backslashes to forward slashes for MSYS2 compatibility
    const normalizedPath = sshPath.replaceAll('\\', '/');
    return `${normalizedPath} ${sshOptions}`;
  }

  if (await commandExists('ssh')) {
    return `ssh ${sshOptions}`;
  }

  throw new Error('SSH not found for rsync');
}

/**
 * Rsync change categories
 */
export interface RsyncChanges {
  newFiles: string[];
  modifiedFiles: string[];
  deletedFiles: string[];
  newDirs: string[];
  other: string[];
}

/**
 * Prefixes to skip in rsync output
 */
const RSYNC_SKIP_PREFIXES = ['sending ', 'receiving ', 'sent ', 'total size'] as const;

/**
 * Checks if a line should be skipped
 */
function shouldSkipLine(line: string): boolean {
  if (!line.trim()) return true;
  return RSYNC_SKIP_PREFIXES.some((prefix) => line.startsWith(prefix));
}

/**
 * Parses a single rsync itemize-changes line
 * Returns the category and filename, or null if not parseable
 */
function parseItemizeLine(line: string): { category: keyof RsyncChanges; filename: string } | null {
  // Handle deletion lines
  if (line.startsWith('deleting ')) {
    return { category: 'deletedFiles', filename: line.substring(9).trim() };
  }

  // Parse itemize-changes format: YXcstpoguax filename Format: 11 characters of flags, space, filename
  if (line.length <= 11 || line[11] !== ' ') {
    return { category: 'other', filename: line };
  }

  const flags = line.substring(0, 11);
  const filename = line.substring(12).trim();

  if (line.includes('*deleting')) {
    return { category: 'deletedFiles', filename };
  }

  if (flags.startsWith('cd')) {
    return { category: 'newDirs', filename };
  }

  const isFileTransfer = (flags.startsWith('>') || flags.startsWith('<')) && flags[1] === 'f';
  if (isFileTransfer) {
    const isNewFile = flags[2] === '+';
    return { category: isNewFile ? 'newFiles' : 'modifiedFiles', filename };
  }

  return { category: 'other', filename: line };
}

/**
 * Parses rsync dry-run output to extract changes
 *
 * @param dryRunOutput - Output from rsync --dry-run --itemize-changes
 * @returns Categorized changes
 */
function parseRsyncChanges(dryRunOutput: string): RsyncChanges {
  const changes: RsyncChanges = {
    newFiles: [],
    modifiedFiles: [],
    deletedFiles: [],
    newDirs: [],
    other: [],
  };

  for (const line of dryRunOutput.split('\n')) {
    if (shouldSkipLine(line)) continue;

    const parsed = parseItemizeLine(line);
    if (parsed) {
      changes[parsed.category].push(parsed.filename);
    }
  }

  return changes;
}

/** Add remote rsync path and permission args. */
function addRemoteRsyncArgs(
  args: string[],
  options: { isUpload?: boolean; remoteRsyncPath?: string },
  universalUser?: string
): void {
  if (universalUser) {
    // A repo key's renet sandbox-gateway admits a privileged receive only when every owner and group maps to the universal user and no device or special file is created (private/renet cmd/renet/sandbox_gateway_transfer.go). An upload is the remote receive, hence --chown (a download's receiver is local and needs none); --no-D rides both directions beside --no-links, so a privileged sync never carries devices or specials either way.
    args.push('--rsync-path', 'sudo rsync');
    if (options.isUpload) {
      args.push('--chown', `${universalUser}:${universalUser}`);
    }
    args.push('--numeric-ids', '--no-links', '--no-D');
  } else if (options.remoteRsyncPath) {
    args.push('--rsync-path', options.remoteRsyncPath);
  }
}

/** Add sync mode args (mirror, verify, excludes). */
function addSyncModeArgs(
  args: string[],
  options: { mirror?: boolean; verify?: boolean; exclude?: string[]; isUpload?: boolean }
): void {
  if (options.mirror) {
    args.push('--delete', '--exclude', '*.sock');
    if (options.isUpload) {
      // Protect (never delete) the rediacc-managed tree on the remote, including .rediacc/docker/data, the repo's Docker data-root.
      args.push('--filter=P /.rediacc/');
    }
  }
  if (options.verify) {
    // No --partial on purpose: real runs pass --inplace and rsync documents that --inplace implies --partial, so an interrupted verify run keeps its data.
    args.push('--checksum', '--ignore-times');
  } else {
    args.push('--partial');
  }
  if (options.exclude?.length) {
    for (const pattern of options.exclude) {
      args.push('--exclude', pattern);
    }
  }
}

/**
 * Builds rsync command arguments
 *
 * @param options - Sync options
 * @param sshCommand - SSH command for -e option
 * @param universalUser - Optional user for sudo rsync
 * @param dryRun - Whether this is a dry-run
 * @returns Array of rsync arguments
 */
export function buildRsyncArgs(
  options: {
    mirror?: boolean;
    verify?: boolean;
    exclude?: string[];
    remoteRsyncPath?: string;
    /** True when syncing local → remote (upload). Enables --chown on remote. */
    isUpload?: boolean;
    /** Auto-create the destination's parent directories (rsync 3.2.3+). */
    mkpath?: boolean;
  },
  sshCommand: string,
  universalUser?: string,
  dryRun = false
): string[] {
  const args: string[] = ['-av'];

  if (dryRun) {
    args.push('--dry-run', '--itemize-changes');
  } else {
    args.push('--verbose', '--inplace', '--no-whole-file', '--progress');
    // Itemized, so a deletion (`*deleting`) is told apart from a transferred file named `deleting ...` (4f037bc9.2).
    if (options.mirror) args.push('--itemize-changes');
  }

  if (options.mkpath) args.push('--mkpath');

  args.push('-e', sshCommand);

  addRemoteRsyncArgs(args, options, universalUser);
  addSyncModeArgs(args, options);

  return args;
}

/**
 * Rsync executor options
 */
export interface RsyncExecutorOptions {
  /** SSH options string */
  sshOptions: string;
  /** Source path, or multiple sources for multi-file upload. */
  source: string | string[];
  /** Destination path */
  destination: string;
  /** Whether to delete files not in source */
  mirror?: boolean;
  /** Whether to verify with checksums */
  verify?: boolean;
  /** Patterns to exclude from sync */
  exclude?: string[];
  /** Explicit rsync command to run on the remote host */
  remoteRsyncPath?: string;
  /** Universal user for sudo */
  universalUser?: string;
  /** True when syncing local → remote (upload). Enables --chown on remote. */
  isUpload?: boolean;
  /** Auto-create the destination's parent directories (rsync 3.2.3+). */
  mkpath?: boolean;
  /** Verbose logging - outputs full rsync command before execution */
  verbose?: boolean;
  /** Callback for progress updates */
  onProgress?: (progress: SyncProgress) => void;
  /** Callback for stdout data */
  onStdout?: (data: string) => void;
  /** Callback for stderr data */
  onStderr?: (data: string) => void;
}

/**
 * Executes rsync with the given options
 *
 * @param options - Rsync execution options
 * @returns Promise resolving to sync result
 */
export async function executeRsync(
  options: RsyncExecutorOptions
): Promise<SyncResult & { skipped: string[]; deleted: number }> {
  const startTime = Date.now();
  const errors: string[] = [];

  const rsyncCommand = await getRsyncCommand();
  const sshCommand = await getRsyncSSHCommand(options.sshOptions);

  // Prepare paths
  const [source, dest] = prepareRsyncPaths(options.source, options.destination);

  // Build arguments
  const args = buildRsyncArgs(
    {
      mirror: options.mirror,
      verify: options.verify,
      exclude: options.exclude,
      remoteRsyncPath: options.remoteRsyncPath,
      isUpload: options.isUpload,
      mkpath: options.mkpath,
    },
    sshCommand,
    options.universalUser,
    false
  );

  if (Array.isArray(source)) {
    args.push(...source, dest);
  } else {
    args.push(source, dest);
  }

  // Merge MSYS2 environment variables for Windows compatibility
  const env = { ...process.env, ...getMsys2Environment() };

  // Verbose logging: output full command before execution
  if (options.verbose) {
    writeProgress(`[rsync] Executing: ${rsyncCommand} ${args.join(' ')}\n`);
  }

  return new Promise((resolve) => {
    const rsync = spawn(rsyncCommand, args, {
      stdio: 'pipe',
      env,
    });

    let filesTransferred = 0;
    let bytesTransferred = 0;
    // The size on the last progress line: what a run that never finished a file (no 100% xfr# line) reports.
    let lastProgressBytes = 0;
    let stderrText = '';
    // rsync prints "skipping non-regular file" as an info message, which the sender writes to stdout, so the skip scan reads both streams. Only the skip lines of stdout are kept.
    const stdoutSkips = createSkipLineScan();
    // Remote (or, on a download, local) files a --mirror run removed: the itemized run prints each as "*deleting   <name>".
    const deletions = createDeleteCounter();
    const countState = newRsyncCountState();
    const bytesState = newRsyncBytesState();

    rsync.stdout.on('data', (data: Buffer) => {
      const output = data.toString();
      stdoutSkips.push(output);
      if (options.mirror) deletions.push(output);
      options.onStdout?.(output);

      // Parse progress from rsync output
      // Format: "   123,456,789 100%   12.34MB/s    0:00:00 (xfr#123, to-chk=456/789)"
      const progressMatch = /(\d[\d,]*)\s+(\d+)%\s+([\d.]+\w+\/s)\s+([\d:]+)/.exec(output);
      if (progressMatch) {
        const bytes = Number.parseInt(progressMatch[1].replaceAll(',', ''), 10);
        lastProgressBytes = bytes;
        options.onProgress?.({
          currentFile: '',
          bytesTransferred: bytes,
          totalBytes: 0,
          percentage: Number.parseInt(progressMatch[2], 10),
          speed: progressMatch[3],
          eta: progressMatch[4],
        });
      }
      bytesTransferred = updateRsyncBytes(bytesState, output) || lastProgressBytes;

      // Count transferred files: the running maximum xfr# over the whole run, so a chunk that carries several xfr# counters is never counted by its first one alone
      filesTransferred = updateRsyncCount(countState, output);
    });

    rsync.stderr.on('data', (data: Buffer) => {
      const error = data.toString();
      options.onStderr?.(error);
      errors.push(error);
      stderrText += error;
    });

    rsync.on('close', (code) => {
      const success = code === 0;

      // Always name the exit status: a binary that dies before printing (a missing DLL) leaves stderr empty, and the exit code is the only reason there is.
      if (!success) {
        const exitCodeMessages: Record<number, string> = {
          1: 'Syntax or usage error in rsync command',
          2: 'Protocol incompatibility between rsync versions',
          3: 'Errors selecting input/output files or directories',
          4: 'Requested action not supported (e.g., unsupported protocol)',
          5: 'Error starting client-server protocol',
          10: 'Error in socket I/O',
          11: 'Error in file I/O',
          12: 'Error in rsync protocol data stream',
          13: 'Errors with program diagnostics',
          14: 'Error in IPC code',
          20: 'Received SIGUSR1 or SIGINT',
          21: 'Some error returned by waitpid()',
          22: 'Error allocating core memory buffers',
          23: 'Partial transfer due to error (some files were not transferred)',
          24: 'Partial transfer due to vanished source files',
          25: 'The --max-delete limit stopped deletions',
          30: 'Timeout in data send/receive',
          35: 'Timeout waiting for daemon connection',
        };
        const label =
          code === null
            ? 'rsync ended without an exit code'
            : `rsync exit code ${formatRsyncExitCode(code)}`;
        const message = code === null ? undefined : exitCodeMessages[code];
        const tail = stderrTail(stderrText);
        errors.push(
          [message ? `${label}: ${message}` : label, tail && `stderr: ${tail}`]
            .filter(Boolean)
            .join('; ')
        );
      }

      resolve({
        success,
        filesTransferred,
        bytesTransferred,
        errors: success ? [] : errors,
        duration: Date.now() - startTime,
        skipped: parseSkippedEntries(`${stdoutSkips.text()}\n${stderrText}`),
        deleted: deletions.count(),
      });
    });

    rsync.on('error', (err) => {
      errors.push(err.message);
      resolve({
        success: false,
        filesTransferred: 0,
        bytesTransferred: 0,
        errors,
        duration: Date.now() - startTime,
        skipped: [],
        deleted: 0,
      });
    });
  });
}

/**
 * Gets a preview of changes (dry-run)
 *
 * @param options - Rsync execution options
 * @returns Promise resolving to categorized changes
 */
export async function getRsyncPreview(options: RsyncExecutorOptions): Promise<RsyncChanges> {
  const rsyncCommand = await getRsyncCommand();
  const sshCommand = await getRsyncSSHCommand(options.sshOptions);

  const [source, dest] = prepareRsyncPaths(options.source, options.destination);

  const args = buildRsyncArgs(
    {
      mirror: options.mirror,
      verify: options.verify,
      exclude: options.exclude,
      remoteRsyncPath: options.remoteRsyncPath,
      isUpload: options.isUpload,
      mkpath: options.mkpath,
    },
    sshCommand,
    options.universalUser,
    true // dry-run
  );

  if (Array.isArray(source)) {
    args.push(...source, dest);
  } else {
    args.push(source, dest);
  }

  // Merge MSYS2 environment variables for Windows compatibility
  const env = { ...process.env, ...getMsys2Environment() };

  // Verbose logging: output full command before execution
  if (options.verbose) {
    writeProgress(`[rsync] Preview: ${rsyncCommand} ${args.join(' ')}\n`);
  }

  return new Promise((resolve, reject) => {
    let output = '';
    let errorOutput = '';

    const rsync = spawn(rsyncCommand, args, {
      stdio: 'pipe',
      env,
    });

    rsync.stdout.on('data', (data: Buffer) => {
      output += data.toString();
    });

    rsync.stderr.on('data', (data: Buffer) => {
      errorOutput += data.toString();
    });

    rsync.on('close', (code) => {
      // Exit code 24 = partial transfer due to vanished source files, acceptable for preview
      if (code === 0 || code === 24) {
        resolve(parseRsyncChanges(output));
      } else {
        const tail = stderrTail(errorOutput);
        reject(
          new Error(
            `rsync dry-run failed (exit code ${code === null ? 'none' : formatRsyncExitCode(code)})${tail ? `: ${tail}` : ''}`
          )
        );
      }
    });

    rsync.on('error', (err) => {
      reject(err);
    });
  });
}
