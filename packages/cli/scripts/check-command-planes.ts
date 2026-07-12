#!/usr/bin/env tsx
/**
 * Command-plane import-graph validator.
 *
 * A `plane` in COMMAND_METADATA is a claim about where a command runs, and the
 * web console and the proxy trust it: a machine-plane command is offered for
 * remote execution, a config-plane command is not. A wrong plane is therefore a
 * security-relevant mistake, and nothing about it is checked by the type system.
 *
 * This gate cross-checks those claims against the import graph. For each
 * top-level domain it walks the module tree from the domain's registering
 * module and asks whether the domain can reach a machine at all — the
 * machine-plane services (renet execute, SSH, SFTP, cloud provisioning).
 *
 *   Rule 1  A domain that cannot reach a machine must declare no machine-plane
 *           command. (The load-bearing rule: it catches a command claiming to
 *           be remote when its code provably never leaves the laptop.)
 *   Rule 2  A domain that can reach a machine must declare at least one
 *           machine-plane command, so a whole domain cannot be silently
 *           mislabelled config.
 *
 * The graph is module-granular, so a domain that merely touches a module which
 * *also* contains machine code reads as machine-touching. Where that coarseness
 * produces a false positive, the domain is listed in OVERRIDES with the reason.
 *
 * Usage:
 *   npx tsx packages/cli/scripts/check-command-planes.ts [--report]
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { cli } from '../src/cli.js';
import { getCommandPlane } from '../src/config/command-planes.js';
import {
  createDescriptionResolver,
  loadLocale,
  walkContractCommands,
} from './lib/command-tree-lib.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(__dirname, '../src');

/**
 * The module that registers each top-level domain, mirroring the imports in
 * src/cli.ts. A domain with no entry here fails the run: a new command family
 * must state where it is registered so its plane claims can be checked.
 */
const DOMAIN_MODULES: Record<string, string> = {
  cluster: 'commands/cluster/index.ts',
  config: 'commands/config.ts',
  credits: 'commands/credits.ts',
  datastore: 'commands/datastore.ts',
  doctor: 'commands/doctor.ts',
  job: 'commands/job.ts',
  machine: 'commands/machine/index.ts',
  mcp: 'commands/mcp/index.ts',
  ops: 'commands/ops/index.ts',
  repo: 'commands/repo.ts',
  serve: 'commands/serve.ts',
  storage: 'commands/storage.ts',
  subscription: 'commands/subscription.ts',
  term: 'commands/term.ts',
  update: 'commands/update.ts',
  vscode: 'commands/vscode.ts',
};

/** Reaching any of these means the code can talk to a customer machine. */
const MACHINE_MARKERS = [
  'services/executor/local-executor',
  'services/machine/',
  'remote/sftp',
  'remote/ssh',
  'services/tofu',
];

/**
 * Domains whose import-graph verdict is wrong because the graph is
 * module-granular. Each reason must say why the reachability is an artefact
 * rather than a real capability.
 *
 * Keep this list empty unless a domain genuinely cannot be classified from its
 * imports. Every entry here is a rule this gate stops enforcing.
 */
const OVERRIDES: Record<string, { expectMachineTouching: boolean; reason: string }> = {
  doctor: {
    expectMachineTouching: false,
    reason:
      'Graph says machine-touching via commands/doctor.ts -> services/account/license.ts -> ' +
      'remote/sftp. license.ts is one module holding two unrelated things: the account-server ' +
      'HTTPS license report (fetchSubscriptionLicenseReport, the only thing doctor calls) and ' +
      'the SFTP license-push that the subscription domain uses. Module granularity cannot split ' +
      'them, so doctor inherits an SFTP edge it never traverses. Drop this override if license.ts ' +
      'is ever split into an HTTPS half and an SSH half.',
  },
};

// ---------- Import graph ----------

const IMPORT_RE = /(?:from\s+|import\s*\(\s*)['"]([^'"]+)['"]/g;

/** Resolve a relative specifier (ESM .js) to a real .ts file under src/. */
function resolveSpecifier(fromFile: string, spec: string): string | null {
  if (!spec.startsWith('.')) return null;
  const base = path.resolve(path.dirname(fromFile), spec);
  const candidates = [
    base.replace(/\.js$/, '.ts'),
    base.replace(/\.js$/, '.tsx'),
    `${base}.ts`,
    path.join(base, 'index.ts'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate;
  }
  return null;
}

interface Reach {
  machineTouching: boolean;
  /** The import chain that first hit a marker, for the report. */
  via: string[];
}

function reachability(entry: string): Reach {
  const seen = new Set<string>();
  const queue: { file: string; chain: string[] }[] = [{ file: entry, chain: [] }];

  while (queue.length > 0) {
    const { file, chain } = queue.shift()!;
    if (seen.has(file)) continue;
    seen.add(file);

    const rel = path.relative(SRC, file).replace(/\\/g, '/');
    const nextChain = [...chain, rel];

    if (MACHINE_MARKERS.some((m) => rel.includes(m))) {
      return { machineTouching: true, via: nextChain };
    }

    const source = fs.readFileSync(file, 'utf-8');
    for (const match of source.matchAll(IMPORT_RE)) {
      const resolved = resolveSpecifier(file, match[1]);
      if (resolved && !seen.has(resolved)) queue.push({ file: resolved, chain: nextChain });
    }
  }

  return { machineTouching: false, via: [] };
}

// ---------- Check ----------

const report = process.argv.includes('--report');

const resolver = createDescriptionResolver(loadLocale('en'));
const commands = walkContractCommands(cli, resolver);

const byDomain = new Map<string, string[]>();
for (const cmd of commands) {
  const domain = cmd.path[0];
  const bucket = byDomain.get(domain) ?? [];
  bucket.push(cmd.pathKey);
  byDomain.set(domain, bucket);
}

const violations: string[] = [];

for (const [domain, paths] of [...byDomain].sort()) {
  const moduleRel = DOMAIN_MODULES[domain];
  if (!moduleRel) {
    violations.push(
      `Domain "${domain}" has no entry in DOMAIN_MODULES (check-command-planes.ts).\n` +
        '  Add the module that registers it, so its plane claims can be checked against the import graph.'
    );
    continue;
  }

  const entry = path.join(SRC, moduleRel);
  if (!fs.existsSync(entry)) {
    violations.push(`Domain "${domain}": DOMAIN_MODULES points at a missing file: ${moduleRel}`);
    continue;
  }

  const reach = reachability(entry);
  const override = OVERRIDES[domain];
  const machineTouching = override ? override.expectMachineTouching : reach.machineTouching;

  const machineLeaves = paths.filter((p) => getCommandPlane(p) === 'machine');

  if (report) {
    const flag = machineTouching ? 'machine-touching' : 'isolated';
    const note = override ? ' (OVERRIDE)' : '';
    console.log(
      `${domain.padEnd(13)} ${flag.padEnd(16)}${note.padEnd(12)} ${machineLeaves.length}/${paths.length} machine leaves`
    );
    if (reach.machineTouching && reach.via.length > 0) {
      console.log(`  via: ${reach.via.join(' -> ')}`);
    }
  }

  // Rule 1: an isolated domain cannot host a machine-plane command.
  if (!machineTouching && machineLeaves.length > 0) {
    violations.push(
      `Domain "${domain}" cannot reach a machine (no import path from ${moduleRel} to any of: ` +
        `${MACHINE_MARKERS.join(', ')}), but declares ${machineLeaves.length} machine-plane command(s):\n` +
        machineLeaves.map((p) => `    ${p}`).join('\n') +
        '\n  Either the plane in command-metadata.ts is wrong, or the command reaches a machine ' +
        'by a path this validator does not model.'
    );
  }

  // Rule 2: a domain that can reach a machine must own at least one.
  if (machineTouching && machineLeaves.length === 0) {
    violations.push(
      `Domain "${domain}" can reach a machine (${reach.via.join(' -> ')}), but declares no ` +
        'machine-plane command.\n  Either a command is mislabelled config/other in ' +
        'command-metadata.ts, or the reachability is an artefact of module granularity — in ' +
        'which case add an OVERRIDES entry in check-command-planes.ts explaining why.'
    );
  }
}

// Overrides must carry a real reason, and must not outlive their cause.
for (const [domain, override] of Object.entries(OVERRIDES)) {
  if (override.reason.trim().length < 30) {
    violations.push(`OVERRIDES["${domain}"] reason is too short — explain why the graph is wrong.`);
  }
  if (!byDomain.has(domain)) {
    violations.push(`OVERRIDES["${domain}"] is stale — no such domain in the command tree.`);
  }
}

if (violations.length > 0) {
  console.error('\x1b[31m✗ Command plane violations\x1b[0m\n');
  for (const v of violations) console.error(`  ${v}\n`);
  process.exit(1);
}

const machineCount = commands.filter((c) => getCommandPlane(c.pathKey) === 'machine').length;
const configCount = commands.filter((c) => getCommandPlane(c.pathKey) === 'config').length;
const otherCount = commands.filter((c) => getCommandPlane(c.pathKey) === 'other').length;

console.log(
  `\x1b[32m✓\x1b[0m Command planes agree with the import graph ` +
    `(${byDomain.size} domains, ${commands.length} commands: ` +
    `${machineCount} machine, ${configCount} config, ${otherCount} other)`
);
