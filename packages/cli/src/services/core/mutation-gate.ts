/**
 * MutationGate, the single chokepoint every config mutation flows through.
 *
 * Responsibilities:
 *   1. Detect which sensitive paths are being mutated (by diffing previous vs new).
 *   2. For each sensitive path, enforce knowledge-gates-capability: require a
 *      matching `--current` digest, a previously empty pointer, or, for a human at
 *      an interactive terminal only, explicit `rotateAcknowledged` (the
 *      `--rotate-secret` / `--rotate` flag). An agent has exactly the first two;
 *      no environment variable widens that.
 *   3. Emit audit log entries for every decision.
 *   4. Fail fast (before any network or disk write) with PreconditionMismatchError.
 *
 * The knowledge check itself is symmetric: a TTY does not let a human skip
 * `--current`. A TTY only decides whether a rotation acknowledgement counts,
 * so a script an agent drives outside the ancestry check cannot rotate either.
 *
 * The gate is DATA-SHAPE-AGNOSTIC: it operates on JSON-Pointer+value pairs
 * produced by the schema walker, so it doesn't care whether the config is in
 * v1 or v2 shape at the call site. This is important because Step 2 of the
 * refactor (types consolidation) is deferred to the final sweep; until then,
 * callers can pass v1-shape or v2-shape diffs and the gate handles both.
 */

import { isatty } from 'node:tty';
import type { SensitivityMeta } from '@rediacc/shared/config-schema';
import { metaForPointer } from '@rediacc/shared/config-schema';
import { digestForPointer } from '../../schema/fingerprint.js';
import { isAgentEnvironment } from '../../utils/agent-guard.js';

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
   * available). Adds a loud audit log entry. Honoured only for a human with a
   * TTY on stdin; an agent, or any caller without a TTY, still needs `--current`.
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
  readonly failures: { pointer: string; reason: string }[];
  constructor(failures: { pointer: string; reason: string }[]) {
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

interface SingleMutationResult {
  decision: GateDecision;
  failure?: { pointer: string; reason: string };
}

/** The refusal for a sensitive mutation that carries no `--current` claim. */
function missingKnowledge(
  pointer: string,
  meta: SensitivityMeta,
  agent: boolean,
  rotateClaimed: boolean
): SingleMutationResult {
  if (rotateClaimed) {
    return {
      decision: {
        pointer,
        meta,
        action: 'refused',
        reason: 'rotate not honoured (agent or no TTY)',
      },
      failure: {
        pointer,
        reason:
          'a rotation without --current is honoured only for a human at an interactive terminal; supply --current',
      },
    };
  }
  return {
    decision: { pointer, meta, action: 'refused', reason: 'missing knowledge' },
    failure: {
      pointer,
      reason: agent
        ? 'sensitive path requires --current'
        : 'sensitive path requires --current (or --rotate-secret at an interactive terminal)',
    },
  };
}

/**
 * Evaluate a single sensitive-path mutation. The allow paths in order of precedence:
 *
 *   1. Explicit rotation acknowledgement (rotateAcknowledged Set populated by
 *      `--rotate-secret` / `--rotate`), honoured only when `rotateHonoured`
 *      (a human with a TTY on stdin).
 *   2. A previously empty pointer (a human outright; an agent with a knowledge claim).
 *   3. Knowledge claim matching the stored digest.
 */
function evaluateSensitiveMutation(
  entry: MutationEntry,
  meta: SensitivityMeta,
  context: MutationContext,
  agent: boolean,
  rotateHonoured: boolean
): SingleMutationResult {
  const rotateClaimed = context.rotateAcknowledged?.has(entry.pointer) === true;
  if (rotateClaimed && rotateHonoured) {
    return {
      decision: { pointer: entry.pointer, meta, action: 'allowed', reason: 'rotate acknowledged' },
    };
  }

  const stored = digestForPointer(context.previousConfig, entry.pointer);
  if (stored === undefined && !agent) {
    // New field added by a HUMAN, there is no previous value to verify, so the passwd-style ceremony does not apply (--current is documented as required for overwrite/unset). Agents keep the explicit ceremony even on first write (existing precedent). Permit, but audit.
    return {
      decision: {
        pointer: entry.pointer,
        meta,
        action: 'allowed',
        reason: 'new field',
      },
    };
  }

  const claimed = context.knowledge?.[entry.pointer];
  if (!claimed) return missingKnowledge(entry.pointer, meta, agent, rotateClaimed);

  if (stored === undefined) {
    // Agent first-write with a knowledge claim, nothing to verify against. Treat as rotation: permit, but audit.
    return {
      decision: {
        pointer: entry.pointer,
        meta,
        action: 'allowed',
        reason: 'new field with knowledge claim',
      },
    };
  }

  if (stored !== claimed) {
    return {
      decision: { pointer: entry.pointer, meta, action: 'refused', reason: 'digest mismatch' },
      failure: {
        pointer: entry.pointer,
        reason: `--current digest mismatch (expected ${stored.slice(0, 8)}…, got ${claimed.slice(0, 8)}…)`,
      },
    };
  }

  return {
    decision: { pointer: entry.pointer, meta, action: 'allowed', reason: 'knowledge verified' },
  };
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
  const failures: { pointer: string; reason: string }[] = [];
  const agent = isAgentEnvironment();
  // A rotation acknowledgement skips the knowledge proof, so it counts only for a human at a terminal.
  const rotateHonoured = !agent && isatty(process.stdin.fd);

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

    const { decision, failure } = evaluateSensitiveMutation(
      entry,
      meta,
      context,
      agent,
      rotateHonoured
    );
    decisions.push(decision);
    if (failure) failures.push(failure);
  }

  if (failures.length > 0) {
    throw new PreconditionMismatchError(failures);
  }

  return decisions;
}
