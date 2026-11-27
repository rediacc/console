#!/usr/bin/env node
/**
 * Generate the THIRD_PARTY_LICENSES text bundled with rdc release builds.
 *
 * Assembles, deterministically and non-fatally-when-offline:
 *   1. Header + the GPL written-offer / source-availability statement.
 *   2. Embedded binaries conveyed by renet (CRIU, rsync) from the
 *      committed inventory (packages/cli/src/data/third-party-credits.json):
 *      version, SPDX, exact-version source URL, planned R2 mirror, notes.
 *   3. The SEA-bundled Node.js runtime + a pointer to the npm section.
 *   4. Renet Go dependencies via `go run github.com/google/go-licenses report`
 *      (network); a clearly-marked placeholder if that is unavailable.
 *   5. Bundled npm dependencies enumerated from the root package-lock.json
 *      (no new dependency).
 *   6. Verbatim license texts for each SPDX id the inventory and both reports name, from the
 *      committed packages/cli/src/data/third-party-licenses/<id>.txt (SPDX license-list-data,
 *      byte-exact); an id with no committed text is marked LICENSE TEXT MISSING, never a URL.
 *
 * Usage:
 *   npx tsx scripts/gen/generate-third-party-licenses.ts [--output <path>] [--repo-root <dir>]
 *
 * The generator always writes SOMETHING (so the SEA build has an asset); only a
 * failure to read the committed inventory is fatal.
 */

import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..', '..');

function parseArgs(): { output: string; repoRoot: string } {
  const args = process.argv.slice(2);
  let repoRoot = CONSOLE_ROOT;
  let output = '';
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--output') output = args[++i];
    else if (args[i] === '--repo-root') repoRoot = path.resolve(args[++i]);
  }
  if (!output) output = path.join(repoRoot, 'packages/cli/dist/assets/THIRD_PARTY_LICENSES');
  return { output, repoRoot };
}

interface Credit {
  kind?: string;
  name: string;
  version: string;
  spdx: string;
  license: string;
  upstreamSourceUrl?: string;
  plannedMirrorUrl?: string;
  notes?: string;
}
interface CreditsData {
  gplWrittenOffer: string;
  components: Credit[];
}

/** Where `packages/cli/bundle.mjs` writes the esbuild metafile, relative to packages/cli. */
const META_REL = 'dist/cli-bundle.meta.json';

const RULE = '='.repeat(78);
const SUBRULE = '-'.repeat(78);

/**
 * The SPDX license-list-data release every committed text under
 * packages/cli/src/data/third-party-licenses/ was copied from, byte for byte, from
 * `text/<id>.txt` at this tag. Refresh a text by fetching it at the tag and committing it unchanged.
 */
const SPDX_LICENSE_LIST_TAG = 'v3.29.0';

/** Deprecated identifiers the Go report still emits, mapped to the current id that has a committed text. */
const SPDX_ALIASES: Record<string, string> = {
  'GPL-2.0': 'GPL-2.0-only',
  'GPL-3.0': 'GPL-3.0-only',
  'LGPL-2.1': 'LGPL-2.1-only',
};

/** Every SPDX id a report row names, collected as the report sections are built. */
const reportIds = new Set<string>();

/** Records the ids of a licence expression such as `(MIT OR Apache-2.0)`; `UNKNOWN`-style words stay as they are. */
function noteLicenses(expression: string): void {
  for (const raw of expression.split(/[()\s]+|\bOR\b|\bAND\b|\bWITH\b/)) {
    const id = raw.trim();
    if (!id || id === 'OR' || id === 'AND' || id === 'WITH') continue;
    reportIds.add(SPDX_ALIASES[id] ?? id);
  }
}

/** Candidate committed filenames for an SPDX id's verbatim text. */
function licenseTextCandidates(spdx: string): string[] {
  return [`${SPDX_ALIASES[spdx] ?? spdx}.txt`];
}

function readCommittedLicenseText(repoRoot: string, spdx: string): string | null {
  const dir = path.join(repoRoot, 'packages/cli/src/data/third-party-licenses');
  for (const name of licenseTextCandidates(spdx)) {
    const p = path.join(dir, name);
    try {
      if (fs.existsSync(p)) return fs.readFileSync(p, 'utf-8');
    } catch {
      // try next candidate
    }
  }
  return null;
}

function loadCredits(repoRoot: string): CreditsData {
  const p = path.join(repoRoot, 'packages/cli/src/data/third-party-credits.json');
  return JSON.parse(fs.readFileSync(p, 'utf-8')) as CreditsData;
}

function componentBlock(c: Credit): string {
  const lines = [`${c.name} ${c.version}`, `  SPDX:    ${c.spdx}`, `  License: ${c.license}`];
  if (c.upstreamSourceUrl) lines.push(`  Source:  ${c.upstreamSourceUrl}`);
  if (c.plannedMirrorUrl) lines.push(`  Mirror:  ${c.plannedMirrorUrl} (planned)`);
  if (c.notes) lines.push(`  Note:    ${c.notes}`);
  return lines.join('\n');
}

function goLicensesSection(repoRoot: string): string {
  const renetDir = path.join(repoRoot, 'private/renet');
  if (!fs.existsSync(path.join(renetDir, 'go.mod'))) {
    return placeholderSection('renet is not present in this checkout (submodule not initialized).');
  }
  try {
    const out = execFileSync(
      'go',
      ['run', 'github.com/google/go-licenses@latest', 'report', './...'],
      { cwd: renetDir, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 180_000 }
    );
    const rows = out
      .split('\n')
      .filter((l) => l.trim().length > 0)
      .map((l) => {
        const [mod, url, lic] = l.split(',');
        noteLicenses(lic ?? 'UNKNOWN');
        return `  ${mod}  [${lic ?? '?'}]  ${url ?? ''}`.trimEnd();
      });
    if (rows.length === 0) return placeholderSection('go-licenses produced no rows.');
    return `Renet Go module dependencies (module  [license]  source):\n\n${rows.join('\n')}`;
  } catch {
    return placeholderSection(
      'go-licenses could not run (offline, or Go/network unavailable at build time).'
    );
  }
}

/**
 * BLOCKER: a placeholder is emitted only when go-licenses cannot run at build
 * time; the release job must regenerate with network so the shipped artifact
 * carries the real Go-dependency license report.
 */
function placeholderSection(reason: string, what = 'Renet Go module dependencies'): string {
  const lines = [`${what}: NOT GENERATED IN THIS BUILD.`, `Reason: ${reason}`];
  if (what === 'Renet Go module dependencies') {
    lines.push(
      'Regenerate on a networked build:',
      '  (cd private/renet && go run github.com/google/go-licenses@latest report ./...)'
    );
  }
  return lines.join('\n');
}

interface NpmDep {
  name: string;
  version: string;
  license: string;
}

function readPkgLicense(dir: string): string {
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf-8'));
    if (typeof pkg.license === 'string') return pkg.license;
    if (pkg.license && typeof pkg.license.type === 'string') return pkg.license.type;
    if (Array.isArray(pkg.licenses)) {
      return pkg.licenses.map((l: { type?: string }) => l.type ?? '?').join(' OR ');
    }
  } catch {
    // fall through
  }
  return 'UNKNOWN';
}

/** Package directory of a bundled input path: the last `node_modules/<pkg>` (scoped or not) segment. */
function bundledPackageDir(inputPath: string): string | null {
  const marker = 'node_modules/';
  const at = inputPath.lastIndexOf(marker);
  if (at < 0) return null;
  const rest = inputPath.slice(at + marker.length).split('/');
  const nameParts = rest[0].startsWith('@') ? rest.slice(0, 2) : rest.slice(0, 1);
  if (nameParts.length === 0 || nameParts.some((p) => !p)) return null;
  return inputPath.slice(0, at + marker.length) + nameParts.join('/');
}

/**
 * The npm packages the rdc bundle really contains: every `node_modules/<pkg>` input of the esbuild
 * metafile `bundle.mjs` writes, with version and licence read from that package's own package.json.
 */
function npmDepsSection(repoRoot: string): string {
  const metaPath = path.join(repoRoot, 'packages/cli', META_REL);
  let inputs: string[];
  try {
    const meta = JSON.parse(fs.readFileSync(metaPath, 'utf-8')) as {
      inputs?: Record<string, unknown>;
    };
    inputs = Object.keys(meta.inputs ?? {});
  } catch {
    return placeholderSection(
      `${META_REL} could not be read (run \`node bundle.mjs\` in packages/cli first).`,
      'CLI npm dependencies'
    );
  }
  const dirs = new Set<string>();
  for (const input of inputs) {
    const dir = bundledPackageDir(input);
    if (dir) dirs.add(dir);
  }
  const deps = new Map<string, NpmDep>();
  for (const dir of dirs) {
    const abs = path.resolve(repoRoot, 'packages/cli', dir);
    try {
      const pkg = JSON.parse(fs.readFileSync(path.join(abs, 'package.json'), 'utf-8')) as {
        name?: string;
        version?: string;
      };
      const name = pkg.name ?? dir.slice(dir.lastIndexOf('node_modules/') + 'node_modules/'.length);
      const version = pkg.version ?? '';
      deps.set(`${name}@${version}`, { name, version, license: readPkgLicense(abs) });
    } catch {
      // an input whose package.json is unreadable is not listed; the count below still guards emptiness
    }
  }
  const rows = [...deps.values()]
    .sort((a, b) => a.name.localeCompare(b.name) || a.version.localeCompare(b.version))
    .map((d) => `  ${d.name}@${d.version}  [${d.license}]`);
  if (rows.length === 0) {
    return placeholderSection(
      'the bundle metafile lists no node_modules inputs.',
      'CLI npm dependencies'
    );
  }
  return [`Bundled npm dependencies (from ${META_REL}):`, '', ...rows].join('\n');
}

/**
 * The LICENSE of the exact Node.js release that builds the SEA (the runtime embedded in rdc),
 * fetched from the tagged source at build time; the output records its sha256.
 */
async function nodeLicenseSection(): Promise<string> {
  const version = process.version;
  const url = `https://raw.githubusercontent.com/nodejs/node/${version}/LICENSE`;
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(60_000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();
    const digest = createHash('sha256').update(text).digest('hex');
    return [
      `Node.js ${version} (runtime embedded in rdc)`,
      `  Source: ${url}`,
      `  sha256: ${digest}`,
      '',
      text.trimEnd(),
    ].join('\n');
  } catch (err) {
    return placeholderSection(
      `the Node.js ${version} LICENSE could not be fetched from ${url}: ${(err as Error).message}`,
      'Node.js runtime LICENSE'
    );
  }
}

function licenseTextsAppendix(repoRoot: string, spdxIds: string[]): string {
  const blocks: string[] = [];
  for (const spdx of spdxIds) {
    const text = readCommittedLicenseText(repoRoot, spdx);
    const header = `${SUBRULE}\n${spdx}\n${SUBRULE}`;
    if (text) {
      blocks.push(`${header}\n\n${text.trimEnd()}`);
    } else {
      blocks.push(
        `${header}\n\nLICENSE TEXT MISSING for ${spdx}: commit the SPDX license-list-data ${SPDX_LICENSE_LIST_TAG} ` +
          `text/${spdx}.txt, unchanged, to packages/cli/src/data/third-party-licenses/${spdx}.txt.`
      );
    }
  }
  return blocks.join('\n\n');
}

async function build(repoRoot: string): Promise<string> {
  const credits = loadCredits(repoRoot);
  const embedded = credits.components.filter((c) => c.kind === 'embedded-binary');
  const rest = credits.components.filter((c) => c.kind !== 'embedded-binary');

  for (const c of credits.components) {
    if (c.spdx && c.spdx !== 'various') noteLicenses(c.spdx);
  }

  const parts: string[] = [];
  parts.push(RULE);
  parts.push('THIRD-PARTY SOFTWARE NOTICES AND LICENSES FOR RDC (Rediacc CLI)');
  parts.push(RULE);
  parts.push('');
  parts.push(
    'Rediacc is proprietary software distributed under the Rediacc license; the ' +
      'following third-party components are distributed alongside it under their ' +
      'own licenses.'
  );
  parts.push('');
  parts.push(
    'This file lists third-party software conveyed by the rdc distribution and ' +
      'its licenses. Unmodified binaries invoked via exec are mere aggregation ' +
      '(GPLv3 s5); no copyleft spreads to rdc itself.'
  );
  parts.push('');
  parts.push('GPL SOURCE AVAILABILITY');
  parts.push(credits.gplWrittenOffer);

  parts.push('');
  parts.push(RULE);
  parts.push('EMBEDDED BINARIES (conveyed by renet)');
  parts.push(RULE);
  parts.push('');
  parts.push(embedded.map(componentBlock).join(`\n\n${SUBRULE}\n\n`));

  parts.push('');
  parts.push(RULE);
  parts.push('RUNTIME AND BUNDLED DEPENDENCIES');
  parts.push(RULE);
  parts.push('');
  parts.push(rest.map(componentBlock).join(`\n\n${SUBRULE}\n\n`));

  parts.push('');
  parts.push(RULE);
  parts.push('RENET GO DEPENDENCIES');
  parts.push(RULE);
  parts.push('');
  parts.push(goLicensesSection(repoRoot));

  parts.push('');
  parts.push(RULE);
  parts.push('CLI NPM DEPENDENCIES');
  parts.push(RULE);
  parts.push('');
  parts.push(npmDepsSection(repoRoot));

  parts.push('');
  parts.push(RULE);
  parts.push('NODE.JS RUNTIME LICENSE');
  parts.push(RULE);
  parts.push('');
  parts.push(await nodeLicenseSection());

  parts.push('');
  parts.push(RULE);
  parts.push('LICENSE TEXTS');
  parts.push(RULE);
  parts.push('');
  // The report sections above have run, so reportIds now holds the inventory's ids and both reports' ids.
  const spdxIds = [...reportIds].sort((a, b) => Number(a > b) - Number(a < b));
  parts.push(licenseTextsAppendix(repoRoot, spdxIds));
  parts.push('');

  return parts.join('\n');
}

async function main(): Promise<void> {
  const { output, repoRoot } = parseArgs();
  let content: string;
  try {
    content = await build(repoRoot);
  } catch (err) {
    console.error(`generate-third-party-licenses: FATAL ${(err as Error).message}`);
    process.exit(1);
  }
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, content, 'utf-8');
  console.log(`THIRD_PARTY_LICENSES written to ${output} (${content.length} bytes)`);
}

await main();
