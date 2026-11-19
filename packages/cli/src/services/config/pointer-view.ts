/**
 * The redacted view of the config at any JSON Pointer, leaf or subtree.
 *
 * `rdc config field get` used to consult the sensitivity registry for the
 * pointer it was given and nothing else, so `--pointer /credentials` printed
 * every secret below it verbatim while `--pointer /credentials/cfDnsApiToken`
 * redacted. The view here applies the same per-leaf rules at every depth:
 *
 * - a registered ancestor (or the pointer itself) decides for the whole value,
 *   exactly as `walkSensitive` treats a registered container as one leaf: a
 *   `public` one passes the value through, any other kind replaces it with its
 *   `<redacted:kind>:<digest>` stub;
 * - otherwise the value is read out of `redactClone(config)`, so every
 *   registered leaf below the pointer carries its stub at its real absolute
 *   pointer.
 */

import { getByPointer, metaForPointer, walkSensitive } from '@rediacc/shared/config-schema';
import { redactClone, shortFingerprint } from '../../schema/fingerprint.js';

export interface PointerView {
  /** The value with every non-public leaf at or below the pointer replaced by its stub. */
  redacted: unknown;
  /** True when at least one non-public value sits at or below the pointer. */
  sensitive: boolean;
}

function isUnder(candidate: string, pointer: string): boolean {
  return pointer === '' || candidate === pointer || candidate.startsWith(`${pointer}/`);
}

/** The view decided by the nearest registered ancestor (or the pointer itself), if any. */
function viewFromRegisteredAncestor(raw: unknown, pointer: string): PointerView | undefined {
  // The pointer's raw (still RFC 6901 escaped) segments rebuild each ancestor pointer verbatim.
  const segments = pointer === '' ? [] : pointer.split('/').slice(1);
  for (let depth = 1; depth <= segments.length; depth++) {
    const meta = metaForPointer(`/${segments.slice(0, depth).join('/')}`);
    if (!meta) continue;
    if (meta.kind === 'public') return { redacted: raw, sensitive: false };
    return {
      redacted: `${meta.redactAs ?? `<redacted:${meta.kind}>`}:${shortFingerprint(raw)}`,
      sensitive: true,
    };
  }
  return undefined;
}

/** True when a non-public, non-empty registered leaf sits at or below the pointer. */
function hasSensitiveBelow(config: unknown, pointer: string): boolean {
  for (const entry of walkSensitive(config)) {
    if (entry.meta.kind === 'public' || !isUnder(entry.pointer, pointer)) continue;
    if (entry.value !== null && entry.value !== undefined) return true;
  }
  return false;
}

/** Returns undefined when nothing exists at the pointer. */
export function redactedViewAtPointer(config: unknown, pointer: string): PointerView | undefined {
  const raw = getByPointer(config, pointer);
  if (raw === undefined) return undefined;
  const decided = viewFromRegisteredAncestor(raw, pointer);
  if (decided) return decided;
  if (!hasSensitiveBelow(config, pointer)) return { redacted: raw, sensitive: false };
  return { redacted: getByPointer(redactClone(config), pointer), sensitive: true };
}
