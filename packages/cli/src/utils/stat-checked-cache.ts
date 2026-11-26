import { statSync } from 'node:fs';

interface Entry {
  path: string;
  mtimeMs: number;
  size: number;
}

/**
 * Remembers where a lookup found a file, and re-stats that file on every hit.
 *
 * A hit is handed out only while the file still exists with the mtime and size it had when stored.
 * A changed mtime or size is read as "replaced" and a missing file as "removed": either drops the entry
 * so the caller probes again. The comparison is a heuristic and not proof of identity: a touch changes
 * the mtime of an unchanged file (one extra probe), and a replacement with the same size and the same
 * mtime is not noticed. A miss is never stored, and neither is a path that cannot be stat'ed (nothing
 * to re-check it against).
 */
export class StatCheckedCache {
  private readonly entries = new Map<string, Entry>();

  /** The stored path when its file is still there with the same mtime and size, else undefined. */
  get(key: string): string | undefined {
    const entry = this.entries.get(key);
    if (!entry) return undefined;
    try {
      const stat = statSync(entry.path);
      if (stat.mtimeMs === entry.mtimeMs && stat.size === entry.size) return entry.path;
    } catch {
      // Removed since the lookup: fall through and drop it.
    }
    this.entries.delete(key);
    return undefined;
  }

  /** Stores a found path; a path that cannot be stat'ed is not stored. */
  set(key: string, path: string): void {
    try {
      const stat = statSync(path);
      this.entries.set(key, { path, mtimeMs: stat.mtimeMs, size: stat.size });
    } catch {
      this.entries.delete(key);
    }
  }
}
