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
 * the derive steps its pins entries carry (the credits inventories, the vendored
 * CRDs) are about that pipeline. Devcontainer tools share none of it. What IS
 * shared -- the parser, the soak, the BLOCKER validator -- is imported rather
 * than copied.
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
 *  - A RELEASE THE IMAGE CANNOT BUILD IS NOT "BEHIND" (worklist #e023eb0d). A
 *    tool installed with `go install` (its pins.json entry names a `goModule`)
 *    builds under the image's Go, GO_VERSION in .devcontainer/toolchain.env with
 *    GOTOOLCHAIN=local, so a release whose go.mod `go` directive is newer cannot
 *    be taken: gopls 0.24.0 (`go 1.27.0`) failed the image build on Go 1.26.x on
 *    2026-10-18. Each such release is printed as deferred, naming the Go it
 *    needs, and the pin is judged against the newest release that builds. The
 *    go.mod is read from proxy.golang.org (`/<module>/@v/v<version>.mod`), and
 *    one the proxy does not answer, or one with no `go` line, is RED, never
 *    eligible (scripts/lib/pins/go-directive.ts).
 *
 * WHAT IT DOES THAT THE EMBED GATE DOES NOT: it filters release TAGS by prefix.
 * bitwarden/clients is a monorepo, so /releases/latest answers with whichever of
 * web/desktop/browser/cli shipped last -- a question nobody asked. See
 * DevcontainerPinSource.tagPrefix.
 *
 * UPSTREAM ASKED: api.github.com, `GET /repos/<owner>/<repo>/releases` for each
 * repository in scripts/lib/devcontainer-pin-sources.ts (bitwarden/clients,
 * bitwarden/sdk-sm, golang/tools, go-delve/delve, golangci/golangci-lint).
 *
 * THE FIX IS ONE COMMAND. A stale pin's failure line is `npm run pins -- bump
 * devcontainer:<base>` (scripts/lib/pins/remedy.ts): the devcontainer driver moves
 * the version and every sha256 ARG together, from the digests the release
 * publishes, and refuses the whole pin when one digest is missing. This gate's
 * own `--upgrade` mode, which did that rewrite here, is retired with it.
 *
 * HARD ON EVERY CADENCE. The step runs `npm run check:ci-devcontainer-pins`
 * directly, with no wrapper, so an exit 1 is red on a pull
 * request, on the nightly and on a dispatch. The `no-external-quality` label on
 * a pull request is the one way the step does not run, and the job's "Announce
 * pin gates held by label" step names this gate in the log when that happens.
 *
 * Usage:
 *   npx tsx scripts/gates/check-devcontainer-pin-freshness.ts
 *   npm run check:ci-devcontainer-pins
 *
 * Exit codes: 0 = every pin that is not held was compared with upstream and is
 * current or deferred; 1 = a confirmed stale pin, a pin that was not compared,
 * a listing that cannot be used, a source with no ARG, or a malformed blocklist
 * entry.
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
import { parseBlockeredList, verifyAllBlockers } from '../lib/blocker-validator.js';
import { GREEN, NC, RED, YELLOW } from '../lib/console.js';
import {
  DEVCONTAINER_PIN_SOURCES as SOURCES,
  type DevcontainerPinSource as Source,
} from '../lib/devcontainer-pin-sources.js';
import { parseDockerfileVersions } from '../lib/dockerfile-versions.js';
import {
  goModUrl,
  goNeeds,
  goTooNew,
  imageGoVersion,
  needsGoWhy,
  TOOLCHAIN_ENV,
} from '../lib/pins/go-directive.js';
import { entriesFor, loadRegistry } from '../lib/pins/registry.js';
import { bumpRemedy } from '../lib/pins/remedy.js';
import { policyPath } from '../lib/policy-paths.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from '../lib/release-age.js';
import {
  askUpstream,
  githubAsker,
  NotCompared,
  PinTally,
  UnreadableListing,
} from '../lib/upstream.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..', '..');
// Test seams, mirroring check-embed-asset-freshness.ts: point the gate at fixture files so its test can prove the BLOCKER validation fires and that a stale pin is caught, without mutating the tracked blocklist or hitting the network.
//
// DEVCONTAINER_DOCKERFILE is the seam this file was MISSING, and its absence had a cost. The retired --upgrade rewrote the Dockerfile in place, so the gate's test drove it against the REAL tracked file and restored it from a trap. That mutation is visible to every other gate sharing the tree: on 2026-09-03 it reddened check:ci-setup-idempotency in the pre-push lane, which reported "setup
// --check changed the working tree" over `.devcontainer/Dockerfile` -- a file run.sh never writes, naming the wrong command and sending the reader into run.sh. It is also a hazard beyond CI: this repo's working tree usually holds another session's uncommitted work, and a gate that rewrites a tracked file, however briefly, can be interrupted.
const DOCKERFILE =
  process.env.DEVCONTAINER_DOCKERFILE || path.join(CONSOLE_ROOT, '.devcontainer/Dockerfile');
const BLOCKLIST =
  process.env.DEVCONTAINER_BLOCKLIST_FILE ||
  policyPath('.devcontainer-upgrade-blocklist', CONSOLE_ROOT);
// The image's Go, which a `go install`ed tool's go.mod is judged against; a seam so a case can name another one without touching the tracked file.
const TOOLCHAIN = process.env.DEVCONTAINER_TOOLCHAIN_ENV || path.join(CONSOLE_ROOT, TOOLCHAIN_ENV);
// A third seam: another API base, so the gate's test can stand a real HTTP server in for GitHub and an offline run can be driven by hand. The token is never sent to it.
const github = githubAsker('rediacc-devcontainer-pin-freshness', process.env.DEVCONTAINER_API_BASE);

interface Latest {
  version: string;
  publishedAt: Date | null;
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
 * `{ "<base>": { "version": "x.y.z", "publishedAt"?: "ISO" } }`
 * used INSTEAD of the network. A base absent from the fixture was not compared,
 * which is red.
 */
let fixtureCache: Record<string, FixtureEntry> | null | undefined;
interface FixtureEntry {
  version: string;
  publishedAt?: string;
  /** Older releases under the prefix, newest first, for a case that needs more than the newest. */
  older?: FixtureEntry[];
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
}

/**
 * Test seam: DEVCONTAINER_GOMOD_FIXTURE points at a JSON map `{ "<module>@<version>": "<go.mod text>" }`.
 * Under a release fixture the go.mod is read from this map and never from the network, so a key
 * the map lacks is a go.mod that was not obtained, which is red.
 */
let gomodCache: Record<string, string> | undefined;
function goModText(module: string, version: string, who: string): Promise<string> {
  if (loadFixture()) {
    if (gomodCache === undefined) {
      const p = process.env.DEVCONTAINER_GOMOD_FIXTURE;
      gomodCache = p ? (JSON.parse(fs.readFileSync(p, 'utf-8')) as Record<string, string>) : {};
    }
    const hit = gomodCache[`${module}@${version}`];
    return hit === undefined
      ? Promise.reject(NotCompared.absentFromFixture(`${module}@${version} go.mod`))
      : Promise.resolve(hit);
  }
  return askUpstream({
    url: goModUrl(module, version),
    headers: { 'User-Agent': 'rediacc-devcontainer-pin-freshness' },
    who,
  }).then((a) => a.body);
}

/** The pins.json `goModule` of each devcontainer pin installed with `go install`, by registry id. */
const GO_MODULES = new Map(
  entriesFor(loadRegistry(), 'devcontainer').flatMap((e) =>
    e.goModule ? [[e.id, e.goModule] as const] : []
  )
);

/** Every stable release matching the source's tag prefix, newest first. Throws NotCompared when the listing was not obtained and UnreadableListing when it cannot be used. */
async function releasesFor(src: Source): Promise<Latest[]> {
  const fixture = loadFixture();
  if (fixture) {
    const hit = fixture[src.base];
    if (!hit) throw NotCompared.absentFromFixture(src.base);
    return [hit, ...(hit.older ?? [])].map((r) => ({
      version: r.version,
      publishedAt: r.publishedAt ? new Date(r.publishedAt) : null,
    }));
  }

  // NOT /releases/latest. On a monorepo that endpoint answers with whichever COMPONENT shipped last -- for bitwarden/clients that is web-*, desktop-*, browser-* or cli-* depending on the week -- so it would compare the CLI pin against a browser-extension version and produce nonsense in both directions. The list endpoint is ordered newest-first, so the first prefix match is the
  // answer.
  const rels = await github(`/repos/${src.repo}/releases?per_page=100`, src.display);
  if (!Array.isArray(rels)) throw new UnreadableListing('the response is not a release list');
  const hits = (rels as Array<GithubRelease | null>).filter(
    (r): r is GithubRelease =>
      !!r && !r.draft && !r.prerelease && (r.tag_name ?? '').startsWith(src.tagPrefix)
  );
  if (hits.length === 0) {
    throw new UnreadableListing(
      `no released tag starting with "${src.tagPrefix}" in the newest 100`
    );
  }

  return hits.map((hit) => ({
    version: (hit.tag_name as string).slice(src.tagPrefix.length),
    publishedAt: hit.published_at ? new Date(hit.published_at) : null,
  }));
}

/** What one source answered: the newest release newer than the pin that the image can build (null when none is), and one line per newer release whose go.mod needs a newer Go. */
interface Judged {
  candidate: Latest | null;
  needsGo: string[];
}

/**
 * The releases newer than `pinned`, newest first, judged for a `go install`ed tool against the
 * image's Go `have`: a release whose go.mod needs a newer Go is set aside with its reason, and the
 * first one that builds is the candidate. A go.mod that was not obtained throws, so the pin is red.
 */
async function judge(src: Source, pinned: string, have: string | null): Promise<Judged> {
  const newer = (await releasesFor(src))
    .filter((r) => isNewer(r.version, pinned))
    .sort((a, b) => (isNewer(a.version, b.version) ? -1 : isNewer(b.version, a.version) ? 1 : 0));
  const mod = GO_MODULES.get(src.id);
  const needsGo: string[] = [];
  for (const r of newer) {
    if (mod !== undefined && have !== null) {
      const need = await goNeeds(
        (url) => goModText(mod, r.version, `${src.display} go.mod (${url})`),
        mod,
        r.version
      );
      if (goTooNew(need, have)) {
        needsGo.push(
          `${src.display}: ${r.version} deferred: ${needsGoWhy(mod, r.version, need, have)}`
        );
        continue;
      }
    }
    return { candidate: r, needsGo };
  }
  return { candidate: null, needsGo };
}

interface Finding {
  src: Source;
  pinned: string;
  latest: string;
}

function loadBlocklist(): { held: Set<string>; errors: string[] } {
  if (!fs.existsSync(BLOCKLIST)) return { held: new Set(), errors: [] };
  const entries = parseBlockeredList(BLOCKLIST);
  const errors = verifyAllBlockers(entries, BLOCKLIST);
  return { held: new Set(entries.map((e) => e.entry.trim().toLowerCase())), errors };
}

async function main(): Promise<void> {
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

  // FAIL CLOSED: a `go install`ed tool is judged against the image's Go, so a tree that names none cannot judge it.
  const have = imageGoVersion(
    fs.existsSync(TOOLCHAIN) ? fs.readFileSync(TOOLCHAIN, 'utf-8') : null
  );
  if (have === null && SOURCES.some((src) => GO_MODULES.has(src.id))) {
    console.error(
      `${RED}✗ ${TOOLCHAIN} names no GO_VERSION, so the Go each \`go install\`ed pin's release needs (${SOURCES.filter(
        (src) => GO_MODULES.has(src.id)
      )
        .map((src) => src.id)
        .join(', ')}) cannot be compared with the image's${NC}`
    );
    process.exit(1);
  }

  const stale: Finding[] = [];
  const deferred: string[] = [];
  const tally = new PinTally('devcontainer', SOURCES.length);
  // A held pin and a source with no ARG are not asked.
  const answers = await tally.askAll(SOURCES, (src) => {
    const pinned = versions.get(src.base);
    return pinned && !held.has(src.base) ? judge(src, pinned, have) : null;
  });

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
    deferred.push(...answer.value.needsGo);
    const latest = answer.value.candidate;
    if (latest === null) continue;
    if (
      latest.publishedAt !== null &&
      isWithinFreshnessWindow(latest.publishedAt.getTime(), nowMs, minReleaseAgeMs)
    ) {
      deferred.push(
        `${src.display}: ${latest.version} just released — deferred to the next UTC day (soak)`
      );
      continue;
    }
    stale.push({ src, pinned, latest: latest.version });
  }

  for (const d of deferred) console.log(`${YELLOW}⏳ ${d}${NC}`);
  for (const h of tally.held) console.log(`${YELLOW}⏸ held: ${h}${NC}`);

  // What a green may not hide: a pin nobody compared.
  const blind = tally.report({
    sources: 'scripts/lib/devcontainer-pin-sources.ts',
    noPinFix: [
      '  Restore the ARG in .devcontainer/Dockerfile, or drop the entry from',
      '  scripts/lib/devcontainer-pin-sources.ts when the tool is no longer installed.',
    ],
  });

  if (stale.length === 0) {
    if (blind > 0) process.exit(1);
    console.log(`${GREEN}✓ Every devcontainer pin is current or deferred (${tally.shape}).${NC}`);
    return;
  }

  console.error('');
  console.error(`${RED}✗ ${stale.length} devcontainer pin(s) are behind upstream:${NC}`);
  for (const f of stale) {
    console.error(`  ${f.src.display}: pinned ${f.pinned}  ->  upstream ${f.latest}`);
  }
  // THE FIX, one line per stale pin: the pins command moves the version and its hashes together (scripts/lib/pins/remedy.ts builds the line).
  console.error('');
  console.error(
    `${YELLOW}TO FIX, per pin (then rebuild the image; a wrong hash fails at \`sha256sum -c -\`):${NC}`
  );
  for (const f of stale) console.error(bumpRemedy(f.src.id));
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
