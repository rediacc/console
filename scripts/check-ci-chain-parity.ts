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
 * ESCAPE HATCH. `.ci-chain-exempt`, BLOCKER-gated like every other suppression
 * list in this repo (see CLAUDE.md). For a gate that genuinely cannot run
 * locally. Prefer fixing the gate over exempting it: an exemption is a hole in
 * the promise above.
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const WORKFLOW_DIR = path.join(ROOT, '.github', 'workflows');
const EXEMPT_PATH = path.join(ROOT, '.ci-chain-exempt');

/** Script names a workflow may run that are gates rather than build steps. */
const GATE_PREFIX = /^(check|test|lint|validate):/;

function parseExempt(): Map<string, string> {
  const out = new Map<string, string>();
  if (!existsSync(EXEMPT_PATH)) return out;
  let blocker = '';
  for (const raw of readFileSync(EXEMPT_PATH, 'utf-8').split('\n')) {
    const line = raw.trim();
    if (line === '') {
      blocker = '';
      continue;
    }
    if (line.startsWith('#')) {
      const m = line.match(/^#\s*BLOCKER:\s*(.+)$/i);
      if (m) blocker = m[1].trim();
      continue;
    }
    const [name, inline] = line.split('#').map((s) => s.trim());
    out.set(name, inline?.replace(/^BLOCKER:\s*/i, '') ?? blocker);
  }
  return out;
}

function main(): void {
  const pkg = JSON.parse(readFileSync(path.join(ROOT, 'package.json'), 'utf-8')) as {
    scripts: Record<string, string>;
  };
  const ciChain = pkg.scripts.ci ?? '';
  if (!ciChain) {
    console.error('[31m✗[0m package.json has no `ci` script — nothing to compare against.');
    process.exit(1);
  }

  const inChain = new Set(Array.from(ciChain.matchAll(/npm run ([\w:@/-]+)/g), (m) => m[1]));

  const files = readdirSync(WORKFLOW_DIR).filter((f) => f.endsWith('.yml') || f.endsWith('.yaml'));
  if (files.length === 0) {
    console.error(`[31m✗[0m No workflows found in ${path.relative(ROOT, WORKFLOW_DIR)}`);
    process.exit(1);
  }

  // gate name -> workflows that run it
  const inWorkflows = new Map<string, Set<string>>();
  for (const file of files) {
    const text = readFileSync(path.join(WORKFLOW_DIR, file), 'utf-8');
    for (const m of text.matchAll(/npm run ([\w:@/-]+)/g)) {
      const name = m[1];
      if (!GATE_PREFIX.test(name)) continue;
      if (name === 'ci') continue;
      if (!inWorkflows.has(name)) inWorkflows.set(name, new Set());
      inWorkflows.get(name)?.add(file);
    }
  }

  // Anti-vacuity: if we matched nothing, the workflows moved and this is blind.
  if (inWorkflows.size === 0) {
    console.error('[31m✗[0m Found ZERO gate invocations across the workflows.');
    console.error('  Expected `npm run check:*` steps — the layout changed and this gate is blind.');
    process.exit(1);
  }

  const exempt = parseExempt();
  const missing: Array<{ name: string; where: string[] }> = [];
  for (const [name, where] of inWorkflows) {
    if (inChain.has(name)) continue;
    if (exempt.has(name)) continue;
    // A script the workflow names but package.json does not define is a
    // different bug; check-workflows.sh owns that. Skip rather than double-report.
    if (!(name in pkg.scripts)) continue;
    missing.push({ name, where: [...where].sort() });
  }

  console.log('CI Chain Parity');
  console.log('='.repeat(60));
  console.log(
    `${inWorkflows.size} gate(s) referenced by ${files.length} workflow(s); ` +
      `${inChain.size} step(s) in \`npm run ci\`; ${exempt.size} exempt.`
  );
  console.log('');

  if (missing.length === 0) {
    console.log('[32m✓[0m Every workflow gate is reachable from `npm run ci`.');
    return;
  }

  console.error(`[31m✗ ${missing.length} gate(s) run in CI but NOT in \`npm run ci\`:[0m`);
  for (const { name, where } of missing.sort((a, b) => a.name.localeCompare(b.name))) {
    console.error(`  ${name}`);
    console.error(`    used by: ${where.join(', ')}`);
  }
  console.error('');
  console.error('`npm run ci` is the promise that local runs catch CI failures. Append these to');
  console.error('the `ci` script in package.json, or add them to .ci-chain-exempt with a BLOCKER');
  console.error('reason if they genuinely cannot run locally.');
  process.exit(1);
}

main();
