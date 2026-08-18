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
 * version, while arm64 extracted Debian bookworm's package — 3.17.1 against a
 * declared 4.2.x. Every gate stayed green. The freshness gate compared the
 * Dockerfile ARG against upstream and saw 4.2.x on both sides; the credits gate
 * compared inventories that both said 4.2.x. Nothing anywhere carried an
 * architecture dimension, so a per-arch divergence was structurally invisible.
 *
 * Checks:
 *   - every component covers the same architecture set (no arch silently dropped)
 *   - every arch entry declares a build method
 *   - download-built arches pin an https url AND a sha256
 *   - source/cross-built components pin an immutable commit, not just a tag
 *   - class is one of base|cluster (it decides which GOOS embeds the asset)
 *
 * Usage:
 *   npx tsx scripts/check-embed-arch-parity.ts
 *   npm run check:ci-embed-arch-parity
 *
 * Path override (used by the gate test with fixtures):
 *   EMBED_PARITY_LOCKFILE
 *
 * Exit codes:
 *   0 - parity holds, or the renet submodule is not checked out
 *   1 - a missing arch, an unpinned fetch, or an incoherent entry
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GREEN, NC, RED, YELLOW } from './utils/console.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');

const LOCKFILE =
  process.env.EMBED_PARITY_LOCKFILE ??
  path.join(CONSOLE_ROOT, 'private/renet/embed-assets.lock.json');

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

function main(): void {
  if (!fs.existsSync(LOCKFILE)) {
    console.log(`${YELLOW}⊘ embed lockfile not present — renet submodule not checked out${NC}`);
    return;
  }

  const lock = JSON.parse(fs.readFileSync(LOCKFILE, 'utf-8')) as {
    components: Record<string, Component>;
  };
  const components = Object.entries(lock.components ?? {});
  const errors: string[] = [];

  // Anti-vacuity: an empty lockfile must never report parity.
  if (components.length === 0) {
    console.error(`${RED}✗ the embed lockfile declares no components — this gate is blind${NC}`);
    process.exit(1);
  }

  // The arch set of the first component is the reference; every other component
  // must match it exactly. A component quietly losing an arch is the shape of the
  // defect this gate is for.
  const reference = Object.keys(components[0][1].arches ?? {}).sort();
  if (reference.length === 0) {
    console.error(`${RED}✗ component '${components[0][0]}' declares no architectures${NC}`);
    process.exit(1);
  }

  let archEntries = 0;
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
    `${GREEN}✓ ${components.length} components x [${reference.join(', ')}] = ${archEntries} arch entries, all pinned${NC}`
  );
}

main();
