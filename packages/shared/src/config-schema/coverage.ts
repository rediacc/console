/**
 * Schema-coverage analysis for the sensitivity registry.
 *
 * Walks a Zod schema's TYPE tree (not a live value) and enumerates every leaf
 * as a JSON Pointer TEMPLATE — record keys and array indices become `*`, the
 * same wildcard convention the registry uses. A leaf is covered when the
 * registry holds a template that matches it, or when a registered ancestor
 * template matches one of its containers (the runtime walker stops at the
 * first match, treating the container as one leaf — e.g. `/policy`).
 *
 * The gate `check:ci-schema-coverage` (scripts/check-schema-coverage.ts) runs
 * this against RdcConfigSchema + SENSITIVITY_REGISTRY and fails closed on:
 *   - any schema leaf no registry template covers (an unclassified field), and
 *   - any registry template that matches nothing the schema can produce
 *     (registry rot — the entry silently commits/encrypts/redacts nothing).
 * The only carve-out is ENVELOPE_EXCLUSIONS below — the document's own
 * plumbing, which no sensitivity kind applies to.
 *
 * Mirrors walker.ts semantics: matching is per-segment with equal length,
 * `*` in a registry template matches any single segment. A CONCRETE registry
 * segment does NOT cover a record/array wildcard position — it would only
 * match one key at runtime, which is not coverage.
 */

import { z } from 'zod';
import { RdcConfigSchema } from './schemas.js';
import type { PointerTemplate } from './sensitivity.js';
import { buildPointer } from './walker.js';

interface DefLike {
  type: string;
  [key: string]: unknown;
}

/** Minimal structural view of a zod v4 schema (classic or core). */
interface SchemaLike {
  _zod: { def: DefLike };
}

function defOf(schema: unknown): DefLike {
  return (schema as SchemaLike)._zod.def;
}

function segments(template: string): string[] {
  return template === '' ? [] : template.split('/').slice(1);
}

/**
 * Registry template R covers schema node template N: equal length, and each
 * registry segment is `*` or equals the schema segment. A schema wildcard
 * (`*` from a record/array) is only covered by a registry `*`.
 */
function covers(registrySegs: string[], nodeSegs: string[]): boolean {
  if (registrySegs.length !== nodeSegs.length) return false;
  return registrySegs.every((rs, i) => rs === '*' || rs === nodeSegs[i]);
}

/**
 * Lenient match used only for STALENESS: a registry template still points at
 * something real if a schema node of the same length matches it with either
 * side's wildcard allowed (a concrete registry key under a record `*` is
 * narrow, but not dead).
 */
function matchesLeniently(registrySegs: string[], nodeSegs: string[]): boolean {
  if (registrySegs.length !== nodeSegs.length) return false;
  return registrySegs.every((rs, i) => rs === '*' || nodeSegs[i] === '*' || rs === nodeSegs[i]);
}

/** R descends into a registered (pruned) container we did not walk into. */
function hasPrunedAncestor(registrySegs: string[], pruned: string[][]): boolean {
  return pruned.some(
    (p) =>
      p.length < registrySegs.length &&
      p.every((ps, i) => ps === '*' || registrySegs[i] === '*' || ps === registrySegs[i])
  );
}

/**
 * Envelope machinery excluded from coverage, per the registry header contract:
 * these are the document's OWN plumbing, not data fields a sensitivity kind
 * applies to. `schemaVersion`/`id`/`version` identify and order the document
 * (they ride in the plaintext envelope, never redacted or encrypted), and
 * `encryption` holds the at-rest MODE plus the ciphertexts OF other fields —
 * classifying ciphertexts as sensitive would be circular. Everything else in
 * the schema, present or future, must carry a registry entry.
 */
export const ENVELOPE_EXCLUSIONS = ['/schemaVersion', '/id', '/version', '/encryption'] as const;

export interface SchemaCoverageReport {
  /** Node templates a registry entry matched (walk pruned there). */
  covered: string[];
  /** Schema leaf templates no registry entry covers — the gate's failures. */
  uncovered: string[];
  /** Registry templates matching nothing the schema can produce. */
  stale: string[];
  /** Nodes skipped by the exclusion list (envelope machinery). */
  excluded: string[];
  /** Leaves enumerated in total (a covered container counts as one leaf). */
  leafCount: number;
}

interface WalkContext {
  templates: { raw: PointerTemplate; segs: string[] }[];
  exclusions: string[][];
  /** Every node template visited, leaf or container (for staleness). */
  nodes: string[][];
  /** Node templates where a registry match pruned the walk. */
  pruned: string[][];
  covered: Set<string>;
  uncovered: Set<string>;
  excluded: Set<string>;
}

/**
 * Prune check at a node: exclusions first, then registry templates. Returns
 * true when the walk should stop here (the node is accounted for).
 */
function markResolved(path: string[], ctx: WalkContext): boolean {
  ctx.nodes.push(path);
  if (ctx.exclusions.some((e) => covers(e, path))) {
    ctx.pruned.push(path);
    ctx.excluded.add(buildPointer(path));
    return true;
  }
  if (ctx.templates.some((t) => covers(t.segs, path))) {
    ctx.pruned.push(path);
    ctx.covered.add(buildPointer(path));
    return true;
  }
  return false;
}

interface ChildRef {
  node: unknown;
  /** Path segment the child adds; undefined = same path (wrappers, unions). */
  seg?: string;
}

/**
 * Children of a zod def in walk order, or undefined for a LEAF (string,
 * number, boolean, literal, enum, unknown, any, date, …).
 */
function childrenOf(def: DefLike): ChildRef[] | undefined {
  switch (def.type) {
    case 'object': {
      const rawShape = def.shape;
      const shape = (typeof rawShape === 'function' ? rawShape() : rawShape) as Record<
        string,
        unknown
      >;
      return Object.entries(shape).map(([key, child]) => ({ node: child, seg: key }));
    }
    case 'record':
    case 'map':
      return [{ node: def.valueType, seg: '*' }];
    case 'array':
      return [{ node: def.element, seg: '*' }];
    case 'set':
      return [{ node: def.valueType, seg: '*' }];
    case 'tuple': {
      const items = ((def.items as unknown[] | undefined) ?? []).map((node) => ({
        node,
        seg: '*',
      }));
      return def.rest ? [...items, { node: def.rest, seg: '*' }] : items;
    }
    case 'union':
      return (def.options as unknown[]).map((node) => ({ node }));
    case 'intersection':
      return [{ node: def.left }, { node: def.right }];
    case 'optional':
    case 'nullable':
    case 'default':
    case 'prefault':
    case 'catch':
    case 'readonly':
    case 'nonoptional':
    case 'promise':
      return [{ node: def.innerType }];
    case 'lazy':
      return [{ node: (def.getter as () => unknown)() }];
    case 'pipe':
      // Coverage describes the stored document shape — walk the input side.
      return [{ node: def.in }];
    default:
      return undefined;
  }
}

function walkSchema(node: unknown, path: string[], ctx: WalkContext, stack: unknown[]): void {
  if (path.length > 0 && markResolved(path, ctx)) return;
  // Cycle guard for recursive (z.lazy) schemas: an uncovered cycle can never
  // enumerate finitely — surface the cycle point itself as the uncovered leaf.
  if (stack.includes(node)) {
    ctx.uncovered.add(buildPointer(path));
    return;
  }
  const children = childrenOf(defOf(node));
  if (children === undefined) {
    ctx.uncovered.add(buildPointer(path));
    return;
  }
  const next = [...stack, node];
  for (const child of children) {
    walkSchema(child.node, child.seg === undefined ? path : [...path, child.seg], ctx, next);
  }
}

export function computeSchemaCoverage(
  schema: z.ZodType,
  templates: readonly PointerTemplate[],
  exclusions: readonly PointerTemplate[] = ENVELOPE_EXCLUSIONS
): SchemaCoverageReport {
  const ctx: WalkContext = {
    templates: templates.map((raw) => ({ raw, segs: segments(raw) })),
    exclusions: exclusions.map(segments),
    nodes: [],
    pruned: [],
    covered: new Set(),
    uncovered: new Set(),
    excluded: new Set(),
  };
  walkSchema(schema, [], ctx, []);
  const stale = ctx.templates
    .filter(
      (t) =>
        !ctx.nodes.some((n) => matchesLeniently(t.segs, n)) &&
        !hasPrunedAncestor(t.segs, ctx.pruned)
    )
    .map((t) => t.raw);
  const covered = [...ctx.covered].sort();
  const uncovered = [...ctx.uncovered].sort();
  const excluded = [...ctx.excluded].sort();
  return { covered, uncovered, stale, excluded, leafCount: covered.length + uncovered.length };
}

/**
 * The pointer `coverageControlSchema()` plants. The gate asserts this fires as
 * UNCOVERED before trusting a green run — an instrument that cannot fire
 * proves nothing.
 */
export const COVERAGE_CONTROL_POINTER = '/__coverageControl';

/** The real config schema extended with one deliberately unregistered leaf. */
export function coverageControlSchema(): z.ZodType {
  return RdcConfigSchema.extend({ __coverageControl: z.string() });
}
