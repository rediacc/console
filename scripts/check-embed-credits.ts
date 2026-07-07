#!/usr/bin/env node
/**
 * Embed credits consistency gate.
 *
 * A third-party binary that renet embeds and conveys must be attributed in BOTH
 * renet-side (private/renet/pkg/embed/credits.go) and CLI-side
 * (packages/cli/src/data/third-party-credits.json) inventories, at the exact
 * version the build actually ships. This gate enforces that so a new or bumped
 * embed cannot silently ship unattributed / mis-versioned.
 *
 * It derives the truth from three durable sources:
 *   1. private/renet/Dockerfile ARGs (CRIU_VERSION / RSYNC_VERSION /
 *      RCLONE_VERSION) — the version source of truth (the .gz assets are
 *      gitignored build artifacts, so versions live in the Dockerfile).
 *   2. private/renet/pkg/embed/embed.go assetFilename() — the set of embedded
 *      component base names ("criu", "rsync", "rclone", and any future embed).
 *   3. The two inventories above.
 *
 * For every embedded component it asserts: an entry exists in credits.go and in
 * the JSON, and both versions equal the Dockerfile ARG. Extra non-embedded
 * inventory entries (Node.js runtime, bundled npm deps) are allowed.
 *
 * Usage:
 *   npx tsx scripts/check-embed-credits.ts
 *   npm run check:ci-embed-credits
 *
 * Path overrides (used by the gate test with fixtures):
 *   EMBED_CREDITS_DOCKERFILE, EMBED_CREDITS_EMBED_GO,
 *   EMBED_CREDITS_CREDITS_GO, EMBED_CREDITS_JSON
 *
 * Exit codes:
 *   0 - inventories are consistent with the Dockerfile + embed asset list
 *   1 - a missing or mismatched attribution was found
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GREEN, NC, RED, YELLOW } from './utils/console.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');

const DOCKERFILE =
  process.env.EMBED_CREDITS_DOCKERFILE ?? path.join(CONSOLE_ROOT, 'private/renet/Dockerfile');
const EMBED_GO =
  process.env.EMBED_CREDITS_EMBED_GO ??
  path.join(CONSOLE_ROOT, 'private/renet/pkg/embed/embed.go');
const CREDITS_GO =
  process.env.EMBED_CREDITS_CREDITS_GO ??
  path.join(CONSOLE_ROOT, 'private/renet/pkg/embed/credits.go');
const CREDITS_JSON =
  process.env.EMBED_CREDITS_JSON ??
  path.join(CONSOLE_ROOT, 'packages/cli/src/data/third-party-credits.json');

const errors: string[] = [];

function read(file: string): string {
  try {
    return fs.readFileSync(file, 'utf-8');
  } catch (err) {
    errors.push(`cannot read ${file}: ${(err as Error).message}`);
    return '';
  }
}

/** Dockerfile ARG <BASE>_VERSION=<version> -> { base(lowercase): version }. */
function parseDockerfileVersions(src: string): Map<string, string> {
  const versions = new Map<string, string>();
  const re = /^ARG\s+([A-Z0-9]+)_VERSION=(\S+)/gm;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src)) !== null) {
    const base = m[1].toLowerCase();
    const version = m[2];
    const existing = versions.get(base);
    if (existing !== undefined && existing !== version) {
      errors.push(
        `Dockerfile: conflicting ${m[1]}_VERSION values ('${existing}' vs '${version}')`
      );
    }
    versions.set(base, version);
  }
  return versions;
}

/** embed.go assetFilename() "<base>-linux-%s.gz" -> set of embedded base names. */
function parseEmbeddedBases(src: string): Set<string> {
  const bases = new Set<string>();
  const re = /Sprintf\("([a-z0-9]+)-linux-/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src)) !== null) {
    bases.add(m[1]);
  }
  return bases;
}

/** embed.go `AssetX = "value"` const map. */
function parseAssetConsts(src: string): Map<string, string> {
  const consts = new Map<string, string>();
  const re = /(Asset\w+)\s*=\s*"([^"]+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src)) !== null) {
    consts.set(m[1], m[2]);
  }
  return consts;
}

interface GoCredit {
  base: string;
  name: string;
  version: string;
}

/**
 * Parse credits.go []Credit entries. Each entry's Asset is either a string
 * literal ("criu") or an embed constant (AssetCRIU), which is resolved via the
 * embed.go const map. Fields Asset -> Name -> Version are declared in order.
 */
function parseGoCredits(src: string, assetConsts: Map<string, string>): GoCredit[] {
  const out: GoCredit[] = [];
  const re =
    /Asset:\s*(?:"([a-z0-9]+)"|(\w+))[\s\S]*?Name:\s*"([^"]+)"[\s\S]*?Version:\s*"([^"]+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src)) !== null) {
    const literal = m[1];
    const ident = m[2];
    let base = literal;
    if (!base && ident) {
      base = assetConsts.get(ident);
      if (!base) {
        errors.push(`credits.go: Asset constant '${ident}' is not defined in embed.go`);
        continue;
      }
    }
    if (!base) continue;
    out.push({ base, name: m[3], version: m[4] });
  }
  return out;
}

interface JsonCredit {
  asset?: string;
  name: string;
  version: string;
}

interface CreditsJson {
  components: JsonCredit[];
}

function parseJsonCredits(src: string): JsonCredit[] {
  if (!src) return [];
  try {
    const data = JSON.parse(src) as CreditsJson;
    if (!Array.isArray(data.components)) {
      errors.push('third-party-credits.json: missing "components" array');
      return [];
    }
    return data.components;
  } catch (err) {
    errors.push(`third-party-credits.json: invalid JSON (${(err as Error).message})`);
    return [];
  }
}

function main(): void {
  const dockerVersions = parseDockerfileVersions(read(DOCKERFILE));
  const embedSrc = read(EMBED_GO);
  const embeddedBases = parseEmbeddedBases(embedSrc);
  const assetConsts = parseAssetConsts(embedSrc);
  const goCredits = parseGoCredits(read(CREDITS_GO), assetConsts);
  const jsonCredits = parseJsonCredits(read(CREDITS_JSON));

  if (embeddedBases.size === 0) {
    errors.push('embed.go: no embedded asset base names found (assetFilename parse failed)');
  }

  const goByBase = new Map(goCredits.map((c) => [c.base, c]));
  const jsonByBase = new Map(
    jsonCredits.filter((c) => c.asset).map((c) => [c.asset as string, c])
  );

  for (const base of [...embeddedBases].sort()) {
    const dockerVersion = dockerVersions.get(base);
    if (dockerVersion === undefined) {
      errors.push(
        `Dockerfile: embedded component '${base}' has no ${base.toUpperCase()}_VERSION ARG`
      );
    }

    const go = goByBase.get(base);
    if (!go) {
      errors.push(`credits.go: missing entry for embedded component '${base}'`);
    } else if (dockerVersion !== undefined && go.version !== dockerVersion) {
      errors.push(
        `credits.go: '${base}' version '${go.version}' != Dockerfile ${base.toUpperCase()}_VERSION '${dockerVersion}'`
      );
    }

    const js = jsonByBase.get(base);
    if (!js) {
      errors.push(
        `third-party-credits.json: missing entry for embedded component '${base}'`
      );
    } else if (dockerVersion !== undefined && js.version !== dockerVersion) {
      errors.push(
        `third-party-credits.json: '${base}' version '${js.version}' != Dockerfile ${base.toUpperCase()}_VERSION '${dockerVersion}'`
      );
    }
  }

  // Flag asset-bearing inventory entries that no longer correspond to an embed.
  for (const c of goCredits) {
    if (!embeddedBases.has(c.base)) {
      errors.push(
        `credits.go: entry '${c.name}' (asset '${c.base}') is not in embed.go's asset list`
      );
    }
  }
  for (const [base, c] of jsonByBase) {
    if (!embeddedBases.has(base)) {
      errors.push(
        `third-party-credits.json: entry '${c.name}' (asset '${base}') is not in embed.go's asset list`
      );
    }
  }

  if (errors.length > 0) {
    console.error(`${RED}Embed credits gate FAILED:${NC}`);
    for (const e of errors) {
      console.error(`  ${YELLOW}-${NC} ${e}`);
    }
    console.error(
      '\nFix: keep private/renet/pkg/embed/credits.go and ' +
        'packages/cli/src/data/third-party-credits.json in sync with the ' +
        'private/renet/Dockerfile version ARGs and the embed.go asset list.'
    );
    process.exit(1);
  }

  const covered = [...embeddedBases].sort().join(', ');
  console.log(`${GREEN}Embed credits gate passed${NC} (covered: ${covered})`);
}

main();
