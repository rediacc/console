import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseSync, visitorKeys } from 'oxc-parser';
import type { Argument, CallExpression, Node, ObjectExpression } from 'oxc-parser';
import { describe, expect, it } from 'vitest';

/**
 * Ledger of every place the CLI resolves a renet binary on a machine, and the
 * access it declares (see `RenetAccess` in services/renet/renet-execution.ts).
 *
 * A read-only verb that provisions replaces the production binary and restarts
 * its router; that happened, from `rdc machine status`. The type system makes
 * the access argument mandatory; this ledger makes its VALUE deliberate. Any new
 * call, any changed access, and any call that disappears fails here until the
 * ledger is updated in the same change.
 */

const HERE = dirname(fileURLToPath(import.meta.url)); // packages/cli/src/__tests__
const CLI_SRC = join(HERE, '..'); // packages/cli/src

/** Callees that carry an access, and where the access sits in their arguments. */
const ACCESS_CALLEES: Record<string, number | { arg: number; property: string }> = {
  acquireRemoteRenet: 0,
  connectForJobs: 1,
  withJobConnection: 1,
  resolveMachineContext: 1,
  ensureRenetProvisioned: 1,
  prepareSyncConnection: { arg: 2, property: 'access' },
};

/** `file::enclosingFunction::callee` -> the declared access of each call, in source order. */
const LEDGER: Record<string, string[]> = {
  'commands/backup-ops.ts::runBackupNow::acquireRemoteRenet': ['provision'],
  'commands/job.ts::withJobConnection::connectForJobs': ['<forwarded>'],
  // `job list`, `job status`.
  'commands/job.ts::registerJobCommands::withJobConnection': ['read-only', 'read-only'],
  'commands/job.ts::runJobLogs::withJobConnection': ['read-only'],
  'commands/job.ts::runJobCancel::withJobConnection': ['provision'],
  'commands/job.ts::runJobGc::withJobConnection': ['provision'],
  'commands/machine/register.ts::registerSetup::acquireRemoteRenet': ['provision'],
  'commands/repo-sync.ts::ensureRenetProvisioned::acquireRemoteRenet': ['<forwarded>'],
  'commands/repo-sync.ts::prepareSyncConnection::ensureRenetProvisioned': ['<forwarded>'],
  'commands/repo-sync.ts::syncUpload::prepareSyncConnection': ['provision'],
  // Also `sync status` (a dry-run download).
  'commands/repo-sync.ts::syncDownload::prepareSyncConnection': ['read-only'],
  'commands/repo-tunnel.ts::tunnelConnect::acquireRemoteRenet': ['read-only'],
  'commands/subscription-actions.ts::resolveMachineContext::acquireRemoteRenet': ['<forwarded>'],
  'commands/subscription-actions.ts::resolveSubscriptionCommandContext::resolveMachineContext': [
    'provision',
  ],
  'commands/subscription-actions.ts::executeMachineStatus::resolveMachineContext': ['read-only'],
  'commands/term.ts::connectTerminal::acquireRemoteRenet': ['read-only'],
  'commands/vscode-browser.ts::prepareBrowserConnection::acquireRemoteRenet': ['read-only'],
  'commands/vscode.ts::prepareRemote::acquireRemoteRenet': ['read-only'],
  'services/backup/backup-schedule.ts::preDeployProvisioning::acquireRemoteRenet': ['provision'],
  'services/executor/job-remote.ts::connectForJobs::acquireRemoteRenet': ['<forwarded>'],
  // Forwarded from renetAccessFor(functionName): RENET_FUNCTION_ACCESS decides, pinned by renet-function-access.test.ts.
  'services/executor/local-executor.ts::provisionFn::acquireRemoteRenet': ['<forwarded>'],
  'services/machine/machine-status.ts::fetchMachineStatus::acquireRemoteRenet': ['read-only'],
  'services/machine/machine-status.ts::fetchRepoLicenseDetail::acquireRemoteRenet': ['read-only'],
  'services/provision/infra-provision.ts::pushInfraConfig::acquireRemoteRenet': ['provision'],
  'services/renet/machine-bootstrap.ts::bootstrapMachine::acquireRemoteRenet': ['provision'],
  'services/serve/server.ts::createServeApp::connectForJobs': ['read-only'],
};

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === '__tests__' || entry === 'node_modules') continue;
      walk(full, out);
    } else if (entry.endsWith('.ts') && !entry.endsWith('.d.ts') && !entry.endsWith('.test.ts')) {
      out.push(full);
    }
  }
  return out;
}

/**
 * oxc/ESTree has no single `parent` link (unlike the TS compiler API's
 * `setParentNodes`), so the AST walk below builds the ancestor chain itself
 * and `enclosingName` reads it back to front -- `ancestors.at(-1)` is the
 * immediate parent, exactly what `node.parent` was in the TS version.
 *
 * `.getText()` doesn't exist either: it always returned the literal source
 * slice of a name node, which `source.slice(start, end)` reproduces exactly,
 * without needing to special-case an Identifier vs. a destructuring pattern.
 *
 * `nameFromAncestor` is the declared name of a single ancestor, if it's one
 * of the containers `enclosingName` recognizes: a named function declaration,
 * a class method (`MethodDefinition`), an object-literal method (`Property`
 * with `method: true` -- there is no separate node type for it in ESTree,
 * unlike the TS compiler API where both are `MethodDeclaration`), or a
 * function expression assigned to a variable. `undefined` means "keep
 * walking outward".
 */
function nameFromAncestor(cur: Node, parent: Node | undefined, source: string): string | undefined {
  if (cur.type === 'FunctionDeclaration' && cur.id != null) {
    return source.slice(cur.id.start, cur.id.end);
  }
  if (cur.type === 'MethodDefinition') {
    return source.slice(cur.key.start, cur.key.end);
  }
  if (cur.type === 'Property' && cur.method) {
    return source.slice(cur.key.start, cur.key.end);
  }
  if (
    (cur.type === 'ArrowFunctionExpression' || cur.type === 'FunctionExpression') &&
    parent?.type === 'VariableDeclarator'
  ) {
    return source.slice(parent.id.start, parent.id.end);
  }
  return undefined;
}

function enclosingName(ancestors: Node[], source: string): string {
  for (let i = ancestors.length - 1; i >= 0; i--) {
    const name = nameFromAncestor(ancestors[i], ancestors[i - 1], source);
    if (name !== undefined) return name;
  }
  return '<module>';
}

/** A plain `key: value` property (ESLint/TS call it `PropertyAssignment`): not shorthand, not computed, not a method. */
function propertyKeyText(property: ObjectExpression['properties'][number]): string | null {
  if (property.type !== 'Property' || property.computed || property.shorthand || property.method) {
    return null;
  }
  if (property.key.type === 'Identifier') return property.key.name;
  if (property.key.type === 'Literal' && typeof property.key.value === 'string') {
    return property.key.value;
  }
  return null;
}

/** The value of a named property on an object-expression argument, or `undefined` if it isn't a plain property. */
function resolvePropertyArg(arg: Argument, property: string): Argument | undefined {
  if (arg.type !== 'ObjectExpression') return undefined;
  const prop = arg.properties.find((p) => propertyKeyText(p) === property);
  return prop?.type === 'Property' ? prop.value : undefined;
}

function accessText(call: CallExpression, where: number | { arg: number; property: string }) {
  const index = typeof where === 'number' ? where : where.arg;
  let arg = call.arguments.at(index);
  if (arg !== undefined && typeof where !== 'number') {
    arg = resolvePropertyArg(arg, where.property);
  }
  if (arg === undefined) return '<missing>';
  if (arg.type === 'Literal' && typeof arg.value === 'string') return arg.value;
  return '<forwarded>';
}

function calleeName(call: CallExpression): string | null {
  const expr = call.callee;
  if (expr.type === 'Identifier') return expr.name;
  return null;
}

/**
 * Generic ESTree walk driven by oxc's own `visitorKeys`, tracking the
 * ancestor stack `enclosingName` reads. `onCall` fires for every
 * `CallExpression`, before that call is itself pushed onto `ancestors` --
 * `ancestors` therefore holds exactly the call's proper ancestors, oldest
 * first, matching the TS version's `node.parent` chain.
 */
function walkAst(
  node: unknown,
  ancestors: Node[],
  onCall: (call: CallExpression, ancestors: Node[]) => void
): void {
  if (node === null || typeof node !== 'object' || !('type' in node)) return;
  const current = node as Node;
  if (current.type === 'CallExpression') onCall(current, ancestors);
  ancestors.push(current);
  const keys = visitorKeys[current.type] ?? [];
  const record = current as unknown as Record<string, unknown>;
  for (const key of keys) {
    const child = record[key];
    if (Array.isArray(child)) {
      for (const c of child) walkAst(c, ancestors, onCall);
    } else {
      walkAst(child, ancestors, onCall);
    }
  }
  ancestors.pop();
}

interface Scan {
  ledger: Record<string, string[]>;
  provisionCallers: string[];
}

function scan(): Scan {
  const ledger: Record<string, string[]> = {};
  const provisionCallers: string[] = [];
  for (const file of walk(CLI_SRC)) {
    const rel = relative(CLI_SRC, file).replaceAll('\\', '/');
    const text = readFileSync(file, 'utf-8');
    if (text.includes('renetProvisioner.provision(')) provisionCallers.push(rel);
    if (!Object.keys(ACCESS_CALLEES).some((name) => text.includes(name))) continue;
    const { program } = parseSync(file, text, { sourceType: 'module' });
    walkAst(program, [], (call, ancestors) => {
      const name = calleeName(call);
      if (name !== null && name in ACCESS_CALLEES) {
        const key = `${rel}::${enclosingName(ancestors, text)}::${name}`;
        (ledger[key] ??= []).push(accessText(call, ACCESS_CALLEES[name]));
      }
    });
  }
  return { ledger, provisionCallers };
}

/** The `enclosingName` of the first call expression found in a parsed source snippet. */
function enclosingNameOfFirstCall(source: string): string {
  const { program } = parseSync('fixture.ts', source, { sourceType: 'module' });
  let found: string | undefined;
  walkAst(program, [], (_call, ancestors) => {
    found ??= enclosingName(ancestors, source);
  });
  if (found === undefined) throw new Error('fixture has no call expression');
  return found;
}

describe('enclosingName', () => {
  it('resolves a call inside an object-literal method to the method, not an outer name', () => {
    const source = `
      const handlers = {
        outer() {
          return {
            innerMethod() {
              return doSomething();
            },
          };
        },
      };
    `;
    expect(enclosingNameOfFirstCall(source)).toBe('innerMethod');
  });
});

describe('renet access ledger', () => {
  const { ledger, provisionCallers } = scan();

  it('every access-bearing call site declares the access the ledger records', () => {
    expect(ledger).toEqual(LEDGER);
  });

  it('no access is ever left to a missing argument', () => {
    const missing = Object.entries(ledger).filter(([, accesses]) => accesses.includes('<missing>'));
    expect(missing).toEqual([]);
  });

  it('only the entry point calls renetProvisioner.provision', () => {
    expect(provisionCallers).toEqual(['services/renet/renet-execution.ts']);
  });

  it('backup status resolves no renet binary at all', () => {
    const keys = Object.keys(ledger).filter((key) => key.includes('::showBackupStatus::'));
    expect(keys).toEqual([]);
  });
});
