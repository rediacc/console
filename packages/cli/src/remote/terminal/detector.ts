import { existsSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Finds MSYS2 installation path on Windows
 */
export function findMSYS2Installation(): string | null {
  const msys2Paths = [
    process.env.MSYS2_ROOT,
    'C:\\msys64',
    'C:\\msys2',
    join(process.env.USERPROFILE ?? '', 'msys64'),
    join(process.env.USERPROFILE ?? '', 'msys2'),
  ].filter(Boolean) as string[];

  for (const path of msys2Paths) {
    if (existsSync(path)) {
      return path;
    }
  }
  return null;
}
