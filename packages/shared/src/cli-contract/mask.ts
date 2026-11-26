/**
 * Parameter masking shared by the web (before a history entry leaves the browser), the
 * account route (before insert) and the CLI argv redaction (D7 of
 * agent/plans/PLAN-console-run-index.md).
 *
 * A key is masked when the contract marks the option `sensitive`, or when the contract does
 * not know the key as an option and its name looks sensitive (fail closed). A positional is
 * masked by that name rule alone, since the contract carries no per-positional flag, so one whose
 * name looks innocuous (`ref`) keeps its value. A known non-sensitive option keeps its value. Nested objects and arrays are scanned for sensitive key names.
 */
import { isSensitiveKey } from '../telemetry/utils.js';
import type { ContractCommand } from './types.js';

/** The placeholder a masked value is stored as. */
export const MASKED = '__redacted__';

/** Whether the value under `key` must not be stored or shown. */
export function isSensitiveParam(entry: ContractCommand | undefined, key: string): boolean {
  const option = entry?.options.find((o) => o.long === key);
  return option ? option.sensitive === true : isSensitiveKey(key);
}

/** Mask every nested key whose name looks sensitive, through objects and arrays. */
function maskNested(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(maskNested);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([k, v]) => [k, isSensitiveKey(k) ? MASKED : maskNested(v)])
    );
  }
  return value;
}

/** A copy of `params` with every sensitive value replaced by {@link MASKED}. */
export function maskParams(
  entry: ContractCommand | undefined,
  params: Record<string, unknown>
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(params)) {
    out[key] = isSensitiveParam(entry, key) ? MASKED : maskNested(value);
  }
  return out;
}
