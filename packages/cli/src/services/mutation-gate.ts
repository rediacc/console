/**
 * MutationGate — the single chokepoint every config mutation flows through.
 *
 * Responsibilities:
 *   1. Detect which sensitive paths are being mutated (by diffing previous vs new).
 *   2. For each sensitive path, enforce the knowledge-gates-capability rule:
 *      - Agent context: require matching `--current` digest OR explicit rotate OR
 *        REDIACC_ALLOW_CONFIG_EDIT scope override.
 *      - Human interactive TTY: bypass (human owns the file).
 *   3. Emit audit log entries for every decision.
 *   4. Fail fast (before any network or disk write) with PreconditionMismatchError.
 *
 * The gate is DATA-SHAPE-AGNOSTIC: it operates on JSON-Pointer+value pairs
 * produced by the schema walker, so it doesn't care whether the config is in
 * v1 or v2 shape at the call site. This is important because Step 2 of the
 * refactor (types consolidation) is deferred to the final sweep; until then,
 * callers can pass v1-shape or v2-shape diffs and the gate handles both.
 */

import { configEditOverrideScope, isAgentEnvironment, scopeAllows } from '../utils/agent-guard.js';
import { digestForPointer } from '../schema/walker.js';
import { metaForPointer } from '../schema/walker.js';
import type { SensitivityMeta } from '../schema/sensitivity.js';

export interface MutationEntry {
  /** JSON Pointer to the mutated leaf. */
  pointer: string;
  /** The value the config currently has (pre-mutation). undefined = new field. */
  previousValue: unknown;
  /** The value the caller wants to write. undefined = deletion. */
  newValue: unknown;
}

export interface MutationContext {
  /**
   * Digests the caller claims to know for specific pointers.
   * Key: JSON Pointer. Value: hex-encoded SHA-256 digest of the plaintext
   * value the caller supplied as `--current`.
   *
   * For each sensitive-path mutation, the gate checks that
   * `knowledge[pointer]` equals `digestForPointer(previousConfig, pointer)`.
   */
  knowledge?: Record<string, string>;
  /**
   * Explicit acknowledgement that the mutation is a rotation (no `--current`
   * available). Adds a loud audit log entry. Agents can only use this with
   * REDIACC_ALLOW_CONFIG_EDIT set in ancestry.
   */
  rotateAcknowledged?: Set<string>;
  /**
   * Caller declares that the user passed `--reveal` in an interactive TTY.
   * Used for display-redaction decisions, not for gate-bypass.
   */
  reveal?: boolean;
  /** The full config object, used to compute current digests. */
  previousConfig: unknown;
}

export class PreconditionMismatchError extends Error {
  readonly failures: Array<{ pointer: string; reason: string }>;
  constructor(failures: Array<{ pointer: string; reason: string }>) {
    super(
      `Precondition failed for ${failures.length} path(s):\n${failures
        .map((f) => `  ${f.pointer}: ${f.reason}`)
        .join('\n')}`
    );
    this.name = 'PreconditionMismatchError';
    this.failures = failures;
  }
}

export interface GateDecision {
  pointer: string;
  meta: SensitivityMeta | undefined;
  action: 'allowed' | 'refused';
  reason: string;
}

/**
 * Evaluate a batch of mutations. If any sensitive path fails the knowledge
 * gate without an acknowledgement, throws PreconditionMismatchError before
 * ANY side effects.
 *
 * Returns per-pointer decisions for audit-log emission by the caller.
 */
export function evaluateMutations(
  entries: readonly MutationEntry[],
  context: MutationContext
): GateDecision[] {
  const decisions: GateDecision[] = [];
  const failures: Array<{ pointer: string; reason: string }> = [];
  const agent = isAgentEnvironment();
  const overrideScope = agent ? configEditOverrideScope() : null;

  for (const entry of entries) {
    const meta = metaForPointer(entry.pointer);
    if (!meta || meta.kind === 'public') {
      decisions.push({
        pointer: entry.pointer,
        meta,
        action: 'allowed',
        reason: 'public or unregistered',
      });
      continue;
    }

    // Non-agent: human TTY owns the file, pass.
    if (!agent) {
      decisions.push({
        pointer: entry.pointer,
        meta,
        action: 'allowed',
        reason: 'human tty',
      });
      continue;
    }

    // Agent path below.
    if (overrideScope && scopeAllows(overrideScope, entry.pointer)) {
      decisions.push({
        pointer: entry.pointer,
        meta,
        action: 'allowed',
        reason: `override scope (${overrideScope})`,
      });
      continue;
    }

    if (context.rotateAcknowledged?.has(entry.pointer)) {
      decisions.push({
        pointer: entry.pointer,
        meta,
        action: 'allowed',
        reason: 'rotate acknowledged',
      });
      continue;
    }

    const claimed = context.knowledge?.[entry.pointer];
    if (!claimed) {
      failures.push({
        pointer: entry.pointer,
        reason: 'sensitive path requires --current (or --rotate-secret)',
      });
      decisions.push({
        pointer: entry.pointer,
        meta,
        action: 'refused',
        reason: 'missing knowledge',
      });
      continue;
    }

    const stored = digestForPointer(context.previousConfig, entry.pointer);
    if (stored === undefined) {
      // New field being added — knowledge claim has nothing to verify against.
      // Treat as rotation: permit, but audit.
      decisions.push({
        pointer: entry.pointer,
        meta,
        action: 'allowed',
        reason: 'new field with knowledge claim',
      });
      continue;
    }

    if (stored !== claimed) {
      failures.push({
        pointer: entry.pointer,
        reason: `--current digest mismatch (expected ${stored.slice(0, 8)}…, got ${claimed.slice(0, 8)}…)`,
      });
      decisions.push({
        pointer: entry.pointer,
        meta,
        action: 'refused',
        reason: 'digest mismatch',
      });
      continue;
    }

    decisions.push({
      pointer: entry.pointer,
      meta,
      action: 'allowed',
      reason: 'knowledge verified',
    });
  }

  if (failures.length > 0) {
    throw new PreconditionMismatchError(failures);
  }

  return decisions;
}
