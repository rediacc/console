#!/usr/bin/env node
/**
 * Devcontainer pin freshness gate.
 *
 * The devcontainer image pins third-party CLIs as `ARG <BASE>_VERSION=` in
 * .devcontainer/Dockerfile, and until this file existed NOTHING watched a single
 * one of them. check-deps.ts sees npm; check-go-deps.sh sees go.mod;
 * check-embed-asset-freshness.ts sees private/renet/Dockerfile and says the hole
 * out loud in its own header -- "npm/Go dep gates never see a Dockerfile ARG".
 * This is that same hole, one Dockerfile over. It was noticed when the Bitwarden
 * CLI was pinned at 2026.8.0 and there was no answer to "what tells us when that
 * goes stale?"
 *
 * WHY A SIBLING OF check-embed-asset-freshness.ts RATHER THAN AN ARM OF IT. That
 * gate is narrowly about the binaries renet EMBEDS: its name, its blocklist and
 * every line of its --upgrade advice ("re-run ./build.sh embed_assets --force",
 * "update the credits inventories") are about that pipeline. Devcontainer tools
 * share none of it, and folding them in would make each of those sentences
 * half-true. What IS shared -- the parser, the soak, the BLOCKER validator -- is
 * imported rather than copied.
 *
 * POLICY, inherited deliberately from that gate because it is what makes a
 * freshness gate liveable rather than a thing people disable:
 *  - FRESHNESS WINDOW: a release younger than the window in .ci/config/release-age.json
 *    (1440 min) is NOT flagged yet, and eligibility is rounded to the next UTC
 *    day so a day's upgrades surface together. Not a new knob: it is the same
 *    number check-deps.ts, audit.sh and check-go-deps.sh already read.
 *  - FAIL CLOSED ON NETWORK (operator ruling 2026-10-13, "Everything fails
 *    closed, nightly included"). Until that ruling this gate reported an
 *    upstream it could not reach as could-not-check and exited 0, so its green
 *    did not mean the pins had been compared. Now a pin whose release list was
 *    not obtained is a RED finding that names the pin, the host and path asked,
 *    the status or error code, and that this is an upstream reachability
 *    failure. The request, the bounded retry (3 attempts, 15 s each, 2 s then
 *    4 s between them) and the finding's wording are shared with every
 *    external gate, in scripts/lib/upstream.ts. The pins are asked
 *    concurrently, so the worst case is 51 s.
 *  - A LISTING THAT ANSWERS AND CANNOT BE USED IS RED TOO: a 200 that is not a
 *    release list, or holds no release under the tag prefix in its newest 100,
 *    means the gate has stopped seeing that upstream.
 *  - A SOURCE WITH NO `ARG <BASE>_VERSION` IN THE DOCKERFILE IS RED on a check
 *    run: nothing was compared for it, and the gate would watch nothing for
 *    that tool from then on.
 *  - BLOCKER-GATED HOLDS: .devcontainer-upgrade-blocklist, each entry carrying a
 *    substantive reason, validated like every other suppression list here.
 *
 * WHAT IT DOES THAT THE EMBED GATE DOES NOT:
 *  1. Filters release TAGS by prefix. bitwarden/clients is a monorepo, so
 *     /releases/latest answers with whichever of web/desktop/browser/cli shipped
 *     last -- a question nobody asked. See DevcontainerPinSource.tagPrefix.
 *  2. Rewrites the sha256 ARGs with the version. The embed gate rewrites the ARG
 *     and tells a human to go refresh the hashes; here that would hand back a
 *     tree whose next `docker build` dies at `sha256sum -c -`. The digests are
 *     already on the release JSON this gate is holding, so it writes them.
 *
 * UPSTREAM ASKED: api.github.com, `GET /repos/<owner>/<repo>/releases` for each
 * repository in scripts/lib/devcontainer-pin-sources.ts (bitwarden/clients,
 * bitwarden/sdk-sm, golang/tools, go-delve/delve, golangci/golangci-lint). The
 * sha256 digests `--upgrade` writes come from that same answer, so there is no
 * second host and no second request.
 *
 * HARD ON EVERY CADENCE. The step runs `npm run check:ci-devcontainer-pins`
 * directly, with no run_external_gate wrapper, so an exit 1 is red on a pull
 * request, on the nightly and on a dispatch. The `no-external-quality` label on
 * a pull request is the one way the step does not run, and the job's "Announce
 * pin gates held by label" step names this gate in the log when that happens.
 *
 * Usage:
 *   npx tsx scripts/gates/check-devcontainer-pin-freshness.ts            # check
 *   npx tsx scripts/gates/check-devcontainer-pin-freshness.ts --upgrade  # rewrite pins
 *   npm run check:ci-devcontainer-pins
 *
 * Exit codes: 0 = every pin that is not held was compared with upstream and is
 * current or deferred; 1 = a confirmed stale pin, a pin that was not compared,
 * a listing that cannot be used, a source with no ARG, a malformed blocklist
 * entry, or an --upgrade that could not resolve every digest it needed.
 *
 * ---- gate ----
 * step: Check devcontainer pin upstream freshness
 * needs: node
 * id: check:ci-devcontainer-pins
 * lane: quality-go
 * env-GITHUB_TOKEN: ${{ github.token }}
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { WK_GH_API_BASE } from '../../packages/shared/src/config/well-known.generated.js';
import { parseBlockeredList, verifyAllBlockers } from '../lib/blocker-validator.js';
import { GREEN, NC, RED, YELLOW } from '../lib/console.js';
import {
  DEVCONTAINER_PIN_SOURCES as SOURCES,
  type DevcontainerPinSource as Source,
} from '../lib/devcontainer-pin-sources.js';
import { parseDockerfileVersions } from '../lib/dockerfile-versions.js';
import { policyPath } from '../lib/policy-paths.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from '../lib/release-age.js';
import { githubAsker, NotCompared, PinTally, UnreadableListing } from '../lib/upstream.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..', '..');
// Test seams, mirroring check-embed-asset-freshness.ts: point the gate at fixture files so its test can prove the BLOCKER validation fires and that a stale pin is caught, without mutating the tracked blocklist or hitting the network.
//
// DEVCONTAINER_DOCKERFILE is the seam this file was MISSING, and its absence had a cost. --upgrade rewrites the Dockerfile in place, so the gate's test drove it against the REAL tracked file and restored it from a trap. That mutation is visible to every other gate sharing the tree: on 2026-09-03 it reddened check:ci-setup-idempotency in the pre-push lane, which reported "setup
// --check changed the working tree" over `.devcontainer/Dockerfile` -- a file run.sh never writes, naming the wrong command and sending the reader into run.sh. It is also a hazard beyond CI: this repo's working tree usually holds another session's uncommitted work, and a gate that rewrites a tracked file, however briefly, can be interrupted.
const DOCKERFILE =
  process.env.DEVCONTAINER_DOCKERFILE || path.join(CONSOLE_ROOT, '.devcontainer/Dockerfile');
const BLOCKLIST =
  process.env.DEVCONTAINER_BLOCKLIST_FILE ||
  policyPath('.devcontainer-upgrade-blocklist', CONSOLE_ROOT);
// A third seam: another API base, so the gate's test can stand a real HTTP server in for GitHub and an offline run can be driven by hand. The token is never sent to it.
const github = githubAsker('rediacc-devcontainer-pin-freshness', process.env.DEVCONTAINER_API_BASE);

interface Latest {
  version: string;
  publishedAt: Date | null;
  /** asset filename -> bare sha256 hex, from the release API's `digest` field. */
  digests: Map<string, string>;
}

/** A version string -> comparable numeric segments. */
function toSegments(v: string): number[] {
  const cleaned = v.replace(/^v/i, '');
  const [core, meta = ''] = cleaned.split('+');
  const nums = core.split(/[.-]/).map((s) => Number.parseInt(s, 10) || 0);
  const metaNum = Number.parseInt(meta.replace(/\D/g, ''), 10) || 0;
  return [...nums, metaNum];
}

/** true when `latest` is strictly newer than `pinned`. */
function isNewer(latest: string, pinned: string): boolean {
  const a = toSegments(latest);
  const b = toSegments(pinned);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i] ?? 0;
    const y = b[i] ?? 0;
    if (x !== y) return x > y;
  }
  return false;
}

/**
 * Test seam: DEVCONTAINER_FRESHNESS_FIXTURE points at a JSON map
 * `{ "<base>": { "version": "x.y.z", "publishedAt"?: "ISO",
 *                "digests"?: { "<asset>": "<sha256>" } } }`
 * used INSTEAD of the network. A base absent from the fixture was not compared,
 * which is red.
 */
let fixtureCache: Record<string, FixtureEntry> | null | undefined;
interface FixtureEntry {
  version: string;
  publishedAt?: string;
  digests?: Record<string, string>;
}
function loadFixture(): Record<string, FixtureEntry> | null {
  const cached = fixtureCache;
  if (cached !== undefined) return cached;
  const p = process.env.DEVCONTAINER_FRESHNESS_FIXTURE;
  const loaded = p ? JSON.parse(fs.readFileSync(p, 'utf-8')) : null;
  fixtureCache = loaded;
  return loaded;
}

interface GithubRelease {
  tag_name?: string;
  published_at?: string;
  draft?: boolean;
  prerelease?: boolean;
  assets?: Array<{ name?: string; digest?: string }>;
}

/** Newest stable release matching the source's tag prefix. Throws NotCompared when the listing was not obtained and UnreadableListing when it cannot be used. */
async function latestFor(src: Source): Promise<Latest> {
  const fixture = loadFixture();
  if (fixture) {
    const hit = fixture[src.base];
    if (!hit) throw NotCompared.absentFromFixture(src.base);
    return {
      version: hit.version,
      publishedAt: hit.publishedAt ? new Date(hit.publishedAt) : null,
      digests: new Map(Object.entries(hit.digests ?? {})),
    };
  }

  // NOT /releases/latest. On a monorepo that endpoint answers with whichever COMPONENT shipped last -- for bitwarden/clients that is web-*, desktop-*, browser-* or cli-* depending on the week -- so it would compare the CLI pin against a browser-extension version and produce nonsense in both directions. The list endpoint is ordered newest-first, so the first prefix match is the
  // answer.
  const rels = await github(`/repos/${src.repo}/releases?per_page=100`, src.display);
  if (!Array.isArray(rels)) throw new UnreadableListing('the response is not a release list');
  const hit = (rels as Array<GithubRelease | null>).find(
    (r) => r && !r.draft && !r.prerelease && (r.tag_name ?? '').startsWith(src.tagPrefix)
  );
  if (!hit?.tag_name) {
    throw new UnreadableListing(
      `no released tag starting with "${src.tagPrefix}" in the newest 100`
    );
  }

  const digests = new Map<string, string>();
  for (const a of hit.assets ?? []) {
    // `digest` is "sha256:<hex>". Bitwarden publishes no .sha256 sidecars and no GPG/cosign signatures, so this is the only machine-readable checksum there is -- an integrity check against the same API that serves the download, not an independent trust root. Worth knowing; still better than no pin.
    if (a.name && a.digest?.startsWith('sha256:')) {
      digests.set(a.name, a.digest.slice('sha256:'.length));
    }
  }

  return {
    version: hit.tag_name.slice(src.tagPrefix.length),
    publishedAt: hit.published_at ? new Date(hit.published_at) : null,
    digests,
  };
}

interface Finding {
  src: Source;
  pinned: string;
  latest: string;
  digests: Map<string, string>;
}

function loadBlocklist(): { held: Set<string>; errors: string[] } {
  if (!fs.existsSync(BLOCKLIST)) return { held: new Set(), errors: [] };
  const entries = parseBlockeredList(BLOCKLIST);
  const errors = verifyAllBlockers(entries, BLOCKLIST);
  return { held: new Set(entries.map((e) => e.entry.trim().toLowerCase())), errors };
}

/**
 * Rewrite one source's version ARG and every hash ARG it declares.
 *
 * ALL-OR-NOTHING per source. A missing digest returns null and the caller leaves
 * that pin alone, because writing the version without its hash produces a tree
 * that fails `docker build` at `sha256sum -c -` -- and an operator who ran
 * --upgrade and got a broken build learns to distrust the gate, not the release.
 */
function rewriteSource(src: string, f: Finding): { text: string } | { error: string } {
  const arg = `${f.src.base.toUpperCase()}_VERSION`;
  let out = src.replace(new RegExp(`(^ARG\\s+${arg}=)\\S+`, 'gm'), `$1${f.latest}`);

  for (const [arch, spec] of Object.entries(f.src.hashArgs ?? {})) {
    const assetName = spec.asset(f.latest);
    const digest = f.digests.get(assetName);
    if (!digest) {
      return {
        error: `${f.src.display}: release ${f.latest} has no digest for ${assetName} (arch ${arch}); refusing to move the version without its hash.`,
      };
    }
    out = out.replace(new RegExp(`(^ARG\\s+${spec.arg}=)\\S+`, 'gm'), `$1${digest}`);
  }
  return { text: out };
}

async function main(): Promise<void> {
  const upgrade = process.argv.includes('--upgrade');
  const dockerfile = fs.readFileSync(DOCKERFILE, 'utf-8');
  const { versions, conflicts } = parseDockerfileVersions(dockerfile);
  const { held, errors: blockerErrors } = loadBlocklist();
  const minReleaseAgeMs = getMinReleaseAgeMs();
  const nowMs = Date.now();

  console.log('Devcontainer pin freshness');
  console.log('='.repeat(60));

  if (blockerErrors.length > 0) {
    console.error(`${RED}✗ ${path.basename(BLOCKLIST)} has invalid entries:${NC}`);
    for (const e of blockerErrors) console.error(`  ${e}`);
    process.exit(1);
  }
  for (const c of conflicts) console.error(`${YELLOW}⚠ ${c}${NC}`);

  const stale: Finding[] = [];
  const deferred: string[] = [];
  const tally = new PinTally('devcontainer', SOURCES.length);
  // A held pin and a source with no ARG are not asked.
  const answers = await tally.askAll(SOURCES, (src) =>
    versions.has(src.base) && !held.has(src.base) ? latestFor(src) : null
  );

  for (const [index, src] of SOURCES.entries()) {
    const pinned = versions.get(src.base);
    const answer = answers[index];
    if (!pinned) {
      // A source naming an ARG the Dockerfile no longer has is not a staleness finding, and it is not a pass either: the gate would watch nothing for that tool.
      tally.noPin.push(
        `${src.display}: no ${src.base.toUpperCase()}_VERSION ARG in the Dockerfile`
      );
      continue;
    }
    if (!answer) {
      tally.held.push(`${src.display} (pinned at ${pinned})`);
      continue;
    }
    if ('err' in answer) {
      tally.failed(`${src.display} (pinned ${pinned})`, `${src.display} (${src.repo})`, answer.err);
      continue;
    }
    tally.compared++;
    const latest = answer.value;
    if (!isNewer(latest.version, pinned)) continue;
    if (
      latest.publishedAt !== null &&
      isWithinFreshnessWindow(latest.publishedAt.getTime(), nowMs, minReleaseAgeMs)
    ) {
      deferred.push(
        `${src.display}: ${latest.version} just released — deferred to the next UTC day (soak)`
      );
      continue;
    }
    stale.push({ src, pinned, latest: latest.version, digests: latest.digests });
  }

  for (const d of deferred) console.log(`${YELLOW}⏳ ${d}${NC}`);
  for (const h of tally.held) console.log(`${YELLOW}⏸ held: ${h}${NC}`);

  // What a green may not hide: a pin nobody compared. --upgrade rewrites the pins it can see, so a missing ARG is left to the check run.
  const blind = tally.report({
    sources: 'scripts/lib/devcontainer-pin-sources.ts',
    noPinFix: [
      '  Restore the ARG in .devcontainer/Dockerfile, or drop the entry from',
      '  scripts/lib/devcontainer-pin-sources.ts when the tool is no longer installed.',
    ],
    noPinIsRed: !upgrade,
  });

  if (stale.length === 0) {
    if (blind > 0) process.exit(1);
    console.log(`${GREEN}✓ Every devcontainer pin is current or deferred (${tally.shape}).${NC}`);
    return;
  }

  if (upgrade) {
    let text = dockerfile;
    const errors: string[] = [];
    for (const f of stale) {
      const result = rewriteSource(text, f);
      if ('error' in result) {
        errors.push(result.error);
        continue;
      }
      text = result.text;
      const alsoHashes = Object.keys(f.src.hashArgs ?? {}).length;
      console.log(
        `${GREEN}↑ ${f.src.display}: ${f.pinned} -> ${f.latest}${NC}` +
          (alsoHashes > 0 ? ` (and ${alsoHashes} sha256 pin(s))` : '')
      );
    }
    if (text !== dockerfile) fs.writeFileSync(DOCKERFILE, text);
    if (errors.length > 0) {
      console.error('');
      for (const e of errors) console.error(`${RED}✗ ${e}${NC}`);
      console.error('  Check the release assets by hand, then set the ARGs yourself:');
      console.error(
        `    curl -s ${WK_GH_API_BASE}/repos/<repo>/releases/tags/<tag> | jq -r '.assets[]|"\\(.name) \\(.digest)"'`
      );
      process.exit(1);
    }
    console.log('');
    console.log(`${YELLOW}Dockerfile ARGs rewritten. Now REBUILD the image and verify:${NC}`);
    console.log(
      '  docker build -t rediacc/devcontainer:bump -f .devcontainer/Dockerfile .devcontainer'
    );
    console.log('  A wrong hash fails that build at `sha256sum -c -`, which is the point.');
    console.log('  The published image only changes when .github/workflows/ci-build-docker.yml');
    console.log('  runs on the merge; developers pick it up with `./run.sh setup --pull`.');
    // A pin that was not compared was not upgraded either, and that is not a clean run.
    if (blind > 0) process.exit(1);
    return;
  }

  console.error('');
  console.error(`${RED}✗ ${stale.length} devcontainer pin(s) are behind upstream:${NC}`);
  for (const f of stale) {
    console.error(`  ${f.src.display}: pinned ${f.pinned}  ->  upstream ${f.latest}`);
  }
  // A copy-pasteable fix, for the same reason check-embed-asset-freshness.ts has one: a human or an agent reading this should be able to act without hunting.
  console.error('');
  console.error(`${YELLOW}TO FIX — bump the pin and its hashes together:${NC}`);
  console.error('    npm run check:ci-devcontainer-pins -- --upgrade');
  console.error('  then rebuild the image to prove the new hashes are right:');
  console.error(
    '    docker build -t rediacc/devcontainer:bump -f .devcontainer/Dockerfile .devcontainer'
  );
  console.error('');
  console.error('TO HOLD one back instead: add its base name (e.g. `bw`) with a `# BLOCKER:`');
  console.error(`reason to ${path.basename(BLOCKLIST)}.`);
  process.exit(1);
}

main().catch((err) => {
  // Per-source network failures are caught above, so reaching here is a real bug in the gate -- which must not be indistinguishable from a pass.
  console.error(`${RED}✗ freshness gate crashed: ${(err as Error).message}${NC}`);
  process.exit(1);
});
