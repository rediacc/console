/**
 * Ticket-group scratch records (PLAN-detached-jobs, `config reconcile`).
 *
 * A command that runs one job per machine under one command (`config reconcile`) needs the per-machine answers in
 * one place when the group's last ticket settles, whichever process observes it. Each machine's step stores its
 * record here, keyed by the command's group id (a request id minted once by the command), and the final step reads
 * every record of the group and drops them.
 *
 * One file per record at `<config dir>/jobs/<config>.scratch/<group>/<key>.json` (directories 0700, files 0600), so
 * concurrent writers never share a file and need no lock. A record is a listing or an error text: no secret enters
 * it, and a group older than STALE_GROUP_MS is removed the next time any group is written.
 */

import {
  chmodSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { join } from 'node:path';
import { getConfigDir } from '@rediacc/shared/paths';

const STALE_GROUP_MS = 24 * 60 * 60 * 1000;
const NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const CLAIM_DIR = 'settled.claim';

/** One machine's record: its captured listing, or why none was recorded. */
export type ScratchRecord = { ok: true; value: string } | { ok: false; error: string };

function parseRecord(path: string): { key: string; record: ScratchRecord } | undefined {
  let parsed: { key?: unknown; ok?: unknown; value?: unknown; error?: unknown };
  try {
    parsed = JSON.parse(readFileSync(path, 'utf8'));
  } catch {
    return undefined; // a torn file never takes the group down
  }
  if (typeof parsed.key !== 'string') return undefined;
  if (parsed.ok === true && typeof parsed.value === 'string') {
    return { key: parsed.key, record: { ok: true, value: parsed.value } };
  }
  if (parsed.ok === false && typeof parsed.error === 'string') {
    return { key: parsed.key, record: { ok: false, error: parsed.error } };
  }
  return undefined;
}

export class ScratchStore {
  private readonly root: string;

  constructor(
    readonly config: string,
    baseDir: string = getConfigDir()
  ) {
    if (!NAME.test(config)) {
      throw new Error(`Invalid config name for the scratch store: ${JSON.stringify(config)}`);
    }
    this.root = join(baseDir, 'jobs', `${config}.scratch`);
  }

  private groupDir(group: string): string {
    if (!NAME.test(group)) throw new Error(`Invalid scratch group id: ${JSON.stringify(group)}`);
    return join(this.root, group);
  }

  /** A record file name for a key: any machine name, encoded so it cannot leave the group directory. */
  private static fileFor(key: string): string {
    return `${encodeURIComponent(key).replaceAll('.', '%2E')}.json`;
  }

  /** Store `record` under `key`; the last write for a key wins. */
  write(group: string, key: string, record: ScratchRecord): void {
    const dir = this.groupDir(group);
    mkdirSync(dir, { recursive: true, mode: 0o700 });
    chmodSync(this.root, 0o700);
    chmodSync(dir, 0o700);
    const path = join(dir, ScratchStore.fileFor(key));
    const tmp = `${path}.${process.pid}.tmp`;
    writeFileSync(tmp, JSON.stringify({ key, ...record }), { mode: 0o600 });
    renameSync(tmp, path);
    this.dropStale(group);
  }

  /** Every record of the group, by key. A torn or foreign file is skipped. */
  read(group: string): Map<string, ScratchRecord> {
    const out = new Map<string, ScratchRecord>();
    const dir = this.groupDir(group);
    let names: string[];
    try {
      names = readdirSync(dir);
    } catch {
      return out;
    }
    for (const name of names) {
      if (!name.endsWith('.json')) continue;
      const record = parseRecord(join(dir, name));
      if (record) out.set(record.key, record.record);
    }
    return out;
  }

  /** Mark `key` as done with the group: its job ended or never started, so no more records are coming from it. */
  finish(group: string, key: string): void {
    const dir = this.groupDir(group);
    mkdirSync(dir, { recursive: true, mode: 0o700 });
    writeFileSync(join(dir, ScratchStore.fileFor(key).replace(/\.json$/, '.done')), '', {
      mode: 0o600,
    });
  }

  /** Has every one of `keys` finished? An empty list has nothing to wait for. */
  allFinished(group: string, keys: string[]): boolean {
    const dir = this.groupDir(group);
    return keys.every((key) =>
      existsSync(join(dir, ScratchStore.fileFor(key).replace(/\.json$/, '.done')))
    );
  }

  /**
   * Take the group's one settlement. Creating a directory is atomic, so of two observers that see the group complete
   * at once exactly one gets true.
   */
  claim(group: string): boolean {
    const dir = this.groupDir(group);
    mkdirSync(dir, { recursive: true, mode: 0o700 });
    try {
      mkdirSync(join(dir, CLAIM_DIR));
      return true;
    } catch {
      return false;
    }
  }

  drop(group: string): void {
    rmSync(this.groupDir(group), { recursive: true, force: true });
  }

  /** Remove other groups untouched for a day (a command that never reached its final step). */
  private dropStale(keep: string): void {
    let groups: string[];
    try {
      groups = readdirSync(this.root);
    } catch {
      return;
    }
    for (const group of groups) {
      if (group === keep) continue;
      const path = join(this.root, group);
      try {
        if (Date.now() - statSync(path).mtimeMs > STALE_GROUP_MS) {
          rmSync(path, { recursive: true, force: true });
        }
      } catch {
        // already gone
      }
    }
  }
}
