#!/usr/bin/env tsx
/**
 * Command-plane import-graph validator.
 *
 * A `plane` in COMMAND_PLANES is a claim about where a command runs, and the web
 * console and the proxy trust it: a machine-plane command is offered for remote
 * execution, a config-plane command is not. A wrong plane is therefore a
 * security-relevant mistake, and nothing about it is checked by the type system.
 *
 * This gate cross-checks those claims against the import graph, at two
 * granularities.
 *
 * DOMAIN rules (the original gate). For each top-level domain, walk the module
 * tree from the domain's registering module and ask whether the domain can reach
 * a machine at all: the machine-plane services (renet execute, SSH, SFTP, cloud
 * provisioning).
 *
 *   Rule 1  A domain that cannot reach a machine must declare no machine-plane
 *           command.
 *   Rule 2  A domain that can reach a machine must declare at least one
 *           machine-plane command, so a whole domain cannot be silently
 *           mislabelled config.
 *
 * LEAF rule (Rule 3). The domain rules are blind to the single most likely
 * mistake this codebase makes, and it has already been made: a config-only leaf
 * RELOCATED into a machine-reaching noun silently inherits that noun's `machine`
 * default and becomes proxyCapable. Rule 1 does not fire (the noun really does
 * reach machines) and Rule 2 does not fire (the noun has dozens of other machine
 * leaves), so nothing anywhere says a word.
 *
 * That is not hypothetical. `repo admin archive {list,restore,purge}` is pure
 * config bookkeeping: it reads and writes the caller's archive map and imports
 * neither an executor nor SSH. It used to be `config repository *-archived`;
 * moving it under `repo` handed it repo's machine default, and a proxied
 * `archive purge` would therefore have permanently deleted the PROXY HOST's
 * archived records instead of the caller's. It was caught by a human noticing a
 * count had moved, which is not a control.
 *
 *   Rule 3  A leaf that claims plane `machine` must be registered by a module
 *           that can actually reach a machine. If the module that defines the
 *           leaf's action handler imports no machine seam, transitively, then
 *           the leaf provably cannot touch a machine and the claim is false.
 *
 * Rule 3 needs to know which module registers each leaf, and Commander does not
 * record that. So this gate patches `Command.prototype.command`/`.action` to
 * capture a stack at registration time BEFORE importing the CLI, and keeps the
 * innermost frame under src/, the module where the leaf's `.action(...)` is
 * written, which is exactly the module whose imports decide what the leaf can
 * reach. A leaf whose module cannot be attributed is a hard failure: an
 * unattributable leaf is one Rule 3 cannot judge, and silently not judging it is
 * how #51 happened in the first place.
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
import {
  createReachability,
  evaluateLeafPlanes,
  instrumentRegistration,
  leafModules,
  MACHINE_MARKERS,
  type Reach,
} from './lib/plane-rules.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(__dirname, '../src');

// Must patch Commander BEFORE the CLI module registers anything, so the imports
// below are dynamic on purpose: a static import would be hoisted above this call.
const registeredIn = instrumentRegistration(SRC);

const { cli } = await import('../src/cli.js');
const { getCommandPlane } = await import('../src/config/command-planes.js');
const { createDescriptionResolver, loadLocale, walkContractCommands } = await import(
  './lib/command-tree-lib.js'
);

/**
 * The module that registers each top-level domain, mirroring the imports in
 * src/cli.ts. A domain with no entry here fails the run: a new command family
 * must state where it is registered so its plane claims can be checked.
 */
const DOMAIN_MODULES = new Map<string, string>([
  ['backup', 'commands/backup.ts'],
  ['cluster', 'commands/cluster/index.ts'],
  ['config', 'commands/config.ts'],
  ['credits', 'commands/credits.ts'],
  ['datastore', 'commands/datastore.ts'],
  ['doctor', 'commands/doctor.ts'],
  ['job', 'commands/job.ts'],
  ['machine', 'commands/machine/index.ts'],
  ['mcp', 'commands/mcp/index.ts'],
  ['ops', 'commands/ops/index.ts'],
  ['repo', 'commands/repo.ts'],
  ['serve', 'commands/serve.ts'],
  ['storage', 'commands/storage.ts'],
  ['subscription', 'commands/subscription.ts'],
  ['term', 'commands/term.ts'],
  ['update', 'commands/update.ts'],
  ['vscode', 'commands/vscode.ts'],
]);

/**
 * Domains whose import-graph verdict is wrong because the graph is
 * module-granular. Each reason must say why the reachability is an artefact
 * rather than a real capability.
 *
 * Keep this list empty unless a domain genuinely cannot be classified from its
 * imports. Every entry here is a rule this gate stops enforcing.
 */
const OVERRIDES = new Map<string, { expectMachineTouching: boolean; reason: string }>([
  [
    'doctor',
    {
      expectMachineTouching: false,
      reason:
        'Graph says machine-touching via commands/doctor.ts -> services/account/license.ts -> ' +
        'remote/sftp. license.ts is one module holding two unrelated things: the account-server ' +
        'HTTPS license report (fetchSubscriptionLicenseReport, the only thing doctor calls) and ' +
        'the SFTP license-push that the subscription domain uses. Module granularity cannot split ' +
        'them, so doctor inherits an SFTP edge it never traverses. Drop this override if license.ts ' +
        'is ever split into an HTTPS half and an SSH half.',
    },
  ],
]);

// ---------- Check ----------

const reachOf = createReachability(SRC);
const reachability = (entry: string): Reach => reachOf(path.relative(SRC, entry));

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

/** Sort `[key, value]` entry pairs by key, ascending, by code unit. */
const byKey = <T>([a]: [string, T], [b]: [string, T]): number => (a < b ? -1 : a > b ? 1 : 0);

for (const [domain, paths] of [...byDomain].sort(byKey)) {
  const moduleRel = DOMAIN_MODULES.get(domain);
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
  const override = OVERRIDES.get(domain);
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
        'command-metadata.ts, or the reachability is an artefact of module granularity, in ' +
        'which case add an OVERRIDES entry in check-command-planes.ts explaining why.'
    );
  }
}

// ---------- Rule 3: per-leaf, the one the domain rules are blind to ----------

const modules = leafModules(cli, registeredIn);

violations.push(
  ...evaluateLeafPlanes(
    commands.map((cmd) => ({
      pathKey: cmd.pathKey,
      plane: getCommandPlane(cmd.pathKey),
      module: modules.get(cmd.pathKey) ?? null,
    })),
    reachOf
  )
);

/** module -> its leaves, for the report. */
const leavesByModule = new Map<string, string[]>();
for (const cmd of commands) {
  const moduleRel = modules.get(cmd.pathKey);
  if (!moduleRel) continue;
  const bucket = leavesByModule.get(moduleRel) ?? [];
  bucket.push(cmd.pathKey);
  leavesByModule.set(moduleRel, bucket);
}

if (report) {
  console.log('\n--- per-leaf (Rule 3): modules registering machine-plane leaves ---');
  for (const [moduleRel, paths] of [...leavesByModule].sort(byKey)) {
    const machineLeaves = paths.filter((p) => getCommandPlane(p) === 'machine');
    const flag = reachOf(moduleRel).machineTouching ? 'machine-touching' : 'isolated';
    console.log(
      `${moduleRel.padEnd(38)} ${flag.padEnd(16)} ${machineLeaves.length}/${paths.length} machine leaves`
    );
  }
}

// Overrides must carry a real reason, and must not outlive their cause.
for (const [domain, override] of OVERRIDES) {
  if (override.reason.trim().length < 30) {
    violations.push(`OVERRIDES["${domain}"] reason is too short. Explain why the graph is wrong.`);
  }
  if (!byDomain.has(domain)) {
    violations.push(`OVERRIDES["${domain}"] is stale: no such domain in the command tree.`);
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
