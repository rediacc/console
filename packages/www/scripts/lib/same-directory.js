import fs from 'node:fs';
import path from 'node:path';

const swapCase = (s) =>
  [...s].map((c) => (c === c.toLowerCase() ? c.toUpperCase() : c.toLowerCase())).join('');

// The deepest segment of the path with letters whose case can be swapped, as the directory holding it, its name, the swapped name and the path below it. A trailing segment such as `2024` has no case, so the probe moves up to the nearest segment that does.
const cased = (p) => {
  let cur = p;
  for (;;) {
    const dir = path.dirname(cur);
    if (dir === cur) return null;
    const name = path.basename(cur);
    const swapped = swapCase(name);
    if (swapped !== name) return { dir, name, swapped, rest: path.relative(cur, p) };
    cur = dir;
  }
};

// Whether the volume holding this directory ignores case, found by asking for the directory under a spelling with one segment's case swapped: a case-insensitive volume resolves it, yet lists only the stored spelling. A case-sensitive volume (Linux, or a case-sensitive APFS volume) either fails the lookup or, when a sibling that differs only by case exists, resolves it and lists it as its own entry, so the listing is what tells the two apart.
const ignoresCase = (p) => {
  const probe = cased(p);
  if (!probe) return false;
  try {
    // A probe that moved up to an ancestor answers for the ancestor's volume, so the directory itself must sit on the same device; a mount point below it (a case-sensitive volume under a case-insensitive parent) gives no answer, and nothing folds.
    if (probe.rest !== '' && fs.statSync(p).dev !== fs.statSync(probe.dir).dev) return false;
    fs.realpathSync(path.join(probe.dir, probe.swapped, probe.rest));
    return !fs.readdirSync(probe.dir).includes(probe.swapped);
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
