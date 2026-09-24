import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
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

function enclosingName(node: ts.Node): string {
  // A SourceFile's parent is undefined at runtime, whatever the declared type says.
  for (let cur: ts.Node | undefined = node.parent; cur; cur = cur.parent as ts.Node | undefined) {
    if ((ts.isFunctionDeclaration(cur) || ts.isMethodDeclaration(cur)) && cur.name !== undefined) {
      return cur.name.getText();
    }
    if (
      (ts.isArrowFunction(cur) || ts.isFunctionExpression(cur)) &&
      ts.isVariableDeclaration(cur.parent)
    ) {
      return cur.parent.name.getText();
    }
  }
  return '<module>';
}

function accessText(call: ts.CallExpression, where: number | { arg: number; property: string }) {
  const index = typeof where === 'number' ? where : where.arg;
  let arg: ts.Expression | undefined = call.arguments.at(index);
  if (arg !== undefined && typeof where !== 'number') {
    if (!ts.isObjectLiteralExpression(arg)) return '<missing>';
    const prop = arg.properties.find(
      (p): p is ts.PropertyAssignment =>
        ts.isPropertyAssignment(p) && p.name.getText() === where.property
    );
    arg = prop?.initializer;
  }
  if (arg === undefined) return '<missing>';
  if (ts.isStringLiteral(arg)) return arg.text;
  return '<forwarded>';
}

function calleeName(call: ts.CallExpression): string | null {
  const expr = call.expression;
  if (ts.isIdentifier(expr)) return expr.text;
  return null;
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
    const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true);
    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node)) {
        const name = calleeName(node);
        if (name !== null && name in ACCESS_CALLEES) {
          const key = `${rel}::${enclosingName(node)}::${name}`;
          (ledger[key] ??= []).push(accessText(node, ACCESS_CALLEES[name]));
        }
      }
      ts.forEachChild(node, visit);
    };
    visit(source);
  }
  return { ledger, provisionCallers };
}

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
