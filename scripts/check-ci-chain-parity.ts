#!/usr/bin/env node
/**
 * Every gate a workflow runs must also be in `npm run ci`.
 *
 * WHY. `npm run ci` is the promise that a developer can find CI failures before
 * pushing. When a gate is wired into a workflow but not into that chain, the
 * promise quietly breaks: `npm run ci` goes green, the push goes red, and the
 * only way to learn the difference is a round trip. Four gates had already
 * drifted out this way -- including `check:ci-quality-gates`, the harness that
 * runs the meta-gates, so the checks that verify other checks were never
 * exercised locally at all.
 *
 * Nothing enforced the relationship, so it decayed silently. Adding a gate to a
 * workflow is the natural motion; remembering the chain is the step people skip.
 * This makes forgetting it a build failure instead of a surprise.
 *
 * DIRECTION IS DELIBERATE. Workflow ⊆ ci is required; the reverse is not. The
 * chain may hold extra checks a workflow does not name individually (most run
 * via the aggregate `npm run ci` step), and that is strictly more coverage
 * locally, which is fine.
 *
 * TWO WAYS A WORKFLOW NAMES A GATE, and both are checked:
 *   1. `npm run check:foo` -- matched by name against the chain.
 *   2. `.ci/scripts/quality/check-foo.sh` -- called directly, bypassing
 *      package.json entirely.
 * Only (1) was ever checked, so (2) was a silent hole: 16 gate scripts ran in CI
 * with no local equivalent, including check-workflow-gates.sh and
 * check-silent-failure-patterns.sh. A name-only check cannot see them, and the
 * report said "Every workflow gate is reachable from `npm run ci`" the whole
 * time. For (2) a gate counts as covered when some chain step's command mentions
 * that script path (directly or one level of `npm run` indirection).
 *
 * TEST SEAM. CHAIN_PARITY_ROOT overrides the repo root.
 *
 * ESCAPE HATCH. `.ci-chain-exempt`, BLOCKER-gated like every other suppression
 * list in this repo (see docs/agent/suppressions.md). For a gate that cannot run
 * locally. Entries are either a script name (`check:ci-foo`) or a repo-relative
 * script path (`.ci/scripts/quality/check-foo.sh`). Prefer fixing the gate over
 * exempting it: an exemption is a hole in the promise above.
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { parseBlockeredList, verifyAllBlockers } from './lib/blocker-validator.js';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// CHAIN_PARITY_ROOT is a test seam -- treat this directory as the repo root, so
// the gate test can drive fixtures without touching a tracked file.
const ROOT = process.env.CHAIN_PARITY_ROOT || path.resolve(__dirname, '..');
const WORKFLOW_DIR = path.join(ROOT, '.github', 'workflows');
const EXEMPT_PATH = path.join(ROOT, '.ci-chain-exempt');

/** Script names a workflow may run that are gates rather than build steps. */
const GATE_PREFIX = /^(check|test|lint|validate):/;

/**
 * Shell gates a workflow may invoke directly. Scoped to the two gate
 * directories and the `check-` prefix so build/deploy/release helpers (which are
 * steps, not gates, and have no business in a local chain) are not swept in.
 */
const BARE_GATE = /(?:^|[\s;&|(])(\.ci\/scripts\/(?:quality|security)\/check-[\w.-]+\.sh)/g;

/**
 * Every `.ci/scripts/**.sh` path reachable from the `ci` chain, following one
 * level of `npm run` indirection (the chain is `npm run a && npm run b`, and
 * those scripts are what actually name the shell gate).
 */
function chainScriptPaths(ciChain: string, scripts: Record<string, string>): Set<string> {
  const paths = new Set<string>();
  const collect = (cmd: string) => {
    for (const m of cmd.matchAll(/\.ci\/scripts\/[\w./-]+\.sh/g)) paths.add(m[0]);
  };
  collect(ciChain);
  for (const [, name] of ciChain.matchAll(/npm run ([\w:@/-]+)/g)) {
    const cmd = scripts[name];
    if (!cmd) continue;
    collect(cmd);
    for (const [, sub] of cmd.matchAll(/npm run ([\w:@/-]+)/g)) collect(scripts[sub] ?? '');
  }
  return paths;
}

function parseExempt(): Map<string, string> {
  const out = new Map<string, string>();
  if (!existsSync(EXEMPT_PATH)) return out;

  // The module header has always claimed this list is "BLOCKER-gated like every
  // other suppression list in this repo". It was not: a bespoke parser scraped
  // the reason text and nothing ever validated it, so `# tbd` would have passed
  // the moment anyone added an entry. Use the shared pair, like every other
  // reader (check-deps.ts, check-actions.ts, audit.sh).
  const entries = parseBlockeredList(EXEMPT_PATH);
  const failures = verifyAllBlockers(entries, EXEMPT_PATH);
  if (failures.length > 0) {
    console.error(`\x1b[31m✗\x1b[0m BLOCKER validation failed for ${EXEMPT_PATH}:`);
    for (const f of failures) console.error(f);
    console.error(
      '\n\x1b[31m✗\x1b[0m An exemption is a hole in the "npm run ci catches CI failures" promise. It must say why the gate genuinely cannot run locally.'
    );
    process.exit(1);
  }
  for (const { entry, blocker } of entries) out.set(entry, blocker);
  return out;
}

/**
 * Does `npm run <name>` resolve? For a workspace-scoped invocation the script
 * lives in that workspace's manifest, not the root one.
 */
function scriptExists(
  name: string,
  workspace: string | undefined,
  rootScripts: Record<string, string>
): boolean {
  if (!workspace) return name in rootScripts;
  for (const dir of ['packages', 'private', 'workers']) {
    const base = path.join(ROOT, dir);
    if (!existsSync(base)) continue;
    for (const entry of readdirSync(base)) {
      const manifest = path.join(base, entry, 'package.json');
      if (!existsSync(manifest)) continue;
      try {
        const m = JSON.parse(readFileSync(manifest, 'utf-8')) as {
          name?: string;
          scripts?: Record<string, string>;
        };
        if (m.name === workspace) return Boolean(m.scripts && name in m.scripts);
      } catch {
        /* unparseable manifest: not our concern here */
      }
    }
  }
  // Workspace not found at all — report it, since the invocation cannot work.
  return false;
}

function main(): void {
  // Both inputs are guarded rather than left to throw: a raw ENOENT stack trace
  // reads as a crashed script, not as "this gate is blind because its input is
  // gone", and the two need different responses from whoever sees it.
  const pkgPath = path.join(ROOT, 'package.json');
  if (!existsSync(pkgPath)) {
    console.error(
      `\x1b[31m✗\x1b[0m No package.json at ${pkgPath} — there is no \`ci\` chain to compare against, so this gate is blind.`
    );
    process.exit(1);
  }
  const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8')) as {
    scripts: Record<string, string>;
  };
  const ciChain = pkg.scripts?.ci ?? '';
  if (!ciChain) {
    console.error('[31m✗[0m package.json has no `ci` script — nothing to compare against.');
    process.exit(1);
  }

  const inChain = new Set(Array.from(ciChain.matchAll(/npm run ([\w:@/-]+)/g), (m) => m[1]));

  // An absent directory used to throw a raw ENOENT stack trace. That is not a
  // diagnostic: it reads as a crashed script rather than "this gate has no input
  // and is therefore asserting nothing".
  if (!existsSync(WORKFLOW_DIR)) {
    console.error(
      `\x1b[31m✗\x1b[0m No workflow directory at ${path.relative(ROOT, WORKFLOW_DIR)} — this gate is blind.`
    );
    process.exit(1);
  }

  const files = readdirSync(WORKFLOW_DIR).filter((f) => f.endsWith('.yml') || f.endsWith('.yaml'));
  if (files.length === 0) {
    console.error(`[31m✗[0m No workflows found in ${path.relative(ROOT, WORKFLOW_DIR)}`);
    process.exit(1);
  }

  // gate name -> workflows that run it
  const inWorkflows = new Map<string, Set<string>>();
  // bare shell gate path -> workflows that run it
  const bareGates = new Map<string, Set<string>>();
  // gate name -> workspace it is scoped to, when invoked with -w/--workspace
  const workspaceScoped = new Map<string, string>();
  for (const file of files) {
    const text = readFileSync(path.join(WORKFLOW_DIR, file), 'utf-8');
    // Strip full-line YAML comments: a path mentioned in prose ("keep in sync
    // with .ci/scripts/quality/lint.sh") is documentation, not an invocation.
    const code = text
      .split('\n')
      .filter((l) => !/^\s*#/.test(l))
      .join('\n');
    for (const m of code.matchAll(BARE_GATE)) {
      if (!bareGates.has(m[1])) bareGates.set(m[1], new Set());
      bareGates.get(m[1])?.add(file);
    }
    // Capture an optional workspace selector: `npm run test:unit -w @rediacc/cli`
    // or `--workspace=@rediacc/cli`. Without it a workspace-scoped gate looks
    // undefined (it is not a ROOT script) and the existence check false-positives.
    for (const m of text.matchAll(
      /npm run ([\w:@/-]+)((?:\s+(?:-w|--workspace=?)\s*[\w@/-]+)?)/g
    )) {
      const name = m[1];
      if (!GATE_PREFIX.test(name)) continue;
      if (name === 'ci') continue;
      const wsMatch = m[2]?.match(/(?:-w|--workspace=?)\s*([\w@/-]+)/);
      if (wsMatch) workspaceScoped.set(name, wsMatch[1]);
      if (!inWorkflows.has(name)) inWorkflows.set(name, new Set());
      inWorkflows.get(name)?.add(file);
    }
  }

  // Anti-vacuity: if we matched nothing AT ALL, the workflows moved and this is
  // blind. Both invocation styles count -- keying this on named gates alone made
  // a bare-gate-only tree report "blind" and swallow the real findings.
  if (inWorkflows.size === 0 && bareGates.size === 0) {
    console.error('[31m✗[0m Found ZERO gate invocations across the workflows.');
    console.error('  Expected `npm run check:*` steps — the layout changed and this gate is blind.');
    process.exit(1);
  }

  const exempt = parseExempt();
  const chainPaths = chainScriptPaths(ciChain, pkg.scripts);
  const missingBare: Array<{ name: string; where: string[] }> = [];
  for (const [scriptPath, where] of bareGates) {
    if (chainPaths.has(scriptPath)) continue;
    if (exempt.has(scriptPath)) continue;
    missingBare.push({ name: scriptPath, where: [...where].sort() });
  }

  const missing: Array<{ name: string; where: string[] }> = [];
  const undefinedScripts: Array<{ name: string; where: string[] }> = [];
  for (const [name, where] of inWorkflows) {
    if (inChain.has(name)) continue;
    if (exempt.has(name)) continue;
    // A workflow naming a script package.json does not define is a DIFFERENT
    // break: the CI step would die with "Missing script". This used to be
    // skipped here with a comment delegating it to check-workflows.sh -- which
    // does not do it (that script checks banned patterns, action pinning,
    // secrets in run:, and the inline-run ratchet; it never reads
    // package.json.scripts). So the reverse break was unguarded entirely.
    if (!scriptExists(name, workspaceScoped.get(name), pkg.scripts)) {
      undefinedScripts.push({ name, where: [...where].sort() });
      continue;
    }
    // A workspace-scoped gate lives in that workspace, not the root chain, so
    // the `npm run ci` coverage comparison below does not apply to it.
    if (workspaceScoped.has(name)) continue;
    missing.push({ name, where: [...where].sort() });
  }

  console.log('CI Chain Parity');
  console.log('='.repeat(60));
  console.log(
    `${inWorkflows.size} named gate(s) + ${bareGates.size} bare shell gate(s) referenced by ` +
      `${files.length} workflow(s); ${inChain.size} step(s) in \`npm run ci\`; ${exempt.size} exempt.`
  );
  console.log('');

  // Report the reverse break first: a workflow naming an undefined script is a
  // hard CI failure ("Missing script"), not a coverage gap.
  if (undefinedScripts.length > 0) {
    console.error(
      `\x1b[31m\u2717 ${undefinedScripts.length} gate(s) named by a workflow but NOT defined in package.json:\x1b[0m`
    );
    for (const { name, where } of undefinedScripts.sort((a, b) => a.name.localeCompare(b.name))) {
      console.error(`  ${name}`);
      console.error(`    used by: ${where.join(', ')}`);
    }
    console.error('');
    console.error('These steps fail in CI with "Missing script". Define the script in package.json,');
    console.error('or fix the name in the workflow.');
    process.exit(1);
  }

  if (missing.length === 0 && missingBare.length === 0) {
    console.log('[32m✓[0m Every workflow gate is reachable from `npm run ci`.');
    return;
  }

  if (missing.length > 0) {
    console.error(`[31m✗ ${missing.length} gate(s) run in CI but NOT in \`npm run ci\`:[0m`);
    for (const { name, where } of missing.sort((a, b) => a.name.localeCompare(b.name))) {
      console.error(`  ${name}`);
      console.error(`    used by: ${where.join(', ')}`);
    }
    console.error('');
  }

  if (missingBare.length > 0) {
    console.error(
      `[31m✗ ${missingBare.length} shell gate(s) invoked directly by a workflow but NOT in \`npm run ci\`:[0m`
    );
    for (const { name, where } of missingBare.sort((a, b) => a.name.localeCompare(b.name))) {
      console.error(`  ${name}`);
      console.error(`    used by: ${where.join(', ')}`);
    }
    console.error('');
    console.error('Give each one a `check:ci-*` entry in package.json, append it to the `ci` chain,');
    console.error('and change the workflow step to `npm run check:ci-*` so both directions agree.');
    console.error('');
  }

  console.error('`npm run ci` is the promise that local runs catch CI failures. Append these to');
  console.error('the `ci` script in package.json, or add them to .ci-chain-exempt with a BLOCKER');
  console.error('reason if they genuinely cannot run locally.');
  process.exit(1);
}

main();
