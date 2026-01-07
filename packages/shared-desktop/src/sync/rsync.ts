import { spawn } from 'child_process';
import { existsSync } from 'fs';
import { join } from 'path';
import { prepareRsyncPaths } from './pathConverter.js';
import {
  getRsyncPath,
  getSshPath,
  getMsys2Environment,
  findSystemMsys2Path,
} from '../msys2/paths.js';
import { getPlatform, commandExists } from '../utils/platform.js';
import type { SyncProgress, SyncResult } from '../types/index.js';

/**
 * MSYS2 subdirectories to check for binaries (kept for backward compatibility)
 */
const MSYS2_BIN_DIRS = ['usr\\bin', 'mingw64\\bin', 'mingw32\\bin'] as const;

/**
 * Finds an executable in MSYS2 installation
 *
 * @deprecated Use getRsyncPath() or getSshPath() from msys2 module instead
 * @param exeName - Executable name (without .exe)
 * @returns Full path to executable or null if not found
 */
export function findMSYS2Executable(exeName: string): string | null {
  if (getPlatform() !== 'windows') {
    return null;
  }

  const systemMsys2 = findSystemMsys2Path();
  if (!systemMsys2) {
    return null;
  }

  for (const subdir of MSYS2_BIN_DIRS) {
    const exePath = join(systemMsys2, subdir, `${exeName}.exe`);
    if (existsSync(exePath)) {
      return exePath;
    }
  }

  return null;
}

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
    throw new Error(
      'rsync not found. Please install MSYS2 with rsync package or use the desktop app.'
    );
  }

  if (await commandExists('rsync')) {
    return 'rsync';
  }

  throw new Error('rsync not found. Please install rsync.');
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
    const normalizedPath = sshPath.replace(/\\/g, '/');
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
 * Parses rsync dry-run output to extract changes
 *
 * @param dryRunOutput - Output from rsync --dry-run --itemize-changes
 * @returns Categorized changes
 */
export function parseRsyncChanges(dryRunOutput: string): RsyncChanges {
  const changes: RsyncChanges = {
    newFiles: [],
    modifiedFiles: [],
    deletedFiles: [],
    newDirs: [],
    other: [],
  };

  const skipPrefixes = ['sending ', 'receiving ', 'sent ', 'total size'];

  for (const line of dryRunOutput.split('\n')) {
    if (!line.trim()) continue;
    if (skipPrefixes.some((prefix) => line.startsWith(prefix))) continue;

    // Handle deletion lines
    if (line.startsWith('deleting ')) {
      changes.deletedFiles.push(line.substring(9).trim());
      continue;
    }

    // Parse itemize-changes format: YXcstpoguax filename
    // Format: 11 characters of flags, space, filename
    if (line.length > 11 && line[11] === ' ') {
      const flags = line.substring(0, 11);
      const filename = line.substring(12).trim();

      if (line.includes('*deleting')) {
        changes.deletedFiles.push(filename);
      } else if (flags.startsWith('cd')) {
        // New directory
        changes.newDirs.push(filename);
      } else if ((flags.startsWith('>') || flags.startsWith('<')) && flags[1] === 'f') {
        // File transfer: > = sending, < = receiving
        // flags[2]: + = new file, . = existing file
        if (flags[2] === '+') {
          changes.newFiles.push(filename);
        } else {
          changes.modifiedFiles.push(filename);
        }
      } else {
        changes.other.push(line);
      }
    } else {
      changes.other.push(line);
    }
  }

  return changes;
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
  }

  args.push('-e', sshCommand);

  // Add sudo rsync path for remote operations if universal user is specified
  if (universalUser) {
    args.push('--rsync-path', `sudo -u ${universalUser} rsync`);
  }

  // Mirror mode: delete files not in source
  if (options.mirror) {
    args.push('--delete', '--exclude', '*.sock');
  }

  // Verify mode: use checksums
  if (options.verify) {
    args.push('--checksum', '--ignore-times');
  } else {
    args.push('--partial', '--append-verify');
  }

  // Exclude patterns
  if (options.exclude?.length) {
    for (const pattern of options.exclude) {
      args.push('--exclude', pattern);
    }
  }

  return args;
}

/**
 * Rsync executor options
 */
export interface RsyncExecutorOptions {
  /** SSH options string */
  sshOptions: string;
  /** Source path */
  source: string;
  /** Destination path */
  destination: string;
  /** Whether to delete files not in source */
  mirror?: boolean;
  /** Whether to verify with checksums */
  verify?: boolean;
  /** Patterns to exclude from sync */
  exclude?: string[];
  /** Universal user for sudo */
  universalUser?: string;
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
export async function executeRsync(options: RsyncExecutorOptions): Promise<SyncResult> {
  const startTime = Date.now();
  const errors: string[] = [];

  const rsyncCommand = await getRsyncCommand();
  const sshCommand = await getRsyncSSHCommand(options.sshOptions);

  // Prepare paths
  const [source, dest] = prepareRsyncPaths(options.source, options.destination);

  // Build arguments
  const args = buildRsyncArgs(
    { mirror: options.mirror, verify: options.verify, exclude: options.exclude },
    sshCommand,
    options.universalUser,
    false
  );

  args.push(source, dest);

  // Merge MSYS2 environment variables for Windows compatibility
  const env = { ...process.env, ...getMsys2Environment() };

  // Verbose logging: output full command before execution
  if (options.verbose) {
    // eslint-disable-next-line no-console
    console.log(`[rsync] Executing: ${rsyncCommand} ${args.join(' ')}`);
  }

  return new Promise((resolve) => {
    const rsync = spawn(rsyncCommand, args, {
      stdio: 'pipe',
      env,
    });

    let filesTransferred = 0;
    let bytesTransferred = 0;

    rsync.stdout.on('data', (data: Buffer) => {
      const output = data.toString();
      options.onStdout?.(output);

      // Parse progress from rsync output
      // Format: "   123,456,789 100%   12.34MB/s    0:00:00 (xfr#123, to-chk=456/789)"
      const progressMatch = output.match(/(\d[\d,]*)\s+(\d+)%\s+([\d.]+\w+\/s)\s+([\d:]+)/);
      if (progressMatch && options.onProgress) {
        const bytes = parseInt(progressMatch[1].replace(/,/g, ''), 10);
        options.onProgress({
          currentFile: '',
          bytesTransferred: bytes,
          totalBytes: 0,
          percentage: parseInt(progressMatch[2], 10),
          speed: progressMatch[3],
          eta: progressMatch[4],
        });
        bytesTransferred = bytes;
      }

      // Count transferred files
      if (output.includes('xfr#')) {
        const xfrMatch = output.match(/xfr#(\d+)/);
        if (xfrMatch) {
          filesTransferred = parseInt(xfrMatch[1], 10);
        }
      }
    });

    rsync.stderr.on('data', (data: Buffer) => {
      const error = data.toString();
      options.onStderr?.(error);
      errors.push(error);
    });

    rsync.on('close', (code) => {
      // Exit code 23 = partial transfer due to error
      // Treat as success if caused by permission issues on lost+found or similar system dirs
      const isPartialTransferOK =
        code === 23 &&
        errors.some((e) => {
          const lower = e.toLowerCase();
          return lower.includes('permission denied') || lower.includes('lost+found');
        });
      const success = code === 0 || isPartialTransferOK;

      // Add descriptive messages for common rsync exit codes
      if (!success && code !== null) {
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
        const message = exitCodeMessages[code];
        if (message) {
          errors.push(`rsync exit code ${code}: ${message}`);
        }
      }

      resolve({
        success,
        filesTransferred,
        bytesTransferred,
        errors: success ? [] : errors,
        duration: Date.now() - startTime,
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
    { mirror: options.mirror, verify: options.verify, exclude: options.exclude },
    sshCommand,
    options.universalUser,
    true // dry-run
  );

  args.push(source, dest);

  // Merge MSYS2 environment variables for Windows compatibility
  const env = { ...process.env, ...getMsys2Environment() };

  // Verbose logging: output full command before execution
  if (options.verbose) {
    // eslint-disable-next-line no-console
    console.log(`[rsync] Preview: ${rsyncCommand} ${args.join(' ')}`);
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
      if (code !== 0) {
        reject(new Error(`rsync dry-run failed: ${errorOutput}`));
      } else {
        resolve(parseRsyncChanges(output));
      }
    });

    rsync.on('error', (err) => {
      reject(err);
    });
  });
}
