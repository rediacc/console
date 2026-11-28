/**
 * Replay a whole-document save as the edit it made.
 *
 * A caller that saves a whole config built from the copy it read hands the
 * writeback a document, not an edit. Pushed as-is after a lost compare-and-swap,
 * that document would overwrite whatever another device wrote meanwhile. So the
 * save is turned back into its edit: the keys whose value differs between the
 * copy the caller read and the document it saves are set on the newest copy, and
 * the keys it dropped are deleted there. Plain objects are compared key by key;
 * arrays and other values are replaced whole. The top-level `version` is the
 * store's to set and never carried.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';

type Plain = Record<string, unknown>;

function isPlain(value: unknown): value is Plain {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function applyKey(target: Plain, read: Plain, saved: Plain, key: string): void {
  const before = read[key];
  const after = saved[key];
  if (key in read && same(before, after)) return;
  const here = target[key];
  if (isPlain(before) && isPlain(after) && isPlain(here)) {
    applyInto(here, before, after, new Set());
  } else {
    target[key] = structuredClone(after);
  }
}

function applyInto(target: Plain, read: Plain, saved: Plain, skip: ReadonlySet<string>): void {
  for (const key of Object.keys(saved)) {
    if (!skip.has(key)) applyKey(target, read, saved, key);
  }
  for (const key of Object.keys(read)) {
    if (skip.has(key) || key in saved) continue;
    delete target[key];
  }
}

/** `newest` with the edit that turned `read` into `saved` applied to it. */
export function replaySavedEdit(newest: RdcConfig, read: RdcConfig, saved: RdcConfig): RdcConfig {
  const next = structuredClone(newest) as unknown as Plain;
  applyInto(next, read as unknown as Plain, saved as unknown as Plain, new Set(['version']));
  return next as unknown as RdcConfig;
}
