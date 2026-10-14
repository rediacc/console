import fs from 'node:fs';
import path from 'node:path';

const swapCase = (s) =>
  [...s].map((c) => (c === c.toLowerCase() ? c.toUpperCase() : c.toLowerCase())).join('');

// Whether the volume holding this directory ignores case, found by asking for the directory under a spelling with its last segment's case swapped: only a case-insensitive volume resolves it. Case-sensitive volumes (Linux, or a case-sensitive APFS volume) keep two directories that differ only by case apart.
const ignoresCase = (p) => {
  const swapped = path.join(path.dirname(p), swapCase(path.basename(p)));
  if (swapped === p) return false;
  try {
    fs.realpathSync(swapped);
    return true;
  } catch {
    return false;
  }
};

// Whether two paths name the same directory however they are spelled (another casing on a case-insensitive filesystem, a symlink, a bind mount). Device and inode answer it; a filesystem that reports inode 0 for directories gives no identity, so the real paths are compared instead, case-folded only where the platform defaults to case-insensitive filesystems and the volume really ignores case.
export const sameDirectory = (a, b, platform = process.platform) => {
  const x = fs.statSync(a);
  const y = fs.statSync(b);
  if (x.ino !== 0 && y.ino !== 0) return x.dev === y.dev && x.ino === y.ino;
  const realA = fs.realpathSync(a);
  const realB = fs.realpathSync(b);
  if (realA === realB) return true;
  const foldable = platform === 'darwin' || platform === 'win32';
  return foldable && ignoresCase(realA) && realA.toLowerCase() === realB.toLowerCase();
};
