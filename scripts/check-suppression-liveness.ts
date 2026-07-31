#!/usr/bin/env tsx
/**
 * check-suppression-liveness.ts — are our suppressions still load-bearing?
 *
 * Every allowlist / blocklist / override in this repo must carry a BLOCKER
 * reason (see docs/agent/suppressions.md). That convention proves a reason EXISTS; it cannot
 * prove the reason is still TRUE. This gate closes the other half: for each
 * entry it asks whether the thing being suppressed still exists at all.
 *
 * Usage:
 *   npx tsx scripts/check-suppression-liveness.ts
 *   npx tsx scripts/check-suppression-liveness.ts --probe overrides
 *   npx tsx scripts/check-suppression-liveness.ts --json
 *
 * Env:
 *   SUPPRESSION_LIVENESS_ROOT  test seam — treat this dir as the repo root
 *
 * Exit 0 when nothing FAIL-tier is stale; 1 otherwise, or if the run was
 * vacuous (every probe skipped while entries existed).
 *
 * The .audit-* allowlists are NOT probed here: their oracle needs a live
 * `npm audit`, and .ci/scripts/security/audit.sh already owns that check
 * (check_stale_entries). Duplicating it would mean a second, slower, network-
 * dependent oracle over the same facts.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { NC, RED } from './utils/console.js';
import { collectActionRefs } from './lib/action-refs.js';
import { parseDockerfileVersions } from './lib/dockerfile-versions.js';
import { EMBED_ASSET_SOURCES } from './lib/embed-asset-sources.js';
import {
  type Probe,
  type Universe,
  blockeredEntries,
  findOrphanedBlockers,
  formatReport,
  isVacuous,
  runProbes,
} from './lib/suppression-liveness.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = process.env.SUPPRESSION_LIVENESS_ROOT || path.join(__dirname, '..');

// ---------------------------------------------------------------------------
// Oracles
// ---------------------------------------------------------------------------

/**
 * The gate name on a two-column `.ci-parity-exempt` line, given its 1-based
 * line number. The file's entry lines are `<direction>  <gate>`, and the shared
 * parseBlockeredList takes the first whitespace-separated token.
 */
function readSecondColumn(root: string, line: number): string {
  const p = path.join(root, '.ci-parity-exempt');
  if (!fs.existsSync(p)) return '';
  const raw = fs.readFileSync(p, 'utf-8').split('\n')[line - 1] ?? '';
  return raw.trim().split(/\s+/)[1] ?? '';
}

/** Every package name declared in any manifest in the workspace. */
function declaredPackageNames(root: string): Universe | null {
  const globs = [
    'package.json',
    'packages/*/package.json',
    'private/*/package.json',
    'private/*/*/package.json',
    'workers/*/package.json',
  ];
  const files: string[] = [];
  for (const g of globs) {
    const parts = g.split('/');
    const walk = (dir: string, i: number): void => {
      if (i === parts.length - 1) {
        const p = path.join(dir, parts[i]);
        if (fs.existsSync(p)) files.push(p);
        return;
      }
      if (parts[i] === '*') {
        if (!fs.existsSync(dir)) return;
        for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
          if (e.isDirectory()) walk(path.join(dir, e.name), i + 1);
        }
      } else {
        walk(path.join(dir, parts[i]), i + 1);
      }
    };
    walk(root, 0);
  }
  if (files.length === 0) return null;

  const names = new Set<string>();
  for (const f of files) {
    let pkg: Record<string, unknown>;
    try {
      pkg = JSON.parse(fs.readFileSync(f, 'utf-8'));
    } catch {
      continue;
    }
    for (const field of [
      'dependencies',
      'devDependencies',
      'optionalDependencies',
      'peerDependencies',
    ]) {
      for (const n of Object.keys((pkg[field] as Record<string, string>) ?? {})) names.add(n);
    }
  }
  return { names, source: `${names.size} declared names across ${files.length} manifests` };
}

/** Every module path in a `require` directive of any go.mod under private/. */
function goRequires(root: string): Universe | null {
  const priv = path.join(root, 'private');
  if (!fs.existsSync(priv)) return null;
  const mods: string[] = [];
  for (const e of fs.readdirSync(priv, { withFileTypes: true })) {
    if (!e.isDirectory()) continue;
    const p = path.join(priv, e.name, 'go.mod');
    if (fs.existsSync(p)) mods.push(p);
  }
  if (mods.length === 0) return null;

  const names = new Set<string>();
  for (const m of mods) {
    for (const raw of fs.readFileSync(m, 'utf-8').split('\n')) {
      const line = raw.trim();
      if (!line || line.startsWith('//')) continue;
      // Both `require foo/bar v1.2.3` and block-form `foo/bar v1.2.3`.
      const match = line.match(/^(?:require\s+)?([a-z0-9][\w.\-/]*\.[\w.\-/]+)\s+v\d/);
      if (match) names.add(match[1]);
    }
  }
  return { names, source: `${names.size} go.mod requires across ${mods.length} module(s)` };
}

/** Asset bases that are BOTH a Dockerfile ARG and a known upstream source. */
function embedAssetBases(root: string): Universe | null {
  const dockerfile = path.join(root, 'private', 'renet', 'Dockerfile');
  if (!fs.existsSync(dockerfile)) return null;
  let versions: Map<string, string>;
  try {
    versions = parseDockerfileVersions(fs.readFileSync(dockerfile, 'utf-8')).versions;
  } catch {
    return null;
  }
  const known = new Set(EMBED_ASSET_SOURCES.map((s) => s.base));
  const names = new Set([...versions.keys()].filter((k) => known.has(k)));
  return { names, source: `${names.size} embedded assets in ${path.basename(dockerfile)}` };
}

/** Every third-party action referenced by a workflow or composite action. */
function referencedActions(root: string): Universe | null {
  const refs = collectActionRefs(root);
  if (refs.size === 0) return null;
  return { names: new Set(refs.keys()), source: `${refs.size} actions referenced under .github` };
}

/** Every package name present anywhere in the lockfile tree. */
function lockfilePackageNames(root: string): Universe | null {
  const lockPath = path.join(root, 'package-lock.json');
  if (!fs.existsSync(lockPath)) return null;
  let lock: { lockfileVersion?: number; packages?: Record<string, unknown> };
  try {
    lock = JSON.parse(fs.readFileSync(lockPath, 'utf-8'));
  } catch {
    return null;
  }
  if (!lock.packages || (lock.lockfileVersion ?? 0) < 2) return null;
  const names = new Set<string>();
  for (const p of Object.keys(lock.packages)) {
    const i = p.lastIndexOf('node_modules/');
    if (i >= 0) names.add(p.slice(i + 'node_modules/'.length));
  }
  return { names, source: `${names.size} packages in package-lock.json v${lock.lockfileVersion}` };
}

// ---------------------------------------------------------------------------
// Probes
// ---------------------------------------------------------------------------

const listProbe = (
  id: string,
  file: string,
  universe: (root: string) => Universe | null,
  minUniverse: number,
  why: (entry: string, u: Universe) => string,
  fix: (entry: string, line: number) => string[]
): Probe => ({
  id,
  file,
  tier: 'fail',
  minUniverse,
  entries: (root) => blockeredEntries(path.join(root, file)),
  universe,
  why,
  fix: (entry, e) => fix(entry, e.line),
});

const PROBES: Probe[] = [
  listProbe(
    'deps',
    '.deps-upgrade-blocklist',
    declaredPackageNames,
    20,
    (entry, u) =>
      `no manifest declares "${entry}" (oracle: ${u.source}). scripts/check-deps.ts only consults this blocklist for names \`npm outdated\` reports, and \`npm outdated\` only reports declared deps — so this entry can never suppress anything.`,
    (entry, line) => [
      `remove line ${line} ("${entry}") from .deps-upgrade-blocklist, then: npm run check:deps`,
    ]
  ),
  listProbe(
    'go-deps',
    '.go-deps-upgrade-blocklist',
    goRequires,
    5,
    (entry, u) =>
      `no go.mod requires "${entry}" (oracle: ${u.source}); .ci/scripts/quality/check-go-deps.sh can never consult this entry.`,
    (entry, line) => [
      `remove line ${line} ("${entry}") from .go-deps-upgrade-blocklist, then: npm run check:ci-renet`,
    ]
  ),
  listProbe(
    'embed-assets',
    '.embed-assets-upgrade-blocklist',
    embedAssetBases,
    4,
    (entry, u) =>
      `"${entry}" is not an embedded asset any more (oracle: ${u.source}); it is absent from the renet Dockerfile ARGs, the known source list, or both.`,
    (entry, line) => [
      `remove line ${line} ("${entry}") from .embed-assets-upgrade-blocklist, then: npm run check:ci-embed-asset-freshness`,
    ]
  ),
  listProbe(
    'actions',
    '.actions-upgrade-blocklist',
    referencedActions,
    3,
    (entry, u) =>
      `no workflow or composite action uses "${entry}" (oracle: ${u.source}); scripts/check-actions.ts only reports on actions it finds a \`uses:\` for.`,
    (entry, line) => [
      `remove line ${line} ("${entry}") from .actions-upgrade-blocklist, then: npm run check:actions`,
    ]
  ),
  listProbe(
    'templates-skiplist',
    'packages/json/.templates-skiplist',
    (root) => {
      const dir = path.join(root, 'packages/json/templates');
      if (!fs.existsSync(dir)) return null;
      const names = new Set<string>();
      for (const cat of fs.readdirSync(dir, { withFileTypes: true })) {
        if (!cat.isDirectory()) continue;
        for (const tpl of fs.readdirSync(path.join(dir, cat.name), { withFileTypes: true })) {
          if (tpl.isDirectory()) names.add(`${cat.name}/${tpl.name}`);
        }
      }
      return { names, source: `${names.size} templates under packages/json/templates` };
    },
    10,
    (entry, u) =>
      `template "${entry}" no longer exists (oracle: ${u.source}); it is skipped by two independent parsers (packages/json/generate.sh and packages/www/scripts/generate-json.js) that can now never match it.`,
    (entry, line) => [
      `remove line ${line} ("${entry}") from packages/json/.templates-skiplist`,
    ]
  ),
  {
    id: 'cli-i18n-orphan',
    file: '.cli-i18n-orphan-allowlist',
    tier: 'fail',
    minUniverse: 50,
    entries: (root) => blockeredEntries(path.join(root, '.cli-i18n-orphan-allowlist')),
    // Entries are key PREFIXES, so exact matching would condemn every one.
    isLive: (entry, u) => {
      for (const leaf of u.names) if (leaf.startsWith(entry)) return true;
      return false;
    },
    universe: ((root: string) => {
      const p = path.join(root, 'packages/cli/src/i18n/locales/en/cli.json');
      if (!fs.existsSync(p)) return null;
      let json: unknown;
      try {
        json = JSON.parse(fs.readFileSync(p, 'utf-8'));
      } catch {
        return null;
      }
      // Flatten to dotted leaf keys; entries are PREFIXES over this space.
      const names = new Set<string>();
      const walk = (node: unknown, prefix: string): void => {
        if (node && typeof node === 'object' && !Array.isArray(node)) {
          for (const [k, v] of Object.entries(node as Record<string, unknown>)) {
            walk(v, prefix ? `${prefix}.${k}` : k);
          }
        } else if (prefix) {
          names.add(prefix);
        }
      };
      walk(json, '');
      return { names, source: `${names.size} leaf keys in en/cli.json` };
    }) as (root: string) => Universe | null,
    why: (entry, u) =>
      `no leaf key starts with "${entry}" (oracle: ${u.source}); the prefix exempts nothing from the orphan report in scripts/check-cli-i18n-key-usage.ts.`,
    fix: (entry, e) => [
      `remove line ${e.line} ("${entry}") from .cli-i18n-orphan-allowlist, then: npm run check:ci-i18n-cli-key-usage`,
    ],
  },
  {
    id: 'dead-bash-allowlist',
    file: '.dead-bash-allowlist',
    tier: 'fail',
    // Structural guard, not a count floor: universe() returns null when the
    // shell tree is missing. A count floor would be the rejected ratio guard,
    // and every entry CAN legitimately go stale at once.
    minUniverse: 0,
    entries: (root) => blockeredEntries(path.join(root, '.dead-bash-allowlist')),
    universe: (root) => {
      if (!fs.existsSync(path.join(root, '.ci'))) return null;
      // A glob: root is live if the directory still exists; a dispatch: prefix
      // is live if some shell function still starts with it; a manual: file is
      // live if the script is still there.
      const names = new Set<string>();
      const shDirs: string[] = [];
      const walk = (d: string): void => {
        if (!fs.existsSync(d)) return;
        for (const e of fs.readdirSync(d, { withFileTypes: true })) {
          if (e.name === 'node_modules' || e.name === '.git') continue;
          const p = path.join(d, e.name);
          if (e.isDirectory()) walk(p);
          else if (e.name.endsWith('.sh')) shDirs.push(path.relative(root, p));
        }
      };
      for (const base of ['.ci', 'scripts', '.claude', '.devcontainer', 'packages', 'private']) {
        walk(path.join(root, base));
      }
      for (const extra of ['run.sh', 'rdc.sh']) {
        if (fs.existsSync(path.join(root, extra))) shDirs.push(extra);
      }
      if (shDirs.length === 0) return null;
      const fnNames: string[] = [];
      for (const rel of shDirs) {
        names.add(`manual:${rel}`);
        for (const seg of rel.split('/').slice(0, -1).map((_, i, a) => `${a.slice(0, i + 1).join('/')}/`)) {
          names.add(`glob:${seg}`);
        }
        try {
          for (const line of fs.readFileSync(path.join(root, rel), 'utf-8').split('\n')) {
            const m = line.match(/^([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\)\s*\{/);
            if (m) fnNames.push(m[1]);
          }
        } catch {
          /* unreadable */
        }
      }
      for (const fn of fnNames) {
        for (let i = 1; i <= fn.length; i++) names.add(`dispatch:${fn.slice(0, i)}`);
      }
      return { names, source: `${shDirs.length} shell files, ${fnNames.length} functions` };
    },
    why: (entry, u) =>
      entry.startsWith('glob:')
        ? `discovery root "${entry.slice(5)}" no longer contains any shell script (oracle: ${u.source}); the exemption covers nothing.`
        : entry.startsWith('dispatch:')
          ? `no shell function starts with "${entry.slice(9)}" (oracle: ${u.source}); the dispatch exemption covers nothing.`
          : `"${entry.slice(7)}" no longer exists (oracle: ${u.source}); the manual-entrypoint exemption covers nothing.`,
    fix: (entry, e) => [
      `remove line ${e.line} ("${entry}") from .dead-bash-allowlist, then: npm run check:ci-dead-bash`,
    ],
  },
  {
    id: 'parity-exempt',
    file: '.ci-parity-exempt',
    tier: 'fail',
    // Structural guard, not a count floor: universe() returns null when there
    // are no workflows to read, and every entry can legitimately go stale at
    // once (a batch of PR-context gates being retired together).
    minUniverse: 0,
    // The entry lines carry a leading direction column, so the shared parser's
    // first-token rule would read "ci-only" as the entry. Split it off here;
    // the BLOCKER association and validation stay with the shared parser.
    entries: (root) =>
      blockeredEntries(path.join(root, '.ci-parity-exempt')).map((e) => ({
        ...e,
        entry: e.entry === 'ci-only' || e.entry === 'local-only' ? readSecondColumn(root, e.line) : e.entry,
      })),
    universe: (root) => {
      // An exemption is live only while the thing it exempts is still invoked
      // by a workflow. Once the step is deleted the entry is a permanent hole
      // in the "a local run catches CI failures" promise, guarding nothing.
      //
      // ONLY THE ci-only DIRECTION IS ORACLED HERE. A local-only entry is live
      // when the LOCAL gate set still runs it, which is a different question
      // with a different oracle (scripts/ci-runner/manifest.ts). There are no
      // local-only entries today; the day one appears, this probe must grow the
      // second oracle rather than judge it against the workflow tree, which
      // would condemn it for the very asymmetry it declares.
      const dir = path.join(root, '.github', 'workflows');
      if (!fs.existsSync(dir)) return null;
      const files = fs.readdirSync(dir).filter((f) => f.endsWith('.yml') || f.endsWith('.yaml'));
      if (files.length === 0) return null;
      const names = new Set<string>();
      for (const f of files) {
        const text = fs
          .readFileSync(path.join(dir, f), 'utf-8')
          .split('\n')
          .filter((l) => !/^\s*#/.test(l))
          .join('\n');
        for (const m of text.matchAll(/npm run ([\w:@/-]+)/g)) names.add(m[1]);
        for (const m of text.matchAll(/(\.ci\/scripts\/[\w./-]+\.sh)/g)) names.add(m[1]);
      }
      return { names, source: `${files.length} workflows, ${names.size} gate invocations` };
    },
    why: (entry, u) =>
      `no workflow invokes "${entry}" any more (oracle: ${u.source}); the exemption holds a hole open for a gate that no longer runs in CI.`,
    fix: (entry, e) => [
      `remove line ${e.line} ("${entry}") from .ci-parity-exempt, then: npm run check:ci-parity`,
    ],
  },
  {
    id: 'content-quality',
    file: '.ci/config/content-quality-allowlist.txt',
    tier: 'fail',
    // The oracle here is per-path existence, so a count floor would be exactly
    // the rejected ratio guard ("all entries dead ⇒ suspicious") — and all
    // entries CAN legitimately be dead, which is the whole point. The trust
    // guard is instead structural: universe() returns null when the content
    // tree is absent, so a partial checkout skips rather than condemns.
    minUniverse: 0,
    entries: (root) => {
      const p = path.join(root, '.ci/config/content-quality-allowlist.txt');
      if (!fs.existsSync(p)) return [];
      // Plain path-per-line list, NOT BLOCKER-gated — mirrors load_allowlist()
      // in .ci/scripts/quality/check-content-quality.sh.
      return fs
        .readFileSync(p, 'utf-8')
        .split('\n')
        .map((line, i) => ({ entry: line.trim(), blocker: '', line: i + 1 }))
        .filter((e) => e.entry !== '' && !e.entry.startsWith('#'));
    },
    universe: (root) => {
      if (!fs.existsSync(path.join(root, 'packages'))) return null;
      const p = path.join(root, '.ci/config/content-quality-allowlist.txt');
      const names = new Set<string>();
      if (fs.existsSync(p)) {
        for (const raw of fs.readFileSync(p, 'utf-8').split('\n')) {
          const line = raw.trim();
          if (!line || line.startsWith('#')) continue;
          if (fs.existsSync(path.join(root, line))) names.add(line);
        }
      }
      return { names, source: `${names.size} allowlisted paths that still exist` };
    },
    why: (entry) =>
      `"${entry}" does not exist; .ci/scripts/quality/check-content-quality.sh can never match a file that is not there, so this entry excludes nothing.`,
    fix: (entry, e) => [
      `remove line ${e.line} ("${entry}") from .ci/config/content-quality-allowlist.txt, then: npm run check:ci-content-quality`,
    ],
  },
  {
    id: 'overrides',
    file: 'package.json',
    // WARN, never FAIL, and never auto-removed. An npm override is prophylactic
    // as much as reactive: it constrains what npm MAY resolve tomorrow, not only
    // what is installed today. "Absent from the lockfile right now" is therefore
    // not proof the guard is worthless — deleting one silently re-opens the hole
    // the next time a transitive drags the package back in. Being wrong here is
    // a security regression, so a human decides.
    tier: 'warn',
    minUniverse: 100,
    entries: (root) => {
      const pkgPath = path.join(root, 'package.json');
      if (!fs.existsSync(pkgPath)) return [];
      const raw = fs.readFileSync(pkgPath, 'utf-8');
      let pkg: { overrides?: Record<string, unknown> };
      try {
        pkg = JSON.parse(raw);
      } catch {
        return [];
      }
      const lines = raw.split('\n');
      return Object.keys(pkg.overrides ?? {}).map((key) => {
        const needle = `"${key}":`;
        // +1 so the reported line is inside the overrides block, not _overridesReasons.
        const idx = lines.findIndex((l, i) => l.includes(needle) && i > 0);
        return { entry: key, blocker: '', line: idx >= 0 ? idx + 1 : 1 };
      });
    },
    universe: lockfilePackageNames,
    normalize: (entry) => {
      // Three key shapes occur in the live file:
      //   keyed:   "brace-expansion@^1.1.7"  -> strip the trailing @<range>
      //   aliased: "inflight": "npm:@isaacs/inflight@^1.0.1" -> probe both names
      //   nested:  "@grpc/proto-loader": { … } -> outer key only
      const at = entry.lastIndexOf('@');
      const base = at > 0 ? entry.slice(0, at) : entry;
      return [entry, base];
    },
    why: (entry, u) => `"${entry}" resolves to 0 nodes in the lockfile (oracle: ${u.source}).`,
    fix: (entry) => [
      `if genuinely dead: npm pkg delete 'overrides["${entry}"]' '_overridesReasons["${entry}"]'`,
      `if it guards against future re-entry: start its reason with "BLOCKER: preventive —" and this probe stops reporting it`,
    ],
  },
];

// ---------------------------------------------------------------------------

function main(): void {
  const args = process.argv.slice(2);
  const jsonMode = args.includes('--json');
  const probeIdx = args.indexOf('--probe');
  const only = probeIdx >= 0 ? args[probeIdx + 1] : null;

  let probes = PROBES;
  if (only) {
    probes = PROBES.filter((p) => p.id === only);
    if (probes.length === 0) {
      console.error(
        `${RED}✗${NC} unknown probe "${only}". Known: ${PROBES.map((p) => p.id).join(', ')}`
      );
      process.exit(2);
    }
  }

  // An override whose reason opens with "preventive" is a deliberate forward
  // guard, not rot; honour that annotation instead of re-litigating it monthly.
  const preventive = new Set<string>();
  const pkgPath = path.join(CONSOLE_ROOT, 'package.json');
  if (fs.existsSync(pkgPath)) {
    try {
      const reasons =
        (JSON.parse(fs.readFileSync(pkgPath, 'utf-8'))._overridesReasons as Record<
          string,
          string
        >) ?? {};
      for (const [k, v] of Object.entries(reasons)) {
        if (/^BLOCKER:\s*preventive\b/i.test(v)) preventive.add(k);
      }
    } catch {
      /* handled by the overrides probe's own guard */
    }
  }

  const result = runProbes(probes, CONSOLE_ROOT);
  result.findings = result.findings.filter(
    (f) => !(f.probe === 'overrides' && preventive.has(f.entry))
  );

  // Cross-cutting: a `# BLOCKER:` reason with no entries beneath it. Not
  // dangerous, but it documents a suppression that is not actually in force —
  // and verifyAllBlockers() cannot see it, because it walks entries.
  const BLOCKER_FILES = [
    '.deps-upgrade-blocklist',
    '.go-deps-upgrade-blocklist',
    '.embed-assets-upgrade-blocklist',
    '.actions-upgrade-blocklist',
    '.cli-i18n-orphan-allowlist',
    '.audit-allowlist',
    '.audit-prod-allowlist',
    '.ci/config/directive-quotes-allowlist.txt',
  ];
  for (const rel of BLOCKER_FILES) {
    for (const o of findOrphanedBlockers(path.join(CONSOLE_ROOT, rel), rel)) {
      result.findings.push({
        probe: 'orphaned-blocker',
        file: o.file,
        entry: `BLOCKER: ${o.reason}…`,
        line: o.line,
        tier: 'warn',
        why: 'this BLOCKER reason has no entries beneath it, so it suppresses nothing; verifyAllBlockers() walks entries and cannot see it.',
        fix: [
          `delete the orphaned BLOCKER block at ${o.file}:${o.line}, or add back the entry it was written for`,
        ],
      });
    }
  }

  if (jsonMode) {
    console.log(JSON.stringify({ ...result, vacuous: isVacuous(result, probes.length) }, null, 2));
  } else {
    console.log(formatReport(result, { ci: process.env.CI === 'true' }));
  }

  if (isVacuous(result, probes.length)) {
    console.error(
      `\n${RED}✗${NC} vacuous run: every probe skipped while suppression entries exist — this proved nothing.`
    );
    process.exit(1);
  }
  process.exit(result.findings.some((f) => f.tier === 'fail') ? 1 : 0);
}

main();
