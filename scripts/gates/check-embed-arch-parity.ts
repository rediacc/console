#!/usr/bin/env node
/**
 * Embed arch-parity gate.
 *
 * Asserts that every component the embed lockfile declares is present for EVERY
 * architecture it declares, and that the per-arch entries are internally
 * coherent. This is the check that did not exist when arm64 criu quietly became a
 * different piece of software from amd64 criu.
 *
 * THE FAILURE THIS EXISTS FOR: amd64 built criu from source at the pinned
 * version, while arm64 extracted Debian bookworm's package: 3.17.1 against a
 * declared 4.2.x. Every gate stayed green. The freshness gate compared the
 * Dockerfile ARG against upstream and saw 4.2.x on both sides; the credits gate
 * compared inventories that both said 4.2.x. Nothing anywhere carried an
 * architecture dimension, so a per-arch divergence was structurally invisible.
 *
 * Checks:
 *   - every component covers the same architecture set (no arch silently dropped)
 *   - every arch entry declares a build method
 *   - download-built arches pin an https url AND a sha256
 *   - a download url carries the component's OWN version (v2.1.18 in the url
 *     under a 2.1.22 version is a finding), and its sha256 equals the digest
 *     the Dockerfile verifies at build time, ARG <NAME>_SHA256_<ARCH>
 *   - source/cross-built components pin an immutable commit, not just a tag
 *   - class is one of base|cluster (it decides which GOOS embeds the asset)
 *
 * Usage:
 *   npx tsx scripts/gates/check-embed-arch-parity.ts
 *   npm run check:ci-embed-arch-parity
 *
 * Path override (used by the gate test with fixtures):
 *   EMBED_PARITY_LOCKFILE
 * The Dockerfile is read from BESIDE the lockfile (<dir>/Dockerfile), so a
 * fixture copies both into one directory and a mutation of either is seen.
 *
 * THE SECOND FAILURE THIS EXISTS FOR: zot went 2.1.18 -> 2.1.20 -> 2.1.21 and
 * the lockfile's version, upstream url, mirror url and the Dockerfile ARGs all
 * moved, while arches.<arch>.url and .sha256 stayed at v2.1.18. The checks
 * above only looked at digest SHAPE, and a stale digest is perfectly shaped.
 *
 * Exit codes:
 *   0 - parity holds, or the renet submodule is not checked out
 *   1 - a missing arch, an unpinned fetch, an incoherent entry, a download
 *       url or digest that disagrees with the version or the Dockerfile, or a
 *       Dockerfile that cannot be read while a download arch needs it
 *
 * ---- gate ----
 * step: Check embed arch parity
 * needs: node, submodules
 * lane: quality-go
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GREEN, NC, RED, YELLOW } from '../lib/console.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..', '..');

const LOCKFILE =
  process.env.EMBED_PARITY_LOCKFILE ??
  path.join(CONSOLE_ROOT, 'private/renet/embed-assets.lock.json');

const DOCKERFILE = path.join(path.dirname(LOCKFILE), 'Dockerfile');

const VALID_CLASSES = new Set(['base', 'cluster']);
const SHA256_RE = /^[0-9a-f]{64}$/;
const COMMIT_RE = /^[0-9a-f]{40}$/;

interface ArchEntry {
  build?: string;
  url?: string;
  sha256?: string;
}

interface Component {
  version?: string;
  class?: string;
  arches?: Record<string, ArchEntry>;
  source?: { kind?: string; commit?: string; sha256?: string; url?: string };
}

/**
 * Every `ARG NAME=value` the Dockerfile declares, by name. One name may be
 * declared in several stages, so every value is kept: two stages disagreeing
 * is itself a finding.
 */
function dockerfileArgs(text: string): Map<string, Set<string>> {
  const args = new Map<string, Set<string>>();
  for (const line of text.split('\n')) {
    const m = /^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)=(\S+)\s*$/.exec(line);
    if (!m) continue;
    const value = m[2].replace(/^(["'])(.*)\1$/, '$2');
    const seen = args.get(m[1]) ?? new Set<string>();
    seen.add(value);
    args.set(m[1], seen);
  }
  return args;
}

/**
 * The general mapping from a lockfile component to its Dockerfile ARG prefix:
 * the component name upper-cased (zot -> ZOT_SHA256_AMD64, k3s ->
 * K3S_SHA256_ARM64). Derived, not tabled, so a new download component is mapped
 * on arrival, and one the rule cannot map is reported as such below.
 */
function argName(component: string, field: string, arch?: string): string {
  const base = `${component.toUpperCase().replace(/[^A-Z0-9]/g, '_')}_${field}`;
  return arch ? `${base}_${arch.toUpperCase()}` : base;
}

const escapeRe = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * True when the decoded url names `version` as a whole token, optionally
 * v-prefixed. Bounded on both sides so 2.1.2 does not match inside v2.1.22 and
 * 2.1.22 does not match inside 12.1.22. The url is decoded first so k3s's
 * `+k3s1` matches whether the url spells it `+` or `%2B`.
 */
function urlCarriesVersion(url: string, version: string): boolean {
  let decoded = url;
  try {
    decoded = decodeURIComponent(url);
  } catch {
    // A malformed escape leaves the raw url, which still matches a literal version.
  }
  const re = new RegExp(`(?<![0-9A-Za-z.+])v?${escapeRe(version)}(?![0-9A-Za-z+]|\\.[0-9])`);
  return re.test(decoded);
}

function main(): void {
  if (!fs.existsSync(LOCKFILE)) {
    console.log(`${YELLOW}⊘ embed lockfile not present; renet submodule not checked out${NC}`);
    return;
  }

  const lock = JSON.parse(fs.readFileSync(LOCKFILE, 'utf-8')) as {
    components: Record<string, Component>;
  };
  const components = Object.entries(lock.components ?? {});
  const errors: string[] = [];

  // Anti-vacuity: an empty lockfile must never report parity.
  if (components.length === 0) {
    console.error(`${RED}✗ the embed lockfile declares no components; this gate is blind${NC}`);
    process.exit(1);
  }

  // The arch set of the first component is the reference; every other component
  // must match it exactly. A component quietly losing an arch is the shape of the defect this gate is for.
  const reference = Object.keys(components[0][1].arches ?? {}).sort();
  if (reference.length === 0) {
    console.error(`${RED}✗ component '${components[0][0]}' declares no architectures${NC}`);
    process.exit(1);
  }

  // The Dockerfile is read lazily: a lockfile with no download arch needs none,
  // and one that has a download arch and no readable Dockerfile is a finding.
  let dockerArgs: Map<string, Set<string>> | null | undefined;
  const loadDockerArgs = (): Map<string, Set<string>> | null => {
    if (dockerArgs === undefined) {
      try {
        dockerArgs = dockerfileArgs(fs.readFileSync(DOCKERFILE, 'utf-8'));
      } catch (e) {
        errors.push(
          `cannot read ${path.relative(CONSOLE_ROOT, DOCKERFILE)} (${(e as Error).message}); ` +
            'the download digests cannot be cross-checked, so this is a failure, not a skip'
        );
        dockerArgs = null;
      }
    }
    return dockerArgs;
  };

  let archEntries = 0;
  let downloadsCrossChecked = 0;
  for (const [name, c] of components) {
    if (!c.class || !VALID_CLASSES.has(c.class)) {
      errors.push(`${name}: class '${c.class ?? '<missing>'}' is not one of base|cluster`);
    }
    if (!c.version) errors.push(`${name}: no version`);

    const arches = Object.keys(c.arches ?? {}).sort();
    if (arches.join(',') !== reference.join(',')) {
      errors.push(
        `${name}: architectures [${arches.join(', ') || '<none>'}] != [${reference.join(', ')}] declared by '${components[0][0]}'`
      );
    }

    let needsCommit = false;
    for (const [arch, entry] of Object.entries(c.arches ?? {})) {
      archEntries++;
      const where = `${name}/${arch}`;
      if (!entry.build) {
        errors.push(`${where}: no build method`);
        continue;
      }
      if (entry.build === 'download') {
        if (!entry.url?.startsWith('https://')) {
          errors.push(
            `${where}: build=download but url is not https (${entry.url ?? '<missing>'})`
          );
        }
        if (!entry.sha256 || !SHA256_RE.test(entry.sha256)) {
          errors.push(`${where}: build=download but sha256 is missing or malformed`);
        }
        if (entry.url && c.version && !urlCarriesVersion(entry.url, c.version)) {
          errors.push(
            `${where}: url does not carry the component version: lockfile url '${entry.url}', ` +
              `expected it to name version '${c.version}' (e.g. .../v${c.version}/...). ` +
              'Fix the url AND the sha256 together; a stale url pins a stale digest.'
          );
        }
        const args = loadDockerArgs();
        if (args) {
          const shaArg = argName(name, 'SHA256', arch);
          const declared = args.get(shaArg);
          if (!declared) {
            errors.push(
              `${where}: no 'ARG ${shaArg}=<digest>' in ${path.relative(CONSOLE_ROOT, DOCKERFILE)}; ` +
                'the lockfile sha256 cannot be cross-checked against what the build verifies'
            );
          } else if (declared.size > 1) {
            errors.push(
              `${where}: ARG ${shaArg} is declared with ${declared.size} different values ` +
                `(${[...declared].join(', ')}); the stages disagree`
            );
          } else {
            const expected = [...declared][0];
            if (entry.sha256 !== expected) {
              errors.push(
                `${where}: sha256 differs from the Dockerfile: lockfile '${entry.sha256 ?? '<missing>'}', ` +
                  `expected '${expected}' (ARG ${shaArg})`
              );
            }
          }
          const versionArg = argName(name, 'VERSION');
          const versions = args.get(versionArg);
          if (versions && c.version) {
            for (const v of versions) {
              if (v !== c.version) {
                errors.push(
                  `${where}: version differs from the Dockerfile: lockfile '${c.version}', ` +
                    `expected '${v}' (ARG ${versionArg})`
                );
              }
            }
          }
          downloadsCrossChecked++;
        }
      } else if (entry.build === 'source' || entry.build === 'cross') {
        needsCommit = true;
      } else {
        errors.push(`${where}: unknown build method '${entry.build}'`);
      }
    }

    // Anything built from source must pin content, not a movable ref. A git tag
    // can be repointed; a GitHub /archive/ tarball is regenerable.
    if (needsCommit) {
      const src = c.source ?? {};
      const hasCommit = src.commit && COMMIT_RE.test(src.commit);
      const hasDigest = src.sha256 && SHA256_RE.test(src.sha256);
      if (!hasCommit && !hasDigest) {
        errors.push(
          `${name}: built from source but pins neither a 40-char commit nor a tarball sha256`
        );
      }
    }
  }

  if (errors.length > 0) {
    console.error(`${RED}✗ embed arch parity failed:${NC}`);
    for (const e of errors) console.error(`  ${e}`);
    console.error(`\n${YELLOW}Source of truth: ${path.relative(CONSOLE_ROOT, LOCKFILE)}${NC}`);
    process.exit(1);
  }

  console.log(
    `${GREEN}✓ ${components.length} components x [${reference.join(', ')}] = ${archEntries} arch entries, all pinned; ` +
      `${downloadsCrossChecked} download arch(es) match their version and the Dockerfile digest${NC}`
  );
}

main();
