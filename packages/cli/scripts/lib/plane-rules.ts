/**
 * The per-leaf plane rule (Rule 3), extracted so a test can drive it in BOTH
 * directions: green on the real tree, and red on a leaf deliberately mis-planed.
 *
 * A rule that has only ever been observed to pass is not a control. Bug #51
 * (`repo admin archive {list,restore,purge}` claiming plane `machine` after being
 * relocated into the `repo` noun, which made a proxied `archive purge` delete the
 * PROXY HOST's archived records) sat under a green gate precisely because the
 * gate could not fail for that reason.
 *
 * See check-command-planes.ts for the full rationale.
 */
import fs from 'node:fs';
import path from 'node:path';
import { Command } from 'commander';

/** Reaching any of these means the code can talk to a customer machine. */
export const MACHINE_MARKERS = [
  'services/executor/local-executor',
  'services/machine/',
  'remote/sftp',
  'remote/ssh',
  'services/tofu',
];

export interface Reach {
  machineTouching: boolean;
  /** The import chain that first hit a marker, for the report. */
  via: string[];
}

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

/** Breadth-first walk of the import graph from `entry`, looking for a machine seam. */
export function createReachability(src: string): (moduleRel: string) => Reach {
  const cache = new Map<string, Reach>();

  return (moduleRel: string): Reach => {
    const cached = cache.get(moduleRel);
    if (cached) return cached;

    const seen = new Set<string>();
    const queue: { file: string; chain: string[] }[] = [
      { file: path.join(src, moduleRel), chain: [] },
    ];
    let result: Reach = { machineTouching: false, via: [] };

    while (queue.length > 0) {
      const { file, chain } = queue.shift()!;
      if (seen.has(file)) continue;
      seen.add(file);
      if (!fs.existsSync(file)) continue;

      const rel = path.relative(src, file).replace(/\\/g, '/');
      const nextChain = [...chain, rel];

      if (MACHINE_MARKERS.some((marker) => rel.includes(marker))) {
        result = { machineTouching: true, via: nextChain };
        break;
      }

      for (const match of fs.readFileSync(file, 'utf-8').matchAll(IMPORT_RE)) {
        const resolved = resolveSpecifier(file, match[1]);
        if (resolved && !seen.has(resolved)) queue.push({ file: resolved, chain: nextChain });
      }
    }

    cache.set(moduleRel, result);
    return result;
  };
}

// ---------- Leaf -> registering module ----------

/**
 * Commander does not record where a command was registered, so capture it: the
 * innermost stack frame under src/ at `.action(fn)` time is the module where the
 * handler is written, and that module's imports are exactly what the leaf can reach.
 *
 * MUST be called before the CLI module is imported, or the registrations have
 * already happened and nothing is captured.
 */
export function instrumentRegistration(src: string): Map<Command, string> {
  const registeredIn = new Map<Command, string>();

  const innermostSrcFrame = (): string | null => {
    for (const line of (new Error().stack ?? '').split('\n').slice(1)) {
      const match = line.match(/\(?((?:\/|file:\/\/)[^):]+\.tsx?)[:)]/);
      if (!match) continue;
      const file = match[1].replace(/^file:\/\//, '');
      if (!file.startsWith(src)) continue;
      return path.relative(src, file).replace(/\\/g, '/');
    }
    return null;
  };

  type CommanderMethod = (...args: unknown[]) => unknown;
  const proto = Command.prototype as unknown as Record<string, CommanderMethod>;

  const originalAction = proto.action;
  proto.action = function patchedAction(this: Command, ...args: unknown[]) {
    // `.action()` is the strongest signal (it is where the handler is defined),
    // so it overwrites a weaker `.command()` attribution for the same object.
    const frame = innermostSrcFrame();
    if (frame) registeredIn.set(this, frame);
    return originalAction.apply(this, args);
  };

  const originalCommand = proto.command;
  proto.command = function patchedCommand(this: Command, ...args: unknown[]) {
    const frame = innermostSrcFrame();
    const created = originalCommand.apply(this, args);
    if (frame && created instanceof Command && !registeredIn.has(created)) {
      registeredIn.set(created, frame);
    }
    return created;
  };

  return registeredIn;
}

/** pathKey -> registering module, for every command object in the live tree. */
export function leafModules(root: Command, registeredIn: Map<Command, string>) {
  const map = new Map<string, string | null>();
  const visit = (cmd: Command, prefix: string[]): void => {
    if (cmd.name() === 'help') return;
    const commandPath = [...prefix, cmd.name()];
    map.set(commandPath.join(' '), registeredIn.get(cmd) ?? null);
    for (const sub of cmd.commands) visit(sub, commandPath);
  };
  for (const cmd of root.commands) visit(cmd, []);
  return map;
}

// ---------- Rule 3 ----------

export interface LeafPlaneClaim {
  pathKey: string;
  /** The plane the command DECLARES (via COMMAND_PLANES ancestor inheritance). */
  plane: string;
  /** The module whose `.action(...)` defines this leaf, or null if unattributable. */
  module: string | null;
}

/**
 * Rule 3: a leaf claiming plane `machine` must be registered by a module that can
 * actually reach a machine.
 *
 * An unattributable leaf is a HARD failure, not a skip: a leaf this rule cannot
 * judge is exactly the leaf #51 hid in.
 */
export function evaluateLeafPlanes(
  claims: LeafPlaneClaim[],
  reach: (moduleRel: string) => Reach
): string[] {
  const violations: string[] = [];

  for (const claim of claims) {
    if (!claim.module) {
      violations.push(
        `Command "${claim.pathKey}" could not be attributed to a source module, so the per-leaf\n` +
          '  plane rule cannot judge its claim. The leaf is registered somewhere this gate does not\n' +
          '  see (a Commander method other than .command()/.action(), or outside packages/cli/src).\n' +
          '  Fix the attribution rather than exempting the leaf: an unjudged machine-plane claim is\n' +
          '  exactly the hole this rule exists to close.'
      );
      continue;
    }

    if (claim.plane !== 'machine') continue;
    if (reach(claim.module).machineTouching) continue;

    violations.push(
      `Command "${claim.pathKey}" declares plane "machine", but the module that registers it\n` +
        `  (${claim.module}) has no import path to any machine seam:\n` +
        `    ${MACHINE_MARKERS.join(', ')}\n` +
        '  So the command provably cannot reach a machine, and the claim makes it proxyCapable:\n' +
        '  the proxy and the web console will offer it for REMOTE execution, where it would act on\n' +
        "  the EXECUTOR's config instead of the caller's.\n" +
        `  Fix: give it an explicit plane in COMMAND_PLANES (likely 'config'), e.g.\n` +
        `    '${claim.pathKey}': { plane: 'config' },\n` +
        '  If it really does reach a machine, it does so by a path this validator does not model.'
    );
  }

  return violations;
}
