#!/usr/bin/env node
/**
 * Generate the THIRD_PARTY_LICENSES text bundled with rdc release builds.
 *
 * Assembles, deterministically and non-fatally-when-offline:
 *   1. Header + the GPL written-offer / source-availability statement.
 *   2. Embedded binaries conveyed by renet (CRIU, rsync, rclone) from the
 *      committed inventory (packages/cli/src/data/third-party-credits.json):
 *      version, SPDX, exact-version source URL, planned R2 mirror, notes.
 *   3. The SEA-bundled Node.js runtime + a pointer to the npm section.
 *   4. Renet Go dependencies via `go run github.com/google/go-licenses report`
 *      (network); a clearly-marked placeholder if that is unavailable.
 *   5. Bundled npm dependencies enumerated from the root package-lock.json
 *      (no new dependency).
 *   6. Verbatim license texts for each SPDX id used, from committed
 *      packages/cli/src/data/third-party-licenses/<id>.txt when present, else the canonical
 *      SPDX URL (offline fallback).
 *
 * Usage:
 *   npx tsx scripts/generate-third-party-licenses.ts [--output <path>] [--repo-root <dir>]
 *
 * The generator always writes SOMETHING (so the SEA build has an asset); only a
 * failure to read the committed inventory is fatal.
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');

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

const RULE = '='.repeat(78);
const SUBRULE = '-'.repeat(78);

/** Canonical SPDX license-text URLs, for the offline fallback note. */
const SPDX_URLS: Record<string, string> = {
  MIT: 'https://spdx.org/licenses/MIT.html',
  'GPL-2.0-only': 'https://www.gnu.org/licenses/old-licenses/gpl-2.0.txt',
  'GPL-3.0-or-later': 'https://www.gnu.org/licenses/gpl-3.0.txt',
  'Apache-2.0': 'https://www.apache.org/licenses/LICENSE-2.0.txt',
};

/** Candidate committed filenames for an SPDX id's verbatim text. */
function licenseTextCandidates(spdx: string): string[] {
  const base = spdx.replace(/-(only|or-later)$/, '');
  return [`${spdx}.txt`, `${base}.txt`];
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
function placeholderSection(reason: string): string {
  return [
    'Renet Go module dependencies: NOT GENERATED IN THIS BUILD.',
    `Reason: ${reason}`,
    'Regenerate on a networked build:',
    '  (cd private/renet && go run github.com/google/go-licenses@latest report ./...)',
  ].join('\n');
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

function npmDepsSection(repoRoot: string): string {
  const lockPath = path.join(repoRoot, 'package-lock.json');
  let lock: { packages?: Record<string, { version?: string; dev?: boolean; license?: string }> };
  try {
    lock = JSON.parse(fs.readFileSync(lockPath, 'utf-8'));
  } catch {
    return placeholderSection('package-lock.json could not be read.');
  }
  const packages = lock.packages ?? {};
  const deps = new Map<string, NpmDep>();
  for (const [p, meta] of Object.entries(packages)) {
    if (!p.includes('node_modules/')) continue; // skip workspace roots
    if (meta.dev) continue; // production deps only
    const name = p.slice(p.lastIndexOf('node_modules/') + 'node_modules/'.length);
    const version = meta.version ?? '';
    const license = meta.license ?? readPkgLicense(path.join(repoRoot, p));
    deps.set(`${name}@${version}`, { name, version, license });
  }
  const rows = [...deps.values()]
    .sort((a, b) => a.name.localeCompare(b.name) || a.version.localeCompare(b.version))
    .map((d) => `  ${d.name}@${d.version}  [${d.license}]`);
  if (rows.length === 0) return placeholderSection('no production npm dependencies found.');
  return [
    'Bundled npm dependencies (production; hoisted from package-lock.json):',
    '',
    ...rows,
  ].join('\n');
}

function licenseTextsAppendix(repoRoot: string, spdxIds: string[]): string {
  const blocks: string[] = [];
  for (const spdx of spdxIds) {
    const text = readCommittedLicenseText(repoRoot, spdx);
    const header = `${SUBRULE}\n${spdx}\n${SUBRULE}`;
    if (text) {
      blocks.push(`${header}\n\n${text.trimEnd()}`);
    } else {
      const url = SPDX_URLS[spdx] ?? `https://spdx.org/licenses/${spdx}.html`;
      blocks.push(
        `${header}\n\nFull license text: ${url}\n` +
          '(Verbatim text is retrievable at the URL above. To bundle it in this file, ' +
          `commit it to packages/cli/src/data/third-party-licenses/${spdx}.txt.)`
      );
    }
  }
  return blocks.join('\n\n');
}

function build(repoRoot: string): string {
  const credits = loadCredits(repoRoot);
  const embedded = credits.components.filter((c) => c.kind === 'embedded-binary');
  const rest = credits.components.filter((c) => c.kind !== 'embedded-binary');

  const spdxIds = [...new Set(credits.components.map((c) => c.spdx))]
    .filter((s) => s && s !== 'various')
    .sort();

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
  parts.push('LICENSE TEXTS');
  parts.push(RULE);
  parts.push('');
  parts.push(licenseTextsAppendix(repoRoot, spdxIds));
  parts.push('');

  return parts.join('\n');
}

function main(): void {
  const { output, repoRoot } = parseArgs();
  let content: string;
  try {
    content = build(repoRoot);
  } catch (err) {
    console.error(`generate-third-party-licenses: FATAL ${(err as Error).message}`);
    process.exit(1);
  }
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, content, 'utf-8');
  console.log(`THIRD_PARTY_LICENSES written to ${output} (${content.length} bytes)`);
}

main();
