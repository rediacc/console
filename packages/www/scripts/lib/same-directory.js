import fs from 'node:fs';

// Whether two paths name the same directory however they are spelled (another casing on a case-insensitive filesystem, a symlink, a bind mount). Device and inode answer it; a filesystem that reports inode 0 for directories gives no identity, so the real paths are compared instead, case-folded where the platform's filesystems default to case-insensitive.
export const sameDirectory = (a, b, platform = process.platform) => {
  const x = fs.statSync(a);
  const y = fs.statSync(b);
  if (x.ino !== 0 && y.ino !== 0) return x.dev === y.dev && x.ino === y.ino;
  const fold = (p) => {
    const real = fs.realpathSync(p);
    return platform === 'darwin' || platform === 'win32' ? real.toLowerCase() : real;
  };
  return fold(a) === fold(b);
};
