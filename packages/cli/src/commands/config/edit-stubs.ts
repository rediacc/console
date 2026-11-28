/**
 * Redaction-stub reconciliation for `rdc config edit`: comment stripping, stub
 * classification against the current config, and the `--current-secrets` file.
 */

import { readFileSync } from 'node:fs';
import {
  canonicalJson,
  getByPointer,
  type RdcConfig,
  walkSensitive,
} from '@rediacc/shared/config-schema';
import { shortFingerprint } from '../../schema/fingerprint.js';
import { ValidationError } from '../../utils/errors.js';
import { parseJsonText } from '../../utils/json-text.js';

const REDACT_PATTERN = /^<redacted:[^>]+>:[0-9a-f]{8}$/;

/**
 * Strip JSONC comment lines (lines starting with `//` after optional whitespace).
 * Block comments and inline `//` are NOT supported, the renderer only emits
 * line comments before the JSON body, so the stripper handles only that form.
 */
export function stripComments(jsonc: string): string {
  return jsonc
    .split('\n')
    .filter((line) => !/^\s*\/\//.test(line))
    .join('\n');
}

/** What `classifyStub` decided for one sensitive path; the rules are documented on `reconcileStubs`. */
type StubOutcome =
  | { kind: 'untouched'; currentValue: unknown }
  | { kind: 'bad-stub' }
  | { kind: 'bad-knowledge' }
  | { kind: 'rotation' }
  | { kind: 'accepted' }
  | { kind: 'public' };

function classifyStub(
  pointer: string,
  editedValue: unknown,
  currentConfig: RdcConfig,
  meta: { kind: string; redactAs?: string },
  knowledge: Record<string, unknown> | undefined
): StubOutcome {
  if (meta.kind === 'public') return { kind: 'public' };

  const currentValue = getByPointer(currentConfig, pointer);
  const currentStub =
    currentValue === null || currentValue === undefined
      ? null
      : `${meta.redactAs ?? `<redacted:${meta.kind}>`}:${shortFingerprint(currentValue)}`;

  if (typeof editedValue === 'string' && currentStub && editedValue === currentStub) {
    return { kind: 'untouched', currentValue };
  }

  if (typeof editedValue === 'string' && REDACT_PATTERN.test(editedValue)) {
    return { kind: 'bad-stub' };
  }

  return classifyReplaced(pointer, currentValue, knowledge);
}

function classifyReplaced(
  pointer: string,
  currentValue: unknown,
  knowledge: Record<string, unknown> | undefined
): StubOutcome {
  // A value that did not exist before rotates nothing: keep it.
  if (currentValue === undefined || currentValue === null) return { kind: 'accepted' };

  const claim = knowledge?.[pointer];
  if (claim === undefined) return { kind: 'rotation' };
  return canonicalJson(claim) === canonicalJson(currentValue)
    ? { kind: 'accepted' }
    : { kind: 'bad-knowledge' };
}

const FAILURE_TEXT = {
  'bad-stub':
    'edited value still looks like a redaction stub but does not match the current digest',
  'bad-knowledge': 'the --current-secrets value does not match the current value',
};

/**
 * Detect modified `<redacted:...>` stubs by comparing each sensitive path's
 * value in the edited config against the current config's stub.
 *
 * Rules:
 *   - Unchanged stub  (stub matches current digest)  → substitute real value back.
 *   - Stub replaced with a DIFFERENT stub             → hard failure (meaningless edit).
 *   - Stub replaced with real plaintext               → rotation intent.
 *     - If knowledge[pointer] supplied (via --current-secrets) and it matches the
 *       current value: accept the new value; a mismatch is a hard failure.
 *     - Otherwise: surface on `rotations` so the caller can prompt or reject.
 *   - A sensitive value with no current value (newly added)  → accepted as is.
 *
 * Returning `rotations` (instead of immediately failing) lets interactive mode
 * show a single confirmation prompt for all rotations; non-interactive `--apply`
 * keeps strict behavior by converting `rotations` to `failures` at the call site.
 */
export function reconcileStubs(
  edited: unknown,
  currentConfig: RdcConfig,
  knowledge: Record<string, unknown> | undefined
): { result: unknown; failures: string[]; rotations: string[] } {
  const failures: string[] = [];
  const rotations: string[] = [];
  const view = JSON.parse(JSON.stringify(edited));

  for (const { pointer, value: editedValue, meta } of walkSensitive(view as RdcConfig)) {
    const outcome = classifyStub(pointer, editedValue, currentConfig, meta, knowledge);
    if (outcome.kind === 'public' || outcome.kind === 'accepted') continue;
    if (outcome.kind === 'untouched') assignAtPointer(view, pointer, outcome.currentValue);
    else if (outcome.kind === 'rotation') rotations.push(pointer);
    else failures.push(`${pointer}: ${FAILURE_TEXT[outcome.kind]}`);
  }

  return { result: view, failures, rotations };
}

function assignAtPointer(root: unknown, pointer: string, value: unknown): void {
  if (pointer === '') return;
  const segments = pointer
    .split('/')
    .slice(1)
    .map((s) => s.replaceAll('~1', '/').replaceAll('~0', '~'));
  let cursor: Record<string, unknown> | undefined = root as Record<string, unknown>;
  for (let i = 0; i < segments.length - 1; i++) {
    cursor = cursor[segments[i]] as Record<string, unknown> | undefined;
    if (!cursor) return;
  }
  cursor[segments[segments.length - 1]] = value;
}

export function loadKnowledgeFile(path: string): Record<string, unknown> {
  const text = readFileSync(path, 'utf8');
  const raw: unknown = parseJsonText(text);
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new ValidationError(`--current-secrets must be a JSON object: ${path}`);
  }
  return raw as Record<string, unknown>;
}
