#!/usr/bin/env tsx
/**
 * check-suppression-liveness.ts — are our suppressions still load-bearing?
 *
 * Every allowlist / blocklist / override in this repo must carry a BLOCKER
 * reason (see docs/agent-reference/suppressions.md). That convention proves a reason EXISTS; it cannot
 * prove the reason is still TRUE. This gate closes the other half: for each
 * entry it asks whether the thing being suppressed still exists at all.
 *
 * Usage:
 *   npx tsx scripts/gates/check-suppression-liveness.ts
 *   npx tsx scripts/gates/check-suppression-liveness.ts --probe overrides
 *   npx tsx scripts/gates/check-suppression-liveness.ts --json
 *
 * Env:
 *   SUPPRESSION_LIVENESS_ROOT  test seam — treat this dir as the repo root
 *
 * Exit 0 when nothing FAIL-tier is stale; 1 otherwise, if the run was vacuous
 * (every probe skipped while entries existed), or if any PER-PROBE INPUT FLOOR
 * is unmet (see PROBE_INPUT_FLOORS below).
 *
 * The .audit-* allowlists are NOT probed here: their oracle needs a live
 * `npm audit`, and .ci/scripts/security/audit.sh already owns that check
 * (check_stale_entries). Duplicating it would mean a second, slower, network-
 * dependent oracle over the same facts.
 */

import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { collectActionRefs } from '../lib/action-refs.js';
import { parseDockerfileVersions } from '../lib/dockerfile-versions.js';
import { DEVCONTAINER_PIN_SOURCES } from '../lib/devcontainer-pin-sources.js';
import { EMBED_ASSET_SOURCES } from '../lib/embed-asset-sources.js';
import { isPolicyFileName, policyPath } from '../lib/policy-paths.js';
import {
  blockeredEntries,
  findOrphanedBlockers,
  formatReport,
  isVacuous,
  type Probe,
  runProbes,
  type Universe,
} from '../lib/suppression-liveness.js';
import { NC, RED } from '../lib/console.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = process.env.SUPPRESSION_LIVENESS_ROOT || path.join(__dirname, '..', '..');

/**
 * Absolute path of one of this gate's inputs, THROUGH THE POLICY SEAM.
 *
 * Sixteen suppression policy files moved from the repository root to
 * `.ci/policy/` in W4 P2, and this gate reads eleven of them. Routing every one
 * of those reads through policyPath() made the move a one-line change in
 * scripts/lib/policy-paths.ts rather than eleven joins to find and update -- and,
 * more to the point, it means this gate cannot be one of the readers left behind,
 * which is precisely the failure the per-probe floors below exist to catch.
 *
 * POLICY_DIR is '.ci/policy', and has been since b80552370 landed the move; this
 * gate needed no edit that day, which was the whole point. BEFORE the move the
 * same calls were a provable no-op, returning paths byte-identical to the joins
 * they replaced, which is what made the seam verifiable ahead of the move rather
 * than only after it. This paragraph said POLICY_DIR was still '' for two days
 * afterwards, and nothing noticed; `check:ci-policy-inventory` reads it now, and
 * fails on any comment in the tree that asserts a POLICY_DIR value the seam does
 * not hold.
 *
 * Files that are NOT policy (package.json, packages/json/.templates-skiplist,
 * .ci/config/content-quality-allowlist.txt) join normally; policyPath refuses an
 * unknown name loudly, so the branch is required rather than defensive.
 */
function inputPath(root: string, file: string): string {
  return isPolicyFileName(file) ? policyPath(file, root) : path.join(root, file);
}

/**
 * Repo-relative LOCATION of one of this gate's inputs, for display.
 *
 * A probe's `file` field is what every message cites, and after the W4 P2 move a
 * bare `.dead-bash-allowlist` would be a name the gate prints and a path nothing
 * holds -- the "is not at <file>" finding would name a location the probe never
 * looked at. Deriving the display string from the same seam that resolves the
 * read keeps the two from ever disagreeing.
 */
function policyRel(file: string): string {
  return isPolicyFileName(file)
    ? path.relative(CONSOLE_ROOT, policyPath(file, CONSOLE_ROOT))
    : file;
}

// --------------------------------------------------------------------------- Oracles ---------------------------------------------------------------------------

/**
 * The gate name on a two-column `.ci-parity-exempt` line, given its 1-based
 * line number. The file's entry lines are `<direction>  <gate>`, and the shared
 * parseBlockeredList takes the first whitespace-separated token.
 */
function readSecondColumn(root: string, line: number): string {
  const p = inputPath(root, '.ci-parity-exempt');
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
    // The SCOPED spelling too, `<dir>:<package>`, for the manifests that can carry one. `.deps-upgrade-blocklist` gained that form because private/account is under an operator freeze while four of its frozen packages are ALSO console's own, and a bare entry would have blinded console's freshness check
    // for them. Without this the liveness probe called every scoped entry DEAD --
    // correctly, by its own lights: no manifest declared that literal string.
    //
    // Adding the scoped name here is STRICTER than stripping the prefix in the probe would have been. `private/account:vitest` is in the universe only if private/account's own manifest declares vitest, so a typo in EITHER half is still a dead entry, where a strip would have accepted any directory name at all as long as some manifest somewhere had the package.
    const dirRel = path.relative(root, path.dirname(f)).split(path.sep).join('/');
    for (const field of [
      'dependencies',
      'devDependencies',
      'optionalDependencies',
      'peerDependencies',
    ]) {
      for (const n of Object.keys((pkg[field] as Record<string, string>) ?? {})) {
        names.add(n);
        if (dirRel) names.add(`${dirRel}:${n}`);
      }
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

/**
 * Devcontainer pin bases that are BOTH a Dockerfile ARG and a watched source.
 *
 * The intersection, not either side alone, and that is the point: a hold on a
 * base the gate does not watch suppresses nothing, and so does a hold on an ARG
 * that has been renamed or deleted. Either way the entry is a claim about a
 * suppression that cannot fire.
 */
function devcontainerPinBases(root: string): Universe | null {
  const dockerfile = path.join(root, '.devcontainer', 'Dockerfile');
  if (!fs.existsSync(dockerfile)) return null;
  let versions: Map<string, string>;
  try {
    versions = parseDockerfileVersions(fs.readFileSync(dockerfile, 'utf-8')).versions;
  } catch {
    return null;
  }
  const known = new Set(DEVCONTAINER_PIN_SOURCES.map((s) => s.base));
  const names = new Set([...versions.keys()].filter((k) => known.has(k)));
  return { names, source: `${names.size} watched devcontainer pins in .devcontainer/Dockerfile` };
}

/**
 * Tokens that still appear in some tracked Dockerfile.
 *
 * An allowlist entry naming a URL no Dockerfile fetches any more suppresses
 * nothing -- the download was removed or re-pinned, and the exemption outlived it.
 */
function dockerfileFetchTokens(root: string): Universe | null {
  let files: string[];
  try {
    files = execSync('git ls-files', { cwd: root, encoding: 'utf-8' })
      .split('\n')
      .filter((p) => /(^|\/)Dockerfile(\.|$)/.test(p));
  } catch {
    return null;
  }
  const blob = files
    .map((f) => {
      try {
        return fs.readFileSync(path.join(root, f), 'utf-8');
      } catch {
        return '';
      }
    })
    .join('\n');
  if (!blob) return null;
  const names = new Set(
    blockeredEntries(inputPath(root, '.unverified-download-allowlist'))
      .map((e) => e.entry.trim())
      .filter((t) => blob.includes(t))
  );
  return { names, source: `${files.length} tracked Dockerfile(s)` };
}

/** Every third-party action referenced by a workflow or composite action. */
function referencedActions(root: string): Universe | null {
  let refs: ReturnType<typeof collectActionRefs>;
  try {
    refs = collectActionRefs(root);
  } catch (err) {
    // A CORPUS BELOW ITS FLOOR IS AN UNAVAILABLE ORACLE, NOT A CRASH. collectActionRefs grew a vacuity floor on 2026-09-04, which is right -- a wrong root must not read as "no actions referenced, everything is dead". But it THROWS, and this probe's contract is that `null` means "cannot tell", which the caller already handles: a run whose oracles are all unavailable while entries
    // exist is declared vacuous and FAILS. So the floor's information is kept and its verdict is stronger, not weaker. Left unhandled it replaced the gate's own "vacuous" verdict with a stack trace and took the whole gate-test battery red (2026-09-05, in the twin now carried by test_gate_suppression_liveness.py).
    if (!(err instanceof Error) || !err.message.startsWith('VACUOUS:')) throw err;
    return null;
  }
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

// --------------------------------------------------------------------------- Probes ---------------------------------------------------------------------------

const listProbe = (
  id: string,
  file: string,
  universe: (root: string) => Universe | null,
  minUniverse: number,
  why: (entry: string, u: Universe) => string,
  fix: (entry: string, line: number) => string[]
): Probe => ({
  id,
  file: policyRel(file),
  tier: 'fail',
  minUniverse,
  entries: (root) => blockeredEntries(inputPath(root, file)),
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
      `no manifest declares "${entry}" (oracle: ${u.source}). scripts/gates/check-deps.ts only consults this blocklist for names \`npm outdated\` reports, and \`npm outdated\` only reports declared deps — so this entry can never suppress anything.`,
    (entry, line) => [
      `remove line ${line} ("${entry}") from .ci/policy/.deps-upgrade-blocklist, then: npm run check:deps`,
    ]
  ),
  listProbe(
    'go-deps',
    '.go-deps-upgrade-blocklist',
    goRequires,
    5,
    (entry, u) =>
      `no go.mod requires "${entry}" (oracle: ${u.source}); .ci/scripts/quality/check_go_deps.py can never consult this entry.`,
    (entry, line) => [
      `remove line ${line} ("${entry}") from .ci/policy/.go-deps-upgrade-blocklist, then: npm run check:ci-renet`,
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
      `remove line ${line} ("${entry}") from .ci/policy/.embed-assets-upgrade-blocklist, then: npm run check:ci-embed-asset-freshness`,
    ]
  ),
  // minUniverse 1, not the 3-5 its neighbours use: this inventory deliberately holds ONE entry (see scripts/lib/devcontainer-pin-sources.ts on why glab, bottom and openvscode-server are not seeded), so any higher floor would disable the probe rather than guard it.
  listProbe(
    'devcontainer-pins',
    '.devcontainer-upgrade-blocklist',
    devcontainerPinBases,
    1,
    (entry, u) =>
      `"${entry}" is not a watched devcontainer pin (oracle: ${u.source}); it is absent from .devcontainer/Dockerfile's ARGs, from scripts/lib/devcontainer-pin-sources.ts, or both.`,
    (entry, line) => [
      `remove line ${line} ("${entry}") from .ci/policy/.devcontainer-upgrade-blocklist, then: npm run check:ci-devcontainer-pins`,
    ]
  ),
  listProbe(
    'unverified-downloads',
    '.unverified-download-allowlist',
    dockerfileFetchTokens,
    1,
    (entry, u) =>
      `no tracked Dockerfile fetches "${entry}" any more (oracle: ${u.source}); the download was removed or re-pinned, so this exemption suppresses nothing.`,
    (entry, line) => [
      `remove line ${line} ("${entry}") from .ci/policy/.unverified-download-allowlist, then: npm run check:ci-unverified-downloads`,
    ]
  ),
  listProbe(
    'actions',
    '.actions-upgrade-blocklist',
    referencedActions,
    3,
    (entry, u) =>
      `no workflow or composite action uses "${entry}" (oracle: ${u.source}); scripts/gates/check-actions.ts only reports on actions it finds a \`uses:\` for.`,
    (entry, line) => [
      `remove line ${line} ("${entry}") from .ci/policy/.actions-upgrade-blocklist, then: npm run check:actions`,
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
    (entry, line) => [`remove line ${line} ("${entry}") from packages/json/.templates-skiplist`]
  ),
  {
    id: 'cli-i18n-orphan',
    file: policyRel('.cli-i18n-orphan-allowlist'),
    tier: 'fail',
    minUniverse: 50,
    entries: (root) => blockeredEntries(inputPath(root, '.cli-i18n-orphan-allowlist')),
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
      `no leaf key starts with "${entry}" (oracle: ${u.source}); the prefix exempts nothing from the orphan report in scripts/gates/check-cli-i18n-key-usage.ts.`,
    fix: (entry, e) => [
      `remove line ${e.line} ("${entry}") from .ci/policy/.cli-i18n-orphan-allowlist, then: npm run check:ci-i18n-cli-key-usage`,
    ],
  },
  {
    id: 'dead-bash-allowlist',
    file: policyRel('.dead-bash-allowlist'),
    tier: 'fail',
    // Structural guard, not a count floor: universe() returns null when the shell tree is missing. A count floor would be the rejected ratio guard, and every entry CAN legitimately go stale at once.
    minUniverse: 0,
    entries: (root) => blockeredEntries(inputPath(root, '.dead-bash-allowlist')),
    universe: (root) => {
      if (!fs.existsSync(path.join(root, '.ci'))) return null;
      // A glob: root is live if the directory still exists; a dispatch: prefix is live if some shell function still starts with it; a manual: file is live if the script is still there.
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
        for (const seg of rel
          .split('/')
          .slice(0, -1)
          .map((_, i, a) => `${a.slice(0, i + 1).join('/')}/`)) {
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
      `remove line ${e.line} ("${entry}") from .ci/policy/.dead-bash-allowlist, then: npm run check:ci-dead-bash`,
    ],
  },
  {
    id: 'parity-exempt',
    file: policyRel('.ci-parity-exempt'),
    tier: 'fail',
    // Structural guard, not a count floor: universe() returns null when there are no workflows to read, and every entry can legitimately go stale at once (a batch of PR-context gates being retired together).
    minUniverse: 0,
    // The entry lines carry a leading direction column, so the shared parser's
    // first-token rule would read "ci-only" as the entry. Split it off here;
    // the BLOCKER association and validation stay with the shared parser.
    entries: (root) =>
      blockeredEntries(inputPath(root, '.ci-parity-exempt')).map((e) => ({
        ...e,
        entry:
          e.entry === 'ci-only' || e.entry === 'local-only'
            ? readSecondColumn(root, e.line)
            : e.entry,
      })),
    universe: (root) => {
      // An exemption is live only while the thing it exempts is still invoked by a workflow. Once the step is deleted the entry is a permanent hole in the "a local run catches CI failures" promise, guarding nothing.
      //
      // ONLY THE ci-only DIRECTION IS ORACLED HERE. A local-only entry is live when the LOCAL gate set still runs it, which is a different question
      // with a different oracle (scripts/ci-runner/manifest.ts). There are no
      // local-only entries today; the day one appears, this probe must grow the second oracle rather than judge it against the workflow tree, which would condemn it for the very asymmetry it declares.
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
        // BOTH EXTENSIONS. This read `\.sh` alone, and W7 P4 is repointing these very workflow lines at Python ports: the moment a step ran `check_branch.py` the oracle stopped seeing any invocation of it and declared the gate's own exemption DEAD, telling the reader to delete the line that keeps a live gate excused. Nine entries at once on 2026-09-08.
        for (const m of text.matchAll(/(\.ci\/scripts\/[\w./-]+\.(?:sh|py))/g)) names.add(m[1]);
      }
      return { names, source: `${files.length} workflows, ${names.size} gate invocations` };
    },
    why: (entry, u) =>
      `no workflow invokes "${entry}" any more (oracle: ${u.source}); the exemption holds a hole open for a gate that no longer runs in CI.`,
    fix: (entry, e) => [
      `remove line ${e.line} ("${entry}") from .ci/policy/.ci-parity-exempt, then: npm run check:ci-parity`,
    ],
  },
  {
    id: 'content-quality',
    file: '.ci/config/content-quality-allowlist.txt',
    tier: 'fail',
    // The oracle here is per-path existence, so a count floor would be exactly the rejected ratio guard ("all entries dead ⇒ suspicious") — and all entries CAN legitimately be dead, which is the whole point. The trust guard is instead structural: universe() returns null when the content tree is absent, so a partial checkout skips rather than condemns.
    minUniverse: 0,
    entries: (root) => {
      const p = path.join(root, '.ci/config/content-quality-allowlist.txt');
      if (!fs.existsSync(p)) return [];
      // Plain path-per-line list, NOT BLOCKER-gated — mirrors load_allowlist() in .ci/scripts/quality/check-content-quality.sh.
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
    // WARN, never FAIL, and never auto-removed. An npm override is prophylactic as much as reactive: it constrains what npm MAY resolve tomorrow, not only what is installed today. "Absent from the lockfile right now" is therefore not proof the guard is worthless — deleting one silently re-opens the hole the next time a transitive drags the package back in. Being wrong here is a
    // security regression, so a human decides.
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
      // Three key shapes occur in the live file: keyed: "brace-expansion@^1.1.7" -> strip the trailing @<range> aliased: "inflight": "npm:@isaacs/inflight@^1.0.1" -> probe both names
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

// --------------------------------------------------------------------------- Per-probe input floors ---------------------------------------------------------------------------
//
// WHY TOTALS ARE NOT ENOUGH. isVacuous() in scripts/lib/suppression-liveness.ts
// keys on entriesChecked === 0 across the WHOLE run. That catches a run which
// asserted nothing at all, and misses the failure that actually happens: ONE list going empty while the other eleven stay full. The total stays healthy, the report still says "every suppression entry is still load-bearing", and the probe over the emptied list has silently stopped being a check.
//
// The way that happens is not somebody deleting a file on purpose. It is a reader looking in the wrong place -- the exact hazard the .ci/policy/ move creates, since every mechanism here treats "file not found" as "zero entries", which is indistinguishable from "nothing is suppressed".
//
// So there are two floors per probe, and they catch the two different shapes:
//
// PRESENCE. The probe's declared file must EXIST. A file that has moved away
//   from where its probe looks is caught here, whatever its contents were.
//
// ENTRIES. If the file exists, it must yield at least minEntries entries. A list emptied IN PLACE -- truncated, or its entries commented out by a bad edit -- is caught here.
//
// minEntries is 1 for every probe whose list carries entries, and 0 for the three that are DELIBERATELY empty. That zero is a policy statement ("this list is allowed to hold nothing"), not a hand-typed population count, so it does not fall foul of the corpus-derived-floors rule: no floor here goes red when a list legitimately shrinks, only when it stops being readable at all.
// Measured 2026-09-06: 12 probes, 87 entries.

interface ProbeInputFloor {
  /** Smallest entry count that makes this probe's verdict mean anything. */
  minEntries: number;
  /** Required when minEntries is 0: why holding nothing is the correct state. */
  emptyIsCorrect?: string;
}

const PROBE_INPUT_FLOORS: Record<string, ProbeInputFloor> = {
  deps: { minEntries: 1 },
  'go-deps': { minEntries: 1 },
  'embed-assets': {
    minEntries: 0,
    emptyIsCorrect:
      'the file says "Empty by default -- nothing is held; every pin tracks upstream"; an entry here holds a renet-embedded binary back',
  },
  'devcontainer-pins': {
    minEntries: 0,
    emptyIsCorrect:
      'same shape as embed-assets: every devcontainer pin tracks upstream unless something is genuinely broken',
  },
  'unverified-downloads': { minEntries: 1 },
  actions: {
    minEntries: 0,
    emptyIsCorrect:
      'no action is currently held back from auto-upgrade; the file carries its format comment and nothing else',
  },
  'templates-skiplist': { minEntries: 1 },
  'cli-i18n-orphan': { minEntries: 1 },
  'dead-bash-allowlist': { minEntries: 1 },
  'parity-exempt': { minEntries: 1 },
  'content-quality': { minEntries: 1 },
  overrides: {
    minEntries: 0,
    emptyIsCorrect:
      'the "file" here is package.json and its entries are the `overrides` keys, which a healthy repository is entitled to hold none of. An emptied overrides block is a package.json edit, visible in review and in the lockfile diff, not a suppression file quietly going missing -- and this probe is warn-tier, so it condemns nothing on its own',
  },
};

/**
 * Is `root` a full checkout of this repository, rather than a test fixture?
 *
 * The PRESENCE floor cannot run against a fixture: the gate's own test suite
 * builds minimal roots that carry one or two suppression files on purpose, and
 * failing them for the other fourteen would be asserting that a fixture must be
 * a whole repository. So presence is enforced only where absence is genuinely a
 * defect.
 *
 * Three markers, from three different subtrees, all of which the real root has
 * and no fixture in this repo has: .ci/rediacc_ci/tests/gates/test_gate_suppression_liveness.py
 * builds roots with package.json and .github but no `.ci`, and
 * test-gate-anti-vacuity.sh builds one with `.ci/scripts` and `scripts` but no
 * package.json and no `.github`. Neither is full, both for a different reason,
 * which is what keeps this predicate from being satisfiable by accident.
 *
 * A fixture that ever DOES look full gets the floor applied to it and fails
 * loudly, which is the safe direction: the alternative is a floor that quietly
 * stops applying to the real tree too.
 */
function isFullCheckout(root: string): boolean {
  return (
    fs.existsSync(path.join(root, 'package.json')) &&
    fs.existsSync(path.join(root, '.ci', 'scripts', 'quality')) &&
    fs.existsSync(path.join(root, '.github', 'workflows'))
  );
}

interface ProbeInput {
  probe: string;
  file: string;
  exists: boolean;
  entries: number;
  floor: number;
  status: 'checked' | 'empty-by-design' | 'starved' | 'file-missing';
}

/** Measure every probe's input and judge it against its floor. */
function measureProbeInputs(probes: Probe[], root: string): ProbeInput[] {
  const full = isFullCheckout(root);
  return probes.map((probe) => {
    const floor = PROBE_INPUT_FLOORS[probe.id];
    if (!floor) {
      // A probe with no declared floor is a registration the author forgot, and it is exactly the probe that would then be free to check nothing. Treat an undeclared probe as requiring at least one entry rather than as exempt: silence is never the safe default here.
      throw new Error(
        `probe "${probe.id}" has no entry in PROBE_INPUT_FLOORS. Declare its minEntries ` +
          `(and, if 0, why holding nothing is the correct state) in scripts/gates/check-suppression-liveness.ts.`
      );
    }
    const abs = inputPath(root, probe.file);
    const exists = fs.existsSync(abs);
    const entries = probe.entries(root).length;

    let status: ProbeInput['status'];
    if (!exists) {
      status = full ? 'file-missing' : 'checked';
    } else if (entries < floor.minEntries) {
      status = 'starved';
    } else if (entries === 0) {
      status = 'empty-by-design';
    } else {
      status = 'checked';
    }
    return { probe: probe.id, file: probe.file, exists, entries, floor: floor.minEntries, status };
  });
}

/** The per-probe inventory block. Deliberately free of the string "FAIL": the
 *  verdict belongs in the findings, this is the input census. */
function formatProbeInputs(inputs: ProbeInput[]): string {
  const out: string[] = ['Per-probe inputs', '-'.repeat(60)];
  const width = Math.max(...inputs.map((i) => i.probe.length));
  for (const i of inputs) {
    const label =
      i.status === 'file-missing'
        ? 'MISSING FILE'
        : i.status === 'starved'
          ? 'BELOW FLOOR'
          : i.status === 'empty-by-design'
            ? 'empty by design'
            : 'ok';
    out.push(
      `  ${i.probe.padEnd(width)}  ${String(i.entries).padStart(3)} entries  floor ${i.floor}  ${label}  ${i.file}`
    );
  }
  const total = inputs.reduce((n, i) => n + i.entries, 0);
  out.push(`  ${inputs.length} probe(s), ${total} entr(ies) declared across their files`);
  out.push('');
  return out.join('\n');
}

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

  // An override whose reason opens with "preventive" is a deliberate forward guard, not rot; honour that annotation instead of re-litigating it monthly.
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

  // Per-probe input floors. Measured BEFORE the findings are rendered so the census is visible even on a run that then fails for a stale entry.
  const probeInputs = measureProbeInputs(probes, CONSOLE_ROOT);
  for (const i of probeInputs) {
    if (i.status === 'file-missing') {
      result.findings.push({
        probe: i.probe,
        file: i.file,
        entry: '(the file itself)',
        line: 1,
        tier: 'fail',
        why: `the "${i.probe}" probe's suppression file is not at ${i.file}, so it parsed zero entries and asserted nothing. In this repo an unreadable suppression file is indistinguishable from an empty one, which reads as "nothing is suppressed" -- the probe has stopped being a check rather than reporting a clean list.`,
        fix: [
          `if the file moved, point the probe at its new location (scripts/lib/policy-paths.ts is the seam for that)`,
          `if the mechanism is genuinely gone, delete its probe from scripts/gates/check-suppression-liveness.ts and its row from PROBE_INPUT_FLOORS`,
        ],
      });
    } else if (i.status === 'starved') {
      result.findings.push({
        probe: i.probe,
        file: i.file,
        entry: '(the whole list)',
        line: 1,
        tier: 'fail',
        why: `the "${i.probe}" probe parsed ${i.entries} entr(ies) from ${i.file}; its floor is ${i.floor}. An emptied list makes this probe silent while the run's totals stay healthy on the other probes -- the exact hiding place per-probe floors exist to close.`,
        fix: [
          `restore the entries, or -- if the list is now legitimately empty -- set its minEntries to 0 in PROBE_INPUT_FLOORS with an emptyIsCorrect reason saying why holding nothing is right`,
        ],
      });
    }
  }

  // Cross-cutting: a `# BLOCKER:` reason with no entries beneath it. Not dangerous, but it documents a suppression that is not actually in force — and verifyAllBlockers() cannot see it, because it walks entries.
  const BLOCKER_FILES = [
    '.deps-upgrade-blocklist',
    '.go-deps-upgrade-blocklist',
    '.embed-assets-upgrade-blocklist',
    '.devcontainer-upgrade-blocklist',
    '.unverified-download-allowlist',
    '.actions-upgrade-blocklist',
    '.cli-i18n-orphan-allowlist',
    '.audit-allowlist',
    '.audit-prod-allowlist',
    '.ci/config/directive-quotes-allowlist.txt',
  ];
  for (const rel of BLOCKER_FILES) {
    for (const o of findOrphanedBlockers(inputPath(CONSOLE_ROOT, rel), policyRel(rel))) {
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
    console.log(
      JSON.stringify({ ...result, probeInputs, vacuous: isVacuous(result, probes.length) }, null, 2)
    );
  } else {
    console.log(formatProbeInputs(probeInputs));
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
