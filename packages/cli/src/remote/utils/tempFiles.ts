import { randomBytes } from 'node:crypto';
import { chmod, readFile, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { getPlatform, getTempPath } from './platform.js';

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
 * Safely removes a temporary file
 */
export async function removeTempFile(filePath: string): Promise<void> {
  try {
    await rm(filePath, { force: true });
  } catch {
    // Ignore errors during cleanup
  }
}
