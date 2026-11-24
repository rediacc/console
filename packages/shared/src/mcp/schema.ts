/**
 * The shape of the MCP tool registry document and its validator (PLAN-rmcp-local-mcp Design 1). Kept apart from registry.ts, which loads the generated file, so the generator can validate a document before the file exists.
 */
import { isMcpLayerErrorCode, type McpLayerErrorCode } from './errors.js';

/** Where a tool is served. Only `proxy` reaches the hosted Worker; `executor` and `in-memory` are verdicts that LM10 turns into `proxy`. */
type McpToolSurface = 'proxy' | 'executor' | 'in-memory' | 'local';

/** The two bases D57 admits for a `local` tool. */
type McpLocalBasis = 'caller-disk' | 'terminal';

interface McpToolAnnotations {
  destructiveHint: boolean;
  readOnlyHint: boolean;
  idempotentHint: boolean;
  openWorldHint: boolean;
}

export interface McpToolEntry {
  /** Tool name, e.g. "repo_up". Unique. */
  name: string;
  /** The contract pathKey the tool runs, e.g. "repo up". */
  command: string;
  description: string;
  /** JSON Schema of the tool arguments (an object schema). */
  inputSchema: Record<string, unknown>;
  annotations: McpToolAnnotations;
  surface: McpToolSurface;
  /** Present exactly when `surface` is `local`. */
  localBasis: McpLocalBasis | null;
  /** The written verdict; present exactly when `surface` is not `proxy`. */
  localReason: string | null;
  timeoutClass: 'read' | 'write';
  /** The tool may start a machine job and returns its id once the attach window passes. */
  attachWindow: boolean;
}

export interface McpRegistry {
  schema: 1;
  /** Sorted by name. */
  tools: McpToolEntry[];
  /** The CLI contract's error codes, sorted; a tool result passes these through from the `rdc` run. */
  contractErrorCodes: string[];
}

/** Every tool result code: an MCP-layer code or a contract code. */
export type McpErrorCode = McpLayerErrorCode | (string & {});

const SURFACES: ReadonlySet<string> = new Set(['proxy', 'executor', 'in-memory', 'local']);
const BASES: ReadonlySet<string> = new Set(['caller-disk', 'terminal']);
const ANNOTATION_KEYS = ['destructiveHint', 'readOnlyHint', 'idempotentHint', 'openWorldHint'] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function nonEmpty(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

/** The shape checks of one entry: strings, schema, annotations, timeout class, attach flag. */
function shapeProblems(raw: Record<string, unknown>, at: string): string[] {
  const problems: string[] = [];
  for (const key of ['name', 'command', 'description'] as const) {
    if (!nonEmpty(raw[key])) problems.push(`${at}.${key} is not a non-empty string`);
  }
  const schema = raw.inputSchema;
  if (!isRecord(schema) || schema.type !== 'object') {
    problems.push(`${at}.inputSchema is not an object schema`);
  }
  const ann = raw.annotations;
  if (!isRecord(ann) || ANNOTATION_KEYS.some((k) => typeof ann[k] !== 'boolean')) {
    problems.push(`${at}.annotations lacks one of ${ANNOTATION_KEYS.join(', ')}`);
  }
  if (raw.timeoutClass !== 'read' && raw.timeoutClass !== 'write') {
    problems.push(`${at}.timeoutClass is not read or write`);
  }
  if (typeof raw.attachWindow !== 'boolean') problems.push(`${at}.attachWindow is not a boolean`);
  return problems;
}

/** Is `basis` the right localBasis for `surface`: one of the two D57 bases on a local tool, null elsewhere? */
function basisFits(surface: unknown, basis: unknown): boolean {
  if (surface !== 'local') return basis === null;
  return typeof basis === 'string' && BASES.has(basis);
}

/** The surface checks of one entry: a known surface, a reason exactly off proxy, a basis exactly on local. */
function surfaceProblems(raw: Record<string, unknown>, at: string): string[] {
  const problems: string[] = [];
  const surface = raw.surface;
  if (typeof surface !== 'string' || !SURFACES.has(surface)) {
    problems.push(`${at}.surface ${JSON.stringify(surface)} is not a known surface`);
  }
  if (surface === 'proxy' && raw.localReason !== null) {
    problems.push(`${at} is proxy but carries a localReason`);
  }
  if (surface !== 'proxy' && !nonEmpty(raw.localReason)) {
    problems.push(`${at} is ${String(surface)} but has no localReason`);
  }
  if (!basisFits(surface, raw.localBasis)) {
    problems.push(
      `${at}.localBasis ${JSON.stringify(raw.localBasis)} does not fit surface ${String(surface)}`
    );
  }
  return problems;
}

function entryProblems(raw: unknown, index: number): string[] {
  const at = `tools[${index}]`;
  if (!isRecord(raw)) return [`${at} is not an object`];
  return [...shapeProblems(raw, at), ...surfaceProblems(raw, at)];
}

/** Order two strings by UTF-16 code units, the order the registry's tools and codes are sorted in. */
export function compareCodeUnits(a: string, b: string): number {
  if (a < b) return -1;
  return a > b ? 1 : 0;
}

/** The tool list checks: every entry, unique names, sorted by UTF-16 code units. */
function toolsProblems(tools: unknown): string[] {
  if (!Array.isArray(tools) || tools.length === 0) return ['tools is not a non-empty array'];
  const problems = tools.flatMap((entry, i) => entryProblems(entry, i));
  const names = tools.map((t) => String(isRecord(t) ? t.name : undefined));
  const seen = new Set<string>();
  names.forEach((name, i) => {
    if (seen.has(name)) problems.push(`tools[${i}].name ${name} is a duplicate`);
    seen.add(name);
    if (i > 0 && compareCodeUnits(names[i - 1], name) >= 0) {
      problems.push(`tools[${i}].name ${name} breaks the sort order`);
    }
  });
  return problems;
}

function codesProblems(codes: unknown): string[] {
  if (!Array.isArray(codes) || codes.some((c) => !nonEmpty(c))) {
    return ['contractErrorCodes is not an array of codes'];
  }
  if (codes.some((c: string) => isMcpLayerErrorCode(c))) {
    return ['contractErrorCodes repeats an MCP-layer code'];
  }
  return [];
}

/** Every structural problem of a registry document; empty when it is well-formed. */
export function mcpRegistryProblems(raw: unknown): string[] {
  if (!isRecord(raw)) return ['the registry is not an object'];
  const problems: string[] = [];
  if (raw.schema !== 1) problems.push(`schema ${JSON.stringify(raw.schema)} is not 1`);
  problems.push(...toolsProblems(raw.tools), ...codesProblems(raw.contractErrorCodes));
  return problems;
}

/** Parse a registry document, throwing with every problem when it is malformed. */
export function parseMcpRegistry(raw: unknown): McpRegistry {
  const problems = mcpRegistryProblems(raw);
  if (problems.length > 0) {
    throw new Error(`malformed MCP registry:\n  ${problems.join('\n  ')}`);
  }
  return raw as McpRegistry;
}
