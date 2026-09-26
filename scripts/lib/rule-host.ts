/**
 * A small, ESLint-shaped runtime for the `eslint-rules/` modules, without ESLint.
 *
 * WHY THIS EXISTS. PLAN-biome-only-lint.md finding #4: none of the 30 enabled
 * `custom`/`i18n`/`i18n-source` rules use `parserServices` (type information),
 * esquery selectors or `:exit` handlers. Two use a scope API
 * (`require-translation.js`, `i18n/interpolation-match.js`) and one uses
 * `getAncestors` (`no-unawaited-drizzle-terminator.js`). Every rule is a plain
 * `Type(node)` or `Document(node)` visitor. That is a small enough surface to
 * run the SAME rule modules unchanged against two already-pinned parsers
 * (`oxc-parser` for JS/TS/JSX, `@humanwhocodes/momoa` for JSON) instead of
 * against ESLint.
 *
 * TWO ENGINES, ONE SHAPE. `runSourceRule` walks an oxc ESTree/TS-ESTree AST and
 * dispatches `Type(node)` visitors. `runJsonRule` parses with momoa and calls a
 * rule's `Document(node)` visitor once (every JSON rule here does its own
 * recursive descent through its own `objectMembers` helper in eslint-rules/, so nothing else
 * needs dispatching).
 * Both hand the rule the same `context` shape: `{ options, filename,
 * physicalFilename, cwd, sourceCode, report }`.
 *
 * WHY TWO PASSES FOR SOURCE FILES. `.parent` and the scope map are built in one
 * full traversal (`buildParentsAndScopes`) BEFORE any rule listener runs
 * (`dispatchVisitors`). A single combined pass would make `getScope`/`.parent`
 * correct only for code written in the "declare, then use" order the probes
 * happen to follow; a hoisted function or a forward reference would see a scope
 * still being built. ESLint's own architecture separates scope analysis from
 * rule traversal for the same reason, so this mirrors it instead of guessing.
 *
 * WHAT THE SCOPE SHIM DELIBERATELY DOES NOT COVER: hoisting subtleties, TDZ,
 * `with`, labeled statements as scopes, or module import bindings. The two rules
 * that read `sourceCode.getScope()` need `scope.block`, `scope.variables[].defs[].node`
 * and `scope.upper` for Program, function, non-function-body block, for, switch,
 * catch and class scopes -- exactly what is implemented below, per finding #4.
 */

import path from 'node:path';

import type {
  DocumentNode,
  Node as MomoaNode,
} from '@humanwhocodes/momoa';
import { parse as momoaParse } from '@humanwhocodes/momoa';
import { parseSync, visitorKeys as jsVisitorKeys } from 'oxc-parser';

// `.tsx` parses as `tsx`, plain `.ts`/`.mts`/`.cts` as `ts` -- forcing every `.ts` file into the `tsx` grammar breaks the OLD-STYLE generic cast (`<T>value`) and generic-arrow ambiguity that grammar exists to resolve in favour of JSX, and real `.ts` sources in this repo use that syntax. Plain JS family files (`.js`/`.jsx`/`.mjs`/`.cjs`) always parse as `jsx` instead: the real config enables JSX (`ecmaFeatures.jsx: true`) for every js, jsx, ts and tsx source path it lints (`eslint.config/typescript.js`'s react-plugin block), including plain `.js` files under `eslint-rules` -- so `custom/require-testid`'s own probe file is plain `.js` with a JSX literal in it, and JS has no cast-vs-JSX ambiguity for that option to break.
function langFor(filename: string): 'jsx' | 'ts' | 'tsx' {
  const ext = path.extname(filename);
  if (ext === '.tsx') return 'tsx';
  if (ext === '.ts' || ext === '.mts' || ext === '.cts') return 'ts';
  return 'jsx';
}

/** The minimal shape every AST node this host touches has in common. */
export interface AnyNode {
  type: string;
  parent?: AnyNode;
  range?: [number, number];
  loc?: { start: { line: number; column: number }; end: { line: number; column: number } };
  [key: string]: unknown;
}

export interface HostVariable {
  name: string;
  defs: Array<{ node: AnyNode }>;
}

export interface HostScope {
  type: string;
  block: AnyNode;
  variables: HostVariable[];
  upper: HostScope | null;
}

export interface ReportDescriptor {
  node: AnyNode;
  messageId?: string;
  message?: string;
  data?: Record<string, unknown>;
  fix?: (fixer: RuleFixer) => FixResult | FixResult[] | null;
}

export interface FixResult {
  range: [number, number];
  text: string;
}

export interface RuleFixer {
  insertTextAfter(node: AnyNode, text: string): FixResult;
  insertTextAfterRange(range: [number, number], text: string): FixResult;
  insertTextBefore(node: AnyNode, text: string): FixResult;
  insertTextBeforeRange(range: [number, number], text: string): FixResult;
  remove(node: AnyNode): FixResult;
  removeRange(range: [number, number]): FixResult;
  replaceText(node: AnyNode, text: string): FixResult;
  replaceTextRange(range: [number, number], text: string): FixResult;
}

export interface HostSourceCode {
  text: string;
  getText(node?: AnyNode): string;
  getAncestors(node: AnyNode): AnyNode[];
  getScope(node: AnyNode): HostScope | null;
}

export interface HostContext {
  options: unknown[];
  filename: string;
  physicalFilename: string;
  cwd: string;
  sourceCode: HostSourceCode;
  report(descriptor: ReportDescriptor): void;
}

export interface RuleMeta {
  messages?: Record<string, string>;
  schema?: unknown;
  fixable?: string;
}

export interface RuleModule {
  meta?: RuleMeta;
  create(context: HostContext): Record<string, (node: AnyNode) => void>;
}

export interface Finding {
  messageId?: string;
  message: string;
  line: number;
  column: number;
  endLine: number;
  endColumn: number;
  nodeType: string;
  fixes: FixResult[];
}

export interface RunOptions {
  filename: string;
  cwd?: string;
  options?: unknown[];
}

/** `{{key}}` interpolation, matching ESLint's own template substitution. Exported so the host-backed rule tester can hydrate an EXPECTED message from a spec's `{ messageId, data }` the same way a real finding's message was built, rather than re-deriving the rule. */
export function interpolate(template: string, data: Record<string, unknown>): string {
  return template.replace(/\{\{\s*(\w+)\s*\}\}/g, (whole, key: string) =>
    Object.prototype.hasOwnProperty.call(data, key) ? String(data[key]) : whole
  );
}

function computeLineStarts(source: string): number[] {
  const starts = [0];
  for (let i = 0; i < source.length; i++) {
    if (source[i] === '\n') starts.push(i + 1);
  }
  return starts;
}

/** 1-based (line, column), matching ESLint's own message.line/message.column. */
function lineColAtOffset(lineStarts: number[], offset: number): { line: number; column: number } {
  let lo = 0;
  let hi = lineStarts.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (lineStarts[mid] <= offset) lo = mid;
    else hi = mid - 1;
  }
  return { line: lo + 1, column: offset - lineStarts[lo] + 1 };
}

/** momoa nodes already carry a 1-based `loc` (verified against `@eslint/json`'s own output: identical line/column, no adjustment). oxc nodes carry only byte offsets. */
function locate(
  node: AnyNode,
  lineStarts: number[] | null
): { start: { line: number; column: number }; end: { line: number; column: number } } {
  if (node.loc) return node.loc;
  if (lineStarts && node.range) {
    return {
      start: lineColAtOffset(lineStarts, node.range[0]),
      end: lineColAtOffset(lineStarts, node.range[1]),
    };
  }
  throw new Error(`rule-host: node "${node.type}" has neither .loc nor .range`);
}

function makeFixer(): RuleFixer {
  const rangeOf = (node: AnyNode): [number, number] => {
    if (!node.range) throw new Error(`rule-host: fixer needs .range on "${node.type}"`);
    return node.range;
  };
  return {
    insertTextAfter: (node, text) => ({ range: [rangeOf(node)[1], rangeOf(node)[1]], text }),
    insertTextAfterRange: (range, text) => ({ range: [range[1], range[1]], text }),
    insertTextBefore: (node, text) => ({ range: [rangeOf(node)[0], rangeOf(node)[0]], text }),
    insertTextBeforeRange: (range, text) => ({ range: [range[0], range[0]], text }),
    remove: (node) => ({ range: rangeOf(node), text: '' }),
    removeRange: (range) => ({ range, text: '' }),
    replaceText: (node, text) => ({ range: rangeOf(node), text }),
    replaceTextRange: (range, text) => ({ range, text }),
  };
}

function collectPatternNames(pattern: AnyNode | null | undefined, out: string[]): void {
  if (!pattern) return;
  switch (pattern.type) {
    case 'Identifier':
      out.push(pattern.name as string);
      return;
    case 'ObjectPattern':
      for (const prop of (pattern.properties as AnyNode[]) ?? []) {
        collectPatternNames((prop.argument ?? prop.value) as AnyNode, out);
      }
      return;
    case 'ArrayPattern':
      for (const el of (pattern.elements as Array<AnyNode | null>) ?? [])
        collectPatternNames(el, out);
      return;
    case 'AssignmentPattern':
      collectPatternNames(pattern.left as AnyNode, out);
      return;
    case 'RestElement':
      collectPatternNames(pattern.argument as AnyNode, out);
      return;
    default:
      return;
  }
}

const FUNCTION_TYPES = new Set([
  'FunctionDeclaration',
  'FunctionExpression',
  'ArrowFunctionExpression',
]);
const OWN_SCOPE_TYPES = new Set([
  'ForStatement',
  'ForInStatement',
  'ForOfStatement',
  'SwitchStatement',
  'CatchClause',
  'ClassDeclaration',
  'ClassExpression',
]);

function isFunctionBody(node: AnyNode, parent: AnyNode | undefined): boolean {
  return !!parent && FUNCTION_TYPES.has(parent.type) && parent.body === node;
}

function declarationTargetScope(kind: string | undefined, innermost: HostScope): HostScope {
  if (kind !== 'var') return innermost;
  let scope: HostScope | null = innermost;
  while (scope && scope.type !== 'module' && scope.type !== 'function') scope = scope.upper;
  return scope ?? innermost;
}

/** Full-tree walk: sets `.parent` everywhere and builds every scope, before any rule listener runs. */
function buildParentsAndScopes(
  node: AnyNode | null | undefined,
  parent: AnyNode | undefined,
  scope: HostScope,
  nodeScope: Map<AnyNode, HostScope>,
  visitorKeys: Record<string, string[]>
): void {
  if (!node || typeof node !== 'object' || typeof node.type !== 'string') return;
  node.parent = parent;

  let childScope = scope;
  if (FUNCTION_TYPES.has(node.type)) {
    childScope = { type: 'function', block: node, variables: [], upper: scope };
    nodeScope.set(node, childScope);
    const names: string[] = [];
    for (const p of (node.params as AnyNode[]) ?? []) collectPatternNames(p, names);
    for (const name of names) childScope.variables.push({ name, defs: [{ node }] });
  } else if (
    node.type === 'BlockStatement' &&
    !isFunctionBody(node, parent) &&
    parent?.type !== 'CatchClause'
  ) {
    childScope = { type: 'block', block: node, variables: [], upper: scope };
    nodeScope.set(node, childScope);
  } else if (OWN_SCOPE_TYPES.has(node.type)) {
    childScope = { type: node.type, block: node, variables: [], upper: scope };
    nodeScope.set(node, childScope);
    if (node.type === 'CatchClause' && node.param) {
      const names: string[] = [];
      collectPatternNames(node.param as AnyNode, names);
      for (const name of names) childScope.variables.push({ name, defs: [{ node }] });
    }
  }

  if (node.type === 'VariableDeclarator') {
    const names: string[] = [];
    collectPatternNames(node.id as AnyNode, names);
    const kind = parent?.type === 'VariableDeclaration' ? (parent.kind as string) : 'let';
    const target = declarationTargetScope(kind, scope);
    for (const name of names) target.variables.push({ name, defs: [{ node }] });
  }

  for (const key of visitorKeys[node.type] ?? []) {
    const value = node[key];
    if (Array.isArray(value)) {
      for (const child of value as AnyNode[])
        buildParentsAndScopes(child, node, childScope, nodeScope, visitorKeys);
    } else if (value && typeof (value as AnyNode).type === 'string') {
      buildParentsAndScopes(value as AnyNode, node, childScope, nodeScope, visitorKeys);
    }
  }
}

function dispatchVisitors(
  node: AnyNode | null | undefined,
  visitors: Record<string, (n: AnyNode) => void>,
  visitorKeys: Record<string, string[]>
): void {
  if (!node || typeof node !== 'object' || typeof node.type !== 'string') return;
  visitors[node.type]?.(node);
  for (const key of visitorKeys[node.type] ?? []) {
    const value = node[key];
    if (Array.isArray(value)) {
      for (const child of value as AnyNode[]) dispatchVisitors(child, visitors, visitorKeys);
    } else if (value && typeof (value as AnyNode).type === 'string') {
      dispatchVisitors(value as AnyNode, visitors, visitorKeys);
    }
  }
}

/** Program root, module scope and the built parent/scope map for `code` under `filename`. */
export function parseSource(
  code: string,
  filename: string
): { program: AnyNode; nodeScope: Map<AnyNode, HostScope> } {
  const result = parseSync(filename, code, { range: true, lang: langFor(filename) });
  if (result.errors.some((e) => e.severity === 'Error')) {
    const first = result.errors.find((e) => e.severity === 'Error');
    throw new Error(`rule-host: parse error in ${filename}: ${first?.message}`);
  }
  const program = result.program as unknown as AnyNode;
  const nodeScope = new Map<AnyNode, HostScope>();
  const moduleScope: HostScope = { type: 'module', block: program, variables: [], upper: null };
  nodeScope.set(program, moduleScope);
  const keys = jsVisitorKeys as unknown as Record<string, string[]>;
  for (const key of keys.Program ?? ['body']) {
    const value = program[key];
    if (Array.isArray(value)) {
      for (const child of value as AnyNode[])
        buildParentsAndScopes(child, program, moduleScope, nodeScope, keys);
    }
  }
  return { program, nodeScope };
}

function buildSourceCode(text: string, nodeScope: Map<AnyNode, HostScope>): HostSourceCode {
  return {
    text,
    getText: (node) => (node?.range ? text.slice(node.range[0], node.range[1]) : text),
    getAncestors: (node) => {
      const ancestors: AnyNode[] = [];
      let current = node.parent;
      while (current) {
        ancestors.unshift(current);
        current = current.parent;
      }
      return ancestors;
    },
    getScope: (node) => {
      let current: AnyNode | undefined = node;
      while (current) {
        const found = nodeScope.get(current);
        if (found) return found;
        current = current.parent;
      }
      return null;
    },
  };
}

/** Run one rule's `Type(node)` visitors over JS/TS/JSX source. */
export function runSourceRule(rule: RuleModule, code: string, run: RunOptions): Finding[] {
  const { program, nodeScope } = parseSource(code, run.filename);
  const lineStarts = computeLineStarts(code);
  const sourceCode = buildSourceCode(code, nodeScope);
  const findings: Finding[] = [];
  const context: HostContext = {
    options: run.options ?? [],
    filename: run.filename,
    physicalFilename: run.filename,
    cwd: run.cwd ?? process.cwd(),
    sourceCode,
    report(descriptor) {
      findings.push(toFinding(rule, descriptor, lineStarts));
    },
  };
  const visitors = rule.create(context);
  const keys = jsVisitorKeys as unknown as Record<string, string[]>;
  dispatchVisitors(program, visitors, keys);
  return findings;
}

/** Run one rule's `Document(node)` visitor over a JSON source. */
export function runJsonRule(rule: RuleModule, code: string, run: RunOptions): Finding[] {
  const document = momoaParse(code, { mode: 'json', ranges: true }) as unknown as DocumentNode &
    AnyNode;
  const findings: Finding[] = [];
  const context: HostContext = {
    options: run.options ?? [],
    filename: run.filename,
    physicalFilename: run.filename,
    cwd: run.cwd ?? process.cwd(),
    sourceCode: {
      text: code,
      getText: (node) => {
        const target = (node ?? document) as unknown as { range?: [number, number] };
        return target.range ? code.slice(target.range[0], target.range[1]) : code;
      },
      getAncestors: () => [],
      getScope: () => null,
    },
    report(descriptor) {
      findings.push(toFinding(rule, descriptor, null));
    },
  };
  const visitors = rule.create(context);
  visitors.Document?.(document as unknown as AnyNode);
  return findings;
}

function toFinding(
  rule: RuleModule,
  descriptor: ReportDescriptor,
  lineStarts: number[] | null
): Finding {
  const data = descriptor.data ?? {};
  const template = descriptor.messageId
    ? rule.meta?.messages?.[descriptor.messageId]
    : descriptor.message;
  if (!template) {
    throw new Error(
      `rule-host: report() with messageId "${String(descriptor.messageId)}" has no meta.messages entry`
    );
  }
  const loc = locate(descriptor.node, lineStarts);
  const fixer = makeFixer();
  const rawFix = descriptor.fix?.(fixer);
  const fixes = rawFix ? (Array.isArray(rawFix) ? rawFix : [rawFix]) : [];
  return {
    messageId: descriptor.messageId,
    message: interpolate(template, data),
    line: loc.start.line,
    column: loc.start.column,
    endLine: loc.end.line,
    endColumn: loc.end.column,
    nodeType: descriptor.node.type,
    fixes,
  };
}
