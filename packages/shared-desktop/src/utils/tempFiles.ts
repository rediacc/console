import { randomBytes } from 'crypto';
import { existsSync } from 'fs';
import { chmod, mkdtemp, rm, writeFile, mkdir, readFile } from 'fs/promises';
import { join } from 'path';
import { getTempPath, getConfigPath, getPlatform } from './platform.js';

/**
 * Generates a random file name with optional prefix and extension
 */
function generateTempName(prefix = 'rediacc', extension = ''): string {
  const random = randomBytes(8).toString('hex');
  return `${prefix}-${random}${extension}`;
}

/**
 * Creates a temporary file with secure permissions (0o600)
 * Returns the path to the created file
 *
 * On Windows, performs a read-back validation to work around potential
 * issues with libcrypto and file system caching (matches Python CLI behavior)
 */
export async function createSecureTempFile(
  content: string | Buffer,
  options: {
    prefix?: string;
    extension?: string;
    directory?: string;
  } = {}
): Promise<string> {
  const { prefix = 'rediacc', extension = '', directory } = options;

  const tempDir = directory ?? getTempPath();
  const fileName = generateTempName(prefix, extension);
  const filePath = join(tempDir, fileName);

  // Write file
  await writeFile(filePath, content, { mode: 0o600 });

  // Explicitly set permissions (in case umask affected the mode)
  await chmod(filePath, 0o600);

  // Windows validation: Read back the file to ensure it was written correctly
  // This works around potential issues with file system caching and libcrypto
  // (matches Python CLI behavior from shared.py:629-637)
  if (getPlatform() === 'windows') {
    const written = await readFile(filePath);
    const expected = typeof content === 'string' ? Buffer.from(content) : content;
    if (!written.equals(expected)) {
      throw new Error(
        `SSH key file validation failed: written content does not match expected content`
      );
    }
  }

  return filePath;
}

/**
 * Creates a temporary SSH key file with proper permissions
 */
export async function createTempSSHKey(privateKey: string): Promise<string> {
  // Normalize the key - ensure it has proper line endings
  let normalizedKey = privateKey.trim();

  // Ensure the key ends with a newline (required by SSH)
  if (!normalizedKey.endsWith('\n')) {
    normalizedKey += '\n';
  }

  return createSecureTempFile(normalizedKey, {
    prefix: 'ssh-key',
    extension: '.pem',
  });
}

/**
 * Creates a temporary directory with secure permissions
 */
export async function createSecureTempDir(prefix = 'rediacc'): Promise<string> {
  const tempBase = getTempPath();
  const dirPath = await mkdtemp(join(tempBase, `${prefix}-`));

  // Set secure permissions on the directory
  await chmod(dirPath, 0o700);

  return dirPath;
}

/**
 * Safely removes a temporary file
 */
export async function removeTempFile(filePath: string): Promise<void> {
  try {
    await rm(filePath, { force: true });
  } catch {
    // Ignore errors during cleanup
  }
}

/**
 * Safely removes a temporary directory and its contents
 */
export async function removeTempDir(dirPath: string): Promise<void> {
  try {
    await rm(dirPath, { recursive: true, force: true });
  } catch {
    // Ignore errors during cleanup
  }
}

/**
 * Creates a temp file that auto-cleans on process exit
 */
export async function createAutoCleanTempFile(
  content: string | Buffer,
  options: {
    prefix?: string;
    extension?: string;
  } = {}
): Promise<string> {
  const filePath = await createSecureTempFile(content, options);

  // Register cleanup handlers
  const cleanup = () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      (require('fs') as typeof import('fs')).unlinkSync(filePath);
    } catch {
      // Ignore
    }
  };

  process.once('exit', cleanup);
  process.once('SIGINT', cleanup);
  process.once('SIGTERM', cleanup);

  return filePath;
}

/**
 * Gets or creates the Rediacc cache directory
 */
export async function getCacheDir(): Promise<string> {
  const configPath = getConfigPath();
  const cacheDir = join(configPath, 'cache');

  if (!existsSync(cacheDir)) {
    await mkdir(cacheDir, { recursive: true, mode: 0o700 });
  }

  return cacheDir;
}

/**
 * Creates a file in the cache directory
 */
export async function writeCacheFile(filename: string, content: string | Buffer): Promise<string> {
  const cacheDir = await getCacheDir();
  const filePath = join(cacheDir, filename);
  await writeFile(filePath, content, { mode: 0o600 });
  return filePath;
}
