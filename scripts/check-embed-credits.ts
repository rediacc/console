#!/usr/bin/env node
/**
 * Embed attribution consistency gate.
 *
 * private/renet/embed-assets.lock.json is the single source of truth for every
 * binary renet embeds and conveys. This gate asserts two things:
 *
 *   1. The Dockerfile's `ARG <BASE>_VERSION=` pins agree with the lockfile. The
 *      Dockerfile keeps its own defaults so `docker build` works standalone, so
 *      this is what stops the two from drifting.
 *   2. The generated attribution artifacts are not stale:
 *        private/renet/pkg/embed/credits_data.go
 *        packages/cli/src/data/third-party-credits.json
 *
 * WHAT CHANGED AND WHY: this gate used to compare each inventory's VERSION field
 * against the Dockerfile ARG, independently, and nothing else. It therefore could
 * not see that the two inventories had already drifted on LICENCE TEXT — all
 * three CSI sidecars carried a generic "run as a host process (spec 09 CSI
 * driver)" line in the CLI mirror while credits.go carried three distinct, more
 * accurate ones. Comparing more fields would have caught that one instance;
 * generating both artifacts from one source removes the whole class, so this gate
 * now checks derivation rather than agreement.
 *
 * Usage:
 *   npx tsx scripts/check-embed-credits.ts
 *   npm run check:ci-embed-credits
 *
 * Path override (used by the gate test with fixtures):
 *   EMBED_CREDITS_DOCKERFILE
 *
 * Exit codes:
 *   0 - the Dockerfile agrees with the lockfile and the artifacts are current,
 *       or the renet submodule is not checked out (nothing to attribute)
 *   1 - a drifted pin or a stale generated artifact
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  type Lockfile,
  LOCKFILE,
  generatedArtifacts,
} from './generate-embed-credits.js';
import { parseDockerfileVersions } from './lib/dockerfile-versions.js';
import { GREEN, NC, RED, YELLOW } from './utils/console.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');

const DOCKERFILE =
  process.env.EMBED_CREDITS_DOCKERFILE ?? path.join(CONSOLE_ROOT, 'private/renet/Dockerfile');

function main(): void {
  if (!fs.existsSync(LOCKFILE) || !fs.existsSync(DOCKERFILE)) {
    console.log(`${YELLOW}⊘ renet submodule not checked out — nothing to attribute${NC}`);
    return;
  }

  const lock = JSON.parse(fs.readFileSync(LOCKFILE, 'utf-8')) as Lockfile;
  const errors: string[] = [];

  const components = Object.entries(lock.components);
  if (components.length === 0) {
    console.error(`${RED}✗ the embed lockfile declares no components — this gate is blind${NC}`);
    process.exit(1);
  }

  // 1. Dockerfile ARG pins must equal the lockfile versions.
  const { versions, conflicts } = parseDockerfileVersions(fs.readFileSync(DOCKERFILE, 'utf-8'));
  errors.push(...conflicts);
  if (versions.size === 0) {
    console.error(`${RED}✗ no ARG <BASE>_VERSION pins found in the Dockerfile — parse failed${NC}`);
    process.exit(1);
  }
  for (const [base, c] of components) {
    const pinned = versions.get(base);
    if (pinned === undefined) {
      errors.push(`Dockerfile: no ARG ${base.toUpperCase()}_VERSION for lockfile component '${base}'`);
    } else if (pinned !== c.version) {
      errors.push(
        `Dockerfile ARG ${base.toUpperCase()}_VERSION='${pinned}' != lockfile '${base}' version '${c.version}'`
      );
    }
  }

  // 1b. ATTRIBUTION URLS MUST NAME THE VERSION ACTUALLY SHIPPED.
  //
  // Found by review on PR #551 after a k3s/zot bump moved `version` and left
  // upstreamSourceUrl/plannedMirrorUrl pointing at the PREVIOUS release. These
  // are not decorative: credits.ts prints them verbatim as "Source:" and
  // "Mirror:", and this file exists to satisfy Apache-2.0 s4 source
  // attribution for the embedded binaries. A URL naming a different release
  // than the one shipped is a compliance defect, not a typo -- it offers the
  // user a source archive that is not the source of what they are running.
  //
  // Substring, not equality, because the two URL shapes differ (a GitHub
  // archive path repeats the version, a mirror names a tarball) and the point
  // is only that neither can still be naming a version we no longer ship.
  for (const [base, c] of components) {
    for (const field of ['upstreamSourceUrl', 'plannedMirrorUrl'] as const) {
      const url = c[field];
      if (url === '') continue;
      if (!url.includes(c.version)) {
        errors.push(
          `${base}: ${field} does not name version '${c.version}' — ${url}`
        );
      }
    }
  }

  // 2. Generated artifacts must be current.
  for (const [file, want] of generatedArtifacts(lock)) {
    const have = fs.existsSync(file) ? fs.readFileSync(file, 'utf-8') : '';
    if (have !== want) {
      errors.push(
        `${path.relative(CONSOLE_ROOT, file)} is stale — regenerate with: npx tsx scripts/generate-embed-credits.ts`
      );
    }
  }

  if (errors.length > 0) {
    console.error(`${RED}✗ embed attribution is inconsistent:${NC}`);
    for (const e of errors) console.error(`  ${e}`);
    console.error(
      `\n${YELLOW}The lockfile is the source of truth: private/renet/embed-assets.lock.json${NC}`
    );
    process.exit(1);
  }

  console.log(
    `${GREEN}✓ ${components.length} embedded components: Dockerfile pins and generated attribution match the lockfile${NC}`
  );
}

main();
