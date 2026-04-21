/**
 * CI integrity check for workers/www/src/redirects.json.
 *
 * Validates:
 *   1. Every non-null `to` path exists in route-manifest.json OR in the
 *      ALLOWED_NON_MANIFEST_TARGETS set (Worker-served SPA routes, file
 *      endpoints, section indexes not emitted by the manifest generator).
 *   2. No redirect chains: if A -> B, B must not itself be a key in EXACT
 *      (self-maps A -> A are legal — they trigger lang-prefix addition
 *      when the request has no lang; the Worker's self-redirect guard
 *      prevents loops when lang is already present).
 *   3. Every pattern `from` compiles as `new RegExp()`.
 *
 * Run via: `npm run check:ci-redirects`
 * Fails fast with diagnostics on any violation.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const REDIRECTS_JSON = path.join(REPO_ROOT, 'workers/www/src/redirects.json');
const MANIFEST = path.join(REPO_ROOT, 'packages/www/dist/route-manifest.json');

interface Rule {
  to: string | null;
  status: 301 | 410;
  rationale: string;
}
interface Pattern {
  from: string;
  to: string | null;
  status: 301 | 410;
  rationale: string;
}
interface Redirects {
  exact: Record<string, Rule>;
  patterns: Pattern[];
  allowed_non_manifest_targets: string[];
}
interface ManifestEntry {
  path: string;
}

function fail(msg: string): never {
  process.stderr.write(`\n\x1b[31mFAIL\x1b[0m  ${msg}\n\n`);
  process.exit(1);
}

function ok(msg: string): void {
  process.stdout.write(`\x1b[32mOK\x1b[0m    ${msg}\n`);
}

// --- Load inputs -----------------------------------------------------------

if (!fs.existsSync(REDIRECTS_JSON)) {
  fail(`Missing ${REDIRECTS_JSON}`);
}
if (!fs.existsSync(MANIFEST)) {
  fail(
    `Missing ${MANIFEST}\n` +
      `This check requires a prior www build. Run:\n` +
      `  cd packages/www && npm run build\n`
  );
}

const redirects: Redirects = JSON.parse(fs.readFileSync(REDIRECTS_JSON, 'utf8'));
const manifest: ManifestEntry[] = JSON.parse(fs.readFileSync(MANIFEST, 'utf8'));
const livePaths = new Set<string>(manifest.map((e) => e.path));
const allowedNonManifest = new Set<string>(redirects.allowed_non_manifest_targets);
const allLive = new Set<string>([...livePaths, ...allowedNonManifest]);

process.stdout.write(
  `Checking ${Object.keys(redirects.exact).length} exact rules + ${redirects.patterns.length} patterns against ${livePaths.size} live pages (+ ${allowedNonManifest.size} allowed non-manifest)\n`
);

// --- Check 1: 301 targets exist --------------------------------------------

const brokenTargets: Array<{ from: string; to: string }> = [];
for (const [from, rule] of Object.entries(redirects.exact)) {
  if (rule.status === 301 && rule.to !== null && !allLive.has(rule.to)) {
    brokenTargets.push({ from, to: rule.to });
  }
}
if (brokenTargets.length > 0) {
  const lines = brokenTargets.map((b) => `  ${b.from}  ->  ${b.to}  (target not live)`).join('\n');
  fail(
    `${brokenTargets.length} exact 301 rule(s) point to non-live pages:\n${lines}\n\n` +
      `Fix: update redirects.json to point to a live page, change to 410, or add the ` +
      `target to ALLOWED_NON_MANIFEST_TARGETS if it's intentionally not in the manifest.`
  );
}
ok(`all ${Object.values(redirects.exact).filter((r) => r.status === 301).length} exact 301 targets are live`);

// --- Check 2: No redirect chains -------------------------------------------
// Self-maps (A -> A) are legal: they trigger lang-prefix addition, and the
// Worker's self-redirect guard prevents loops. A rule pointing at a self-map
// target is also fine (Worker resolves in one hop). Only flag genuine chains
// A -> B where B -> C with C !== B.

const chains: Array<{ from: string; to: string; via: string }> = [];
for (const [from, rule] of Object.entries(redirects.exact)) {
  if (rule.status !== 301 || rule.to === null || rule.to === from) continue;
  const next = redirects.exact[rule.to];
  if (next && next.status === 301 && next.to !== null && next.to !== rule.to) {
    chains.push({ from, to: rule.to, via: next.to });
  }
}
if (chains.length > 0) {
  const lines = chains.map((c) => `  ${c.from}  ->  ${c.to}  ->  ${c.via}  (multi-hop)`).join('\n');
  fail(
    `${chains.length} redirect chain(s) detected:\n${lines}\n\n` +
      `Fix: point the source directly at the final target.`
  );
}
ok('no redirect chains');

// --- Check 3: Pattern regex compiles ---------------------------------------

const badPatterns: Array<{ from: string; error: string }> = [];
for (const p of redirects.patterns) {
  try {
    new RegExp(p.from);
  } catch (e) {
    badPatterns.push({ from: p.from, error: String(e) });
  }
}
if (badPatterns.length > 0) {
  const lines = badPatterns.map((b) => `  ${b.from}\n    ${b.error}`).join('\n');
  fail(`${badPatterns.length} pattern(s) failed to compile:\n${lines}`);
}
ok(`all ${redirects.patterns.length} patterns compile`);

// --- Check 4: Basic shape sanity -------------------------------------------

const shapeIssues: string[] = [];
for (const [from, rule] of Object.entries(redirects.exact)) {
  if (!from.startsWith('/')) shapeIssues.push(`key must start with /: ${from}`);
  if (rule.status !== 301 && rule.status !== 410)
    shapeIssues.push(`${from}: status must be 301 or 410, got ${rule.status}`);
  if (rule.status === 410 && rule.to !== null)
    shapeIssues.push(`${from}: 410 must have to=null, got ${JSON.stringify(rule.to)}`);
  if (rule.status === 301 && rule.to === null)
    shapeIssues.push(`${from}: 301 must have non-null to`);
  if (!rule.rationale || rule.rationale.length < 10)
    shapeIssues.push(`${from}: rationale too short (<10 chars)`);
}
if (shapeIssues.length > 0) {
  fail(`Shape validation failed:\n${shapeIssues.map((s) => `  ${s}`).join('\n')}`);
}
ok('all rules have correct shape');

process.stdout.write('\n\x1b[32mAll redirect integrity checks passed.\x1b[0m\n');
