/**
 * SFTP-based file transfer fallback for systems without rsync.
 * Slower than rsync (no delta sync) but works anywhere SSH works.
 */

import * as fsPromises from 'node:fs/promises';
import * as path from 'node:path';
import { SFTPClient, type SFTPClientConfig } from '../sftp/client.js';

export interface SftpTransferResult {
  success: boolean;
  filesTransferred: number;
  bytesTransferred: number;
  errors: string[];
  duration: number;
}

export interface SftpTransferOptions {
  /** Patterns to exclude (simple glob: *.log, node_modules, etc.) */
  exclude?: string[];
  /** Progress callback for each file */
  onProgress?: (file: string, bytesTransferred: number, totalBytes: number) => void;
  /** Dry run — count files without transferring */
  dryRun?: boolean;
  /** Remote user for sudo chown after upload */
  universalUser?: string;
}

/**
 * Check if a filename matches any exclude pattern (simple glob).
 */
function isExcluded(filePath: string, patterns: string[]): boolean {
  const normalized = filePath.replaceAll('\\', '/');
  for (const pattern of patterns) {
    if (pattern.startsWith('*.')) {
      // Extension match
      if (normalized.endsWith(pattern.slice(1))) return true;
    } else if (
      normalized.includes(`/${pattern}/`) ||
      normalized.endsWith(`/${pattern}`) ||
      normalized === pattern
    ) {
      // Directory or file name match
      return true;
    }
  }
  return false;
}

/**
 * Recursively collect all files in a local directory.
 */
async function walkLocalDir(
  dirPath: string,
  basePath: string,
  exclude: string[]
): Promise<{ relativePath: string; absolutePath: string; size: number }[]> {
  const files: { relativePath: string; absolutePath: string; size: number }[] = [];
  const entries = await fsPromises.readdir(dirPath, { withFileTypes: true });

  for (const entry of entries) {
    const absolutePath = path.join(dirPath, entry.name);
    const relativePath = path.relative(basePath, absolutePath).replaceAll('\\', '/');

    if (isExcluded(relativePath, exclude)) continue;

    if (entry.isDirectory()) {
      const subFiles = await walkLocalDir(absolutePath, basePath, exclude);
      files.push(...subFiles);
    } else if (entry.isFile()) {
      const stat = await fsPromises.stat(absolutePath);
      files.push({ relativePath, absolutePath, size: stat.size });
    }
  }

  return files;
}

/**
 * Collect unique subdirectory paths from a list of files.
 */
function collectSubdirs(files: { relativePath: string }[]): string[] {
  const subdirs = new Set<string>();
  for (const file of files) {
    const dir = path.dirname(file.relativePath).replaceAll('\\', '/');
    if (dir && dir !== '.') subdirs.add(dir);
  }
  return [...subdirs].sort();
}

/**
 * Upload a local directory to a remote path via SFTP.
 * No delta sync — transfers all files.
 */
export async function sftpUploadDirectory(
  localPath: string,
  remotePath: string,
  config: SFTPClientConfig,
  options?: SftpTransferOptions
): Promise<SftpTransferResult> {
  const startTime = Date.now();
  const exclude = options?.exclude ?? [];
  const errors: string[] = [];

  // Normalize local path (remove trailing slash for path.relative)
  const normalizedLocal = localPath.replace(/[/\\]+$/, '');

  // Collect local files
  const files = await walkLocalDir(normalizedLocal, normalizedLocal, exclude);

  if (options?.dryRun) {
    return {
      success: true,
      filesTransferred: files.length,
      bytesTransferred: files.reduce((sum, f) => sum + f.size, 0),
      errors: [],
      duration: Date.now() - startTime,
    };
  }

  const sftp = new SFTPClient(config);
  let filesTransferred = 0;
  let bytesTransferred = 0;

  try {
    await sftp.connect();

    const normalizedRemote = remotePath.replace(/\/+$/, '');

    // Use SSH exec channel for file operations (not SFTP subsystem) because
    // sandbox-gateway may restrict SFTP paths differently from exec paths.
    // Write files by piping data through: base64 | base64 -d > file
    const subdirs = collectSubdirs(files);

    // Create target + all subdirectories via exec
    const allDirs = [normalizedRemote, ...subdirs.map((d) => `${normalizedRemote}/${d}`)];
    await sftp.exec(`mkdir -p ${allDirs.map((d) => `"${d}"`).join(' ')}`);

    // Upload files via exec channel using base64 encoding to handle binary safely.
    // execStreaming pipes base64 data through stdin → base64 -d > file on remote.
    const totalBytes = files.reduce((s, f) => s + f.size, 0);
    for (const file of files) {
      const remoteFilePath = `${normalizedRemote}/${file.relativePath}`;
      try {
        const data = await fsPromises.readFile(file.absolutePath);
        const b64 = data.toString('base64');
        const exitCode = await sftp.execStreaming(`base64 -d > "${remoteFilePath}"`, {
          stdin: b64,
        });
        if (exitCode !== 0) {
          errors.push(`${file.relativePath}: remote write failed (exit code ${exitCode})`);
          continue;
        }
        filesTransferred++;
        bytesTransferred += data.length;
        options?.onProgress?.(file.relativePath, bytesTransferred, totalBytes);
      } catch (err) {
        errors.push(`${file.relativePath}: ${err instanceof Error ? err.message : String(err)}`);
      }
    }
  } finally {
    sftp.close();
  }

  return {
    success: errors.length === 0,
    filesTransferred,
    bytesTransferred,
    errors,
    duration: Date.now() - startTime,
  };
}

/**
 * Download a remote directory to a local path via SFTP.
 * No delta sync — transfers all files.
 */
export async function sftpDownloadDirectory(
  remotePath: string,
  localPath: string,
  config: SFTPClientConfig,
  options?: SftpTransferOptions
): Promise<SftpTransferResult> {
  const startTime = Date.now();
  const errors: string[] = [];

  const sftp = new SFTPClient(config);
  let filesTransferred = 0;
  let bytesTransferred = 0;

  try {
    await sftp.connect();

    const normalizedRemote = remotePath.replace(/\/+$/, '');
    const normalizedLocal = localPath.replace(/[/\\]+$/, '');

    // List remote files via exec (not SFTP subsystem, which may be sandboxed differently)
    const findOutput = await sftp.exec(
      `find "${normalizedRemote}" -type f -printf '%P\\t%s\\n' 2>/dev/null || find "${normalizedRemote}" -type f -exec stat -c '%n\\t%s' {} \\; 2>/dev/null | sed "s|^${normalizedRemote}/||"`
    );
    const remoteFiles = findOutput
      .trim()
      .split('\n')
      .filter(Boolean)
      .map((line) => {
        const [relativePath, sizeStr] = line.split('\t');
        return { relativePath, size: Number.parseInt(sizeStr || '0', 10) };
      });

    if (options?.dryRun) {
      sftp.close();
      return {
        success: true,
        filesTransferred: remoteFiles.length,
        bytesTransferred: remoteFiles.reduce((sum, f) => sum + f.size, 0),
        errors: [],
        duration: Date.now() - startTime,
      };
    }

    // Ensure local base directory exists
    await fsPromises.mkdir(normalizedLocal, { recursive: true });

    // Download files via exec (base64 encode on remote, decode locally)
    const totalBytes = remoteFiles.reduce((s, f) => s + f.size, 0);
    for (const file of remoteFiles) {
      const localFilePath = path.join(normalizedLocal, file.relativePath);
      try {
        await fsPromises.mkdir(path.dirname(localFilePath), { recursive: true });

        const b64 = await sftp.exec(`base64 "${normalizedRemote}/${file.relativePath}"`);
        const data = Buffer.from(b64.trim(), 'base64');
        await fsPromises.writeFile(localFilePath, data);
        filesTransferred++;
        bytesTransferred += data.length;
        options?.onProgress?.(file.relativePath, bytesTransferred, totalBytes);
      } catch (err) {
        errors.push(`${file.relativePath}: ${err instanceof Error ? err.message : String(err)}`);
      }
    }
  } finally {
    sftp.close();
  }

  return {
    success: errors.length === 0,
    filesTransferred,
    bytesTransferred,
    errors,
    duration: Date.now() - startTime,
  };
}
