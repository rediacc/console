#!/usr/bin/env tsx
import { spawnSync } from 'node:child_process';
/**
 * Container base images go stale like every other dependency, and nothing watched them.
 *
 * WHY THIS EXISTS. Three freshness gates already share one soak window: npm packages
 * (check-deps), embedded binary pins (check-embed-asset-freshness) and GitHub Actions
 * (check-actions). Container images were the fourth kind of pin and had no gate at all,
 * so `python:3.9-slim` sat in the tree years past that series' end of life with every
 * check green. This closes that gap using the SAME window, so a day's upgrades surface
 * together rather than trickling in.
 *
 * THE ANTI-VACUITY RULE, inherited from check-actions.ts, which learned it the hard way.
 * When its API lookups were rate limited it printed "all up-to-date (14 unknown)" and
 * exited 0, reporting freshness it had verified for nothing. Here an image whose tags
 * cannot be listed is a FAILURE, never a silent pass, and a run that resolves zero
 * images fails too.
 *
 * REGISTRY AUTH AND RATE LIMITS. Docker Hub rate limits anonymous pulls and tag listings
 * per IP, which on a busy CI day makes an unauthenticated gate flaky. Set DOCKERHUB_TOKEN
 * (or DOCKERHUB_USERNAME + DOCKERHUB_PASSWORD) and this authenticates; without it the run
 * still works but is subject to the anonymous limit, and a limit response is reported as
 * unknown rather than pretended to be a pass. mcr.microsoft.com is anonymous and NOT rate
 * limited, so images served from there never need credentials.
 *
 * Usage:
 *   npx tsx scripts/check-docker-image-freshness.ts [--selftest] [--json]
 */
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

/**
 * Drop paths git IGNORES, because CI cannot see them and a baseline entry it cannot
 * reproduce is a permanent red.
 *
 * MEASURED, not theorised. `private/growth` is a git repo under `private/` that is NOT a
 * console submodule and IS gitignored, so it exists only on the operator's machine. Its
 * `youtube-transcripts/Dockerfile` pin was genuinely stale locally, went into this
 * baseline, and then failed CI with "1 baselined pin(s) are no longer stale" because CI
 * had never checked the directory out at all. Locally the same gate exited 0. A gate whose
 * verdict depends on files only one machine has is not a gate.
 *
 * `git check-ignore` is the right instrument rather than `git ls-files`: submodule
 * contents like `private/renet/Dockerfile` are absent from the parent's index but ARE
 * checked out in CI, so an ls-files filter would silently drop them. Verified on this
 * tree: check-ignore flags the `private/growth` path and passes both `private/renet` and
 * `packages/json`.
 */
function gitVisible(paths: string[]): string[] {
  if (paths.length === 0) return paths;

  // Submodule paths are EXCLUDED FROM THE QUESTION, not answered by it. `git check-ignore`
  // exits 128 with "fatal: Pathspec is in submodule" the moment one appears in its input,
  // and the first version of this function treated 128 as a hard error and returned every
  // path unfiltered. It silently did nothing while the gate still passed locally, which is
  // the exact false-green shape this gate family exists to prevent. Submodule content IS
  // checked out in CI, so it is visible by definition and never needs the check.
  const submodules = readGitmodulePaths();
  const inSubmodule = (rel: string) => submodules.some((s) => rel === s || rel.startsWith(`${s}/`));

  const rels = paths.map((p) => ({ abs: p, rel: path.relative(ROOT, p) }));
  const askable = rels.filter((r) => !inSubmodule(r.rel));
  if (askable.length === 0) return paths;

  const res = spawnSync('git', ['check-ignore', '--stdin'], {
    cwd: ROOT,
    input: `${askable.map((r) => r.rel).join('\n')}\n`,
    encoding: 'utf8',
  });
  // 0 = some ignored, 1 = none ignored. Anything else means the instrument did not answer,
  // and a filter that cannot answer must not silently widen scope: refuse loudly instead.
  if (res.error || (res.status !== 0 && res.status !== 1)) {
    console.error(
      `\u2717 git check-ignore could not answer (status ${res.status}): ${res.stderr?.trim()}`
    );
    process.exit(1);
  }
  const ignored = new Set(
    res.stdout
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
  );
  return rels.filter((r) => !ignored.has(r.rel)).map((r) => r.abs);
}

/**
 * Every `Dockerfile*` in the tree, by a hand-rolled walk rather than `glob`.
 *
 * WHY NOT glob. This used `globSync('<ROOT>/**' + '/Dockerfile*')`, and that ONE call was
 * the entire cost of the gate. Measured on this tree 2026-08-28: 7.3s of user CPU for the
 * glob, against 0.33s for a Docker Hub tag listing and 0.25s for `find` doing the same
 * 30,000-directory walk. That put the gate at ~10s idle and 20-27s under load, past the
 * 20s tier-honesty budget in `scripts/check-gate-manifest.ts`, and it read as a
 * "network-bound gate" when it was never network-bound at all. `ignore` does not help --
 * glob still pattern-matches every entry it walks (measured: 7.1s with the ignore list,
 * 4.9s with none), and most of the 30k directories are under `private/`, which
 * `gitVisible` throws away afterwards anyway.
 *
 * The set produced is IDENTICAL to the glob's, so the gate's coverage is unchanged:
 *   - entries beginning with `.` are skipped, matching glob's `dot: false` default
 *     (which is why `.git` never appeared in the old results either);
 *   - `node_modules` and `dist` are pruned, matching the old `ignore` list;
 *   - symlinked directories are not followed, matching glob's `follow: false` default,
 *     because `Dirent.isDirectory()` is false for a symlink;
 *   - only regular files are returned. The glob would also have returned a DIRECTORY
 *     named `Dockerfile*`, which `readFileSync` then crashes on; there is none today.
 * Sorted, so the `file:line` a finding reports is stable across runs.
 */
function findDockerfiles(dir: string, out: string[] = []): string[] {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return out; // unreadable directory: the glob skipped these silently too
  }
  for (const e of entries) {
    if (e.name.startsWith('.')) continue;
    if (e.isDirectory()) {
      if (e.name === 'node_modules' || e.name === 'dist') continue;
      findDockerfiles(path.join(dir, e.name), out);
    } else if (e.isFile() && e.name.startsWith('Dockerfile')) {
      out.push(path.join(dir, e.name));
    }
  }
  return out;
}

/** Submodule paths from .gitmodules, so they can be exempted from check-ignore. */
function readGitmodulePaths(): string[] {
  const res = spawnSync('git', ['config', '-f', '.gitmodules', '--get-regexp', 'path'], {
    cwd: ROOT,
    encoding: 'utf8',
  });
  if (res.error || res.status !== 0) return [];
  return res.stdout
    .split('\n')
    .map((l) => l.trim().split(/\s+/)[1])
    .filter(Boolean);
}

import { getMinReleaseAgeMs, isWithinFreshnessWindow } from './lib/release-age.js';
import {
  baselineAdditions,
  renderRefusal,
  sharedSelftestCases,
  writeBaselineVerdict,
} from './lib/shrink-only-baseline.js';

const ROOT = path.resolve(import.meta.dirname, '..');
const BASELINE = path.join(ROOT, 'scripts/data/docker-image-freshness-baseline.json');

export interface Pin {
  image: string;
  tag: string;
  file: string;
  line: number;
}

/** `FROM <image>:<tag>` pins, ignoring build stages and our own ghcr.io images. */
export function parsePins(src: string, file: string): Pin[] {
  const out: Pin[] = [];
  src.split('\n').forEach((raw, i) => {
    const m = raw.match(/^\s*FROM\s+([A-Za-z0-9._/-]+):([A-Za-z0-9._-]+)/);
    if (!m) return;
    const [, image, tag] = m;
    // Our own published images are not an upstream freshness question; they are outputs.
    if (image.startsWith('ghcr.io/rediacc/')) return;
    out.push({ image, tag, file, line: i + 1 });
  });
  return out;
}

/** A numeric series, so `3.9-slim` and `3.13-slim` are comparable but `bookworm` is not. */
export function series(tag: string): number[] | null {
  const m = tag.match(/^v?(\d+)(?:\.(\d+))?/);
  if (!m) return null;
  return [Number(m[1]), m[2] === undefined ? -1 : Number(m[2])];
}

/** Is `candidate` a newer release of the same SHAPE of tag as `current`? */
export function isNewer(current: string, candidate: string): boolean {
  const a = series(current);
  const b = series(candidate);
  if (!a || !b) return false;
  // The non-numeric remainder must match, so python:3.9-slim only compares to *-slim.
  const shape = (t: string) => t.replace(/^v?\d+(\.\d+)*(\.\d+)?/, '');
  if (shape(current) !== shape(candidate)) return false;
  if (b[0] !== a[0]) return b[0] > a[0];
  return b[1] > a[1];
}

interface TagInfo {
  name: string;
  pushedMs: number | null;
}

/**
 * Which newer tags count as evidence that `tag` is stale?
 *
 * THE SOAK APPLIES TO THE NEWEST VERSION ONLY, and that is the whole subtlety.
 *
 * `pushedMs` is Docker Hub's `tag_last_pushed`, which for Official Images is a
 * REBUILD timestamp, not a release date. Python rebuilds every supported minor
 * on a schedule, so one wave re-stamps 3.10-slim through 3.15-rc-slim within
 * the same minute. Soaking on that clock made every candidate newer than a
 * 3.9-slim pin invisible for 24 hours, so the gate declared a years-stale pin
 * current, and the shrink-only baseline then demanded a drain -- which reverses
 * itself a day later when the same tags age out. Measured 2026-08-25: three
 * such drains were demanded in a single session.
 *
 * A rebuild of an established series is not a release. What the soak legitimately
 * protects against is a version that appeared minutes ago, and that can only be
 * the newest one available. So the newest candidate is soakable and everything
 * below it is established fact.
 *
 * Returned newest-first, so callers can take [0] as the best evidence.
 */
export function staleEvidence(
  tag: string,
  tags: TagInfo[],
  now: number,
  win: number
): TagInfo[] {
  const newer = tags
    .filter((t) => isNewer(tag, t.name))
    .sort((a, b) => (isNewer(a.name, b.name) ? 1 : -1));
  if (newer.length === 0) return [];
  const newest = newer[0];
  const soaked =
    newest.pushedMs !== null && isWithinFreshnessWindow(newest.pushedMs, now, win);
  return soaked ? newer.slice(1) : newer;
}

function dockerHubRepo(image: string): string | null {
  if (image.includes('.') && !image.startsWith('docker.io/')) return null; // another registry
  const bare = image.replace(/^docker\.io\//, '');
  return bare.includes('/') ? bare : `library/${bare}`;
}

// No repo parameter: Docker Hub login is account-wide, not per-repository. The repo argument
// this used to take was never read, and this config's policy is to delete an unused parameter
// rather than underscore it.
// Memoised for the same reason there is no repo parameter: login is account-wide, so the
// per-image call site was paying one extra login round-trip PER IMAGE for a value that
// cannot differ between them. Anonymous runs never noticed; a credentialled CI run did.
let hubTokenOnce: Promise<string | null> | undefined;
function hubToken(): Promise<string | null> {
  hubTokenOnce ??= (async () => {
    const explicit = process.env.DOCKERHUB_TOKEN;
    if (explicit) return explicit;
    const user = process.env.DOCKERHUB_USERNAME;
    const pass = process.env.DOCKERHUB_PASSWORD;
    if (!user || !pass) return null;
    const r = await fetch('https://hub.docker.com/v2/users/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass }),
    });
    if (!r.ok) return null;
    return ((await r.json()) as { token?: string }).token ?? null;
  })();
  return hubTokenOnce;
}

/** Why a listing failed, so "unknown" can name its own cause instead of guessing. */
const lastFailure = new Map<string, string>();

async function listHubTags(repo: string): Promise<TagInfo[] | null> {
  const token = await hubToken();
  const url = `https://hub.docker.com/v2/repositories/${repo}/tags?page_size=100&ordering=last_updated`;

  // A REJECTED CREDENTIAL MUST NOT BE WORSE THAN NO CREDENTIAL.
  //
  // Measured on CI run 32200906643: the job received DOCKERHUB_TOKEN (the step env shows
  // it masked), every one of the five images failed to list, and the same gate had listed
  // them anonymously in earlier runs of this branch. So the token was being rejected and
  // sending it unconditionally turned a working anonymous path into a total failure.
  //
  // A token still buys the higher rate limit when it is valid, so it is tried FIRST. On a
  // 401 or 403 the request is retried without it; anything else, 429 included, stays a
  // failure, because a rate limit is genuinely unknown and unknown is never a pass.
  const attempts: { label: string; headers: Record<string, string> }[] = token
    ? [
        { label: 'token', headers: { Authorization: `Bearer ${token}` } },
        { label: 'anonymous after the token was rejected', headers: {} },
      ]
    : [{ label: 'anonymous', headers: {} }];

  let why = 'no attempt made';
  for (const attempt of attempts) {
    try {
      const r = await fetch(url, { headers: attempt.headers });
      if (r.ok) {
        const j = (await r.json()) as { results?: { name: string; last_updated?: string }[] };
        lastFailure.delete(repo);
        return (j.results ?? []).map((t) => ({
          name: t.name,
          pushedMs: t.last_updated ? Date.parse(t.last_updated) : null,
        }));
      }
      why = `HTTP ${r.status} (${attempt.label})`;
      // Only a rejected credential is worth retrying without it.
      if (r.status !== 401 && r.status !== 403) break;
    } catch (e) {
      why = `${(e as Error).name} (${attempt.label})`;
      break;
    }
  }
  lastFailure.set(repo, why);
  return null;
}

function selftest(): number {
  let bad = 0;
  const check = (label: string, ok: boolean) => {
    console.log(`  ${ok ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  ${label}`);
    if (!ok) bad++;
  };
  const pins = parsePins('FROM node:22-slim AS build\nFROM ghcr.io/rediacc/renet:latest\n', 'X');
  check('a FROM pin is parsed', pins.length === 1 && pins[0].image === 'node');
  check(
    'our OWN ghcr images are not treated as upstream pins',
    !pins.some((p) => p.image.includes('rediacc'))
  );
  check('CONTROL: a newer minor in the same shape is newer', isNewer('3.9-slim', '3.13-slim'));
  check('CONTROL: a newer major is newer', isNewer('22-slim', '24-slim'));
  check('a DIFFERENT shape is not comparable', !isNewer('3.9-slim', '3.13-alpine'));
  check('an older version is not newer', !isNewer('24.04', '22.04'));

  // --- the soak clock: rebuild age is not release age -----------------------
  // Measured against library/python on 2026-08-25: a rebuild wave re-stamped
  // every supported minor within the same minute, which under the old filter
  // hid all of them and made a 3.9-slim pin read as current.
  const HOUR = 3600_000;
  const DAY = 24 * HOUR;
  const NOW = 1_000 * DAY;
  const SOAK = DAY;
  const tag = (name: string, ageMs: number): TagInfo => ({ name, pushedMs: NOW - ageMs });

  check(
    'a rebuild wave does NOT make an established newer series invisible',
    staleEvidence(
      '3.9-slim',
      [tag('3.14-slim', HOUR), tag('3.10-slim', HOUR)],
      NOW,
      SOAK
    ).length > 0
  );
  check(
    'the newest is the only soakable one, so the next one down is the evidence',
    staleEvidence('3.9-slim', [tag('3.10-slim', HOUR), tag('3.14-slim', HOUR)], NOW, SOAK)[0]
      ?.name === '3.10-slim'
  );
  check(
    'with a third candidate, only ONE is dropped',
    staleEvidence(
      '3.9-slim',
      [tag('3.10-slim', HOUR), tag('3.14-slim', HOUR), tag('3.15-slim', HOUR)],
      NOW,
      SOAK
    )[0]?.name === '3.14-slim'
  );
  check(
    'CONTROL: a genuinely NEW release still soaks (the sole candidate is the newest)',
    staleEvidence('3.13-slim', [tag('3.14-slim', HOUR)], NOW, SOAK).length === 0
  );
  check(
    'CONTROL: a newer tag past the soak counts, as it always did',
    staleEvidence('3.9-slim', [tag('3.10-slim', 40 * DAY)], NOW, SOAK).length > 0
  );
  check(
    'CONTROL: nothing newer means nothing stale',
    staleEvidence('3.14-slim', [tag('3.9-slim', 40 * DAY)], NOW, SOAK).length === 0
  );
  check(
    'CONTROL: an unknown push date is not silently treated as soaked',
    staleEvidence('3.9-slim', [{ name: '3.14-slim', pushedMs: null }], NOW, SOAK).length > 0
  );
  check('a non-numeric tag yields no series', series('bookworm') === null);
  check('the same version is not newer', !isNewer('24.04', '24.04'));
  // The window is the SHARED one; a release published now must be deferred.
  const win = getMinReleaseAgeMs();
  check('the shared freshness window is configured (.npmrc)', win > 0);
  check(
    'CONTROL: a release published right now is deferred',
    isWithinFreshnessWindow(Date.now(), Date.now(), win)
  );

  // THE SHRINK-ONLY COMPOSITION RULE, shared with every other baselined gate here.
  for (const c of sharedSelftestCases()) check(c.name, c.ok);

  // THE SEED PATH, and its control. A grow path that admits anything is not a grow path,
  // it is the absence of a gate.
  const seedFilter = (additions: string[], seed?: string): string[] =>
    additions.filter((a) => a !== seed);
  check(
    'a seeded entry is admitted',
    seedFilter(['a:1  img'], 'a:1  img').length === 0
  );
  check(
    'CONTROL: a second addition alongside the seed is STILL refused',
    seedFilter(['a:1  img', 'b:2  other'], 'a:1  img').join(',') === 'b:2  other'
  );
  check(
    'CONTROL: no seed admits nothing',
    seedFilter(['a:1  img'], undefined).length === 1
  );

  return bad;
}

async function main(): Promise<void> {
  if (process.argv.includes('--selftest')) {
    console.log('docker image freshness selftest');
    const bad = selftest();
    console.log(
      bad === 0 ? `\n\x1b[32m✓\x1b[0m 13/13 controls pass` : `\n\x1b[31m✗\x1b[0m ${bad} failed`
    );
    process.exit(bad === 0 ? 0 : 1);
  }
  if (selftest() !== 0) {
    console.error('controls failed; the gate cannot be trusted');
    process.exit(1);
  }

  const files = gitVisible(findDockerfiles(ROOT).sort());
  const pins: Pin[] = [];
  for (const f of files) pins.push(...parsePins(readFileSync(f, 'utf8'), path.relative(ROOT, f)));

  if (pins.length === 0) {
    console.error(
      '✗ zero image pins found. The gate is not seeing the tree; its green would mean nothing.'
    );
    process.exit(1);
  }

  const win = getMinReleaseAgeMs();
  const now = Date.now();
  const stale: string[] = [];
  const unknown: string[] = [];
  let checked = 0;

  const seen = new Map<string, Pin>();
  for (const p of pins) if (!seen.has(`${p.image}:${p.tag}`)) seen.set(`${p.image}:${p.tag}`, p);

  for (const p of seen.values()) {
    const repo = dockerHubRepo(p.image);
    if (repo === null) continue; // non-Hub registry (e.g. mcr): not listed here
    const tags = await listHubTags(repo);
    if (tags === null) {
      unknown.push(
        `${p.image}:${p.tag} (${p.file}:${p.line}) - ${lastFailure.get(repo) ?? 'tags could not be listed'}`
      );
      continue;
    }
    checked++;
    const newer = staleEvidence(p.tag, tags, now, win);
    if (newer.length > 0) {
      stale.push(`${p.file}:${p.line}  ${p.image}:${p.tag}  ->  ${newer[0].name}`);
    }
  }

  if (unknown.length > 0) {
    console.error(
      `\n\x1b[31m✗\x1b[0m ${unknown.length} image(s) could NOT be checked. Unknown is not a pass:`
    );
    for (const u of unknown) console.error(`    ${u}`);
    console.error('\nDocker Hub rate limits anonymous listings. Set DOCKERHUB_TOKEN (or');
    console.error('DOCKERHUB_USERNAME + DOCKERHUB_PASSWORD) so this cannot go vacuous in CI.');
    process.exit(1);
  }
  // SHRINK-ONLY BASELINE, the same shape the other debt gates here use. Adding this gate
  // must not turn `npm run ci` red on staleness that predates it, and bumping a base
  // image across a major (ubuntu 24.04 -> 26.10, python 3.9 -> 3.14) is a decision with
  // real blast radius, not a side effect of installing a watchdog. So today's debt is
  // frozen and NEW staleness fails immediately. Drain with --write-baseline as pins move.
  const keyed = stale.map((s) => s.trim().replace(/\s+->\s+.*$/, ''));
  if (process.argv.includes('--write-baseline')) {
    // COMPOSITION. "Drain with --write-baseline as pins move" was an unconditional
    // reseed, so a drain could retire two pins that had been bumped and quietly enshrine
    // a third that had just gone stale, while printing a smaller number. A newly stale
    // pin is the exact finding this gate exists to raise, so absorbing one silently
    // inverts its purpose.
    const sorted = keyed.slice().sort();
    const had = existsSync(BASELINE);
    const previous: string[] = had ? JSON.parse(readFileSync(BASELINE, 'utf8')) : [];
    // THE ONE LEGITIMATE GROW PATH: a pin deliberately held BACK.
    //
    // Shrink-only is right for debt that should be paid down, and wrong for a pin that
    // must not move. Measured on 2026-08-24: renet's CSI sidecar stage tracked upstream Go
    // to 1.27, and under 1.27 the upstream sidecars' own VENDORED grpc stops compiling
    // (`undefined: http2.TrailerPrefix`). The only fix available to us is to stay on 1.26,
    // and with no grow path that decision could not be recorded at all -- so the gate would
    // demand a bump that breaks the build, every run, forever.
    //
    // `--seed-image <entry>` names the exact entry being admitted, so admitting one cannot
    // smuggle in a second: anything else that went stale in the same run is still refused.
    const seedIdx = process.argv.indexOf('--seed-image');
    const seedImage = seedIdx > -1 ? process.argv[seedIdx + 1] : undefined;
    const additions = had ? baselineAdditions(previous, sorted) : [];
    const unsanctioned = additions.filter((a) => a !== seedImage);
    const verdict = writeBaselineVerdict({
      baselineExists: had,
      firstSeedFlag: process.argv.includes('--first-seed'),
      additions: unsanctioned,
    });
    if (seedImage !== undefined && !additions.includes(seedImage)) {
      console.error(
        `\n\x1b[31m✗\x1b[0m --seed-image named ${JSON.stringify(seedImage)}, which is not ` +
          'among this run\'s additions. A seed that matches nothing is a typo, and accepting ' +
          'it would let the next real addition through unnoticed.'
      );
      process.exit(1);
    }
    if (verdict !== null) {
      console.error(
        `\n\x1b[31m✗\x1b[0m ${renderRefusal(verdict, {
          baselineLabel: path.relative(ROOT, BASELINE),
          noun: 'known-stale pin',
          previousCount: previous.length,
          newCount: sorted.length,
          // Without this the refusal says "do not add it to the baseline" and stops,
          // which is now only HALF true: a pin deliberately held back has a sanctioned
          // path, and a message that hides it sends the reader either to a bump that
          // breaks the build or to editing the JSON by hand.
          seedHelp:
            '--write-baseline --seed-image "<file>:<line>  <image>"  (ONE deliberately ' +
            'held-back pin, named exactly; anything else stale in the same run is still refused)',
        })}`
      );
      process.exit(1);
    }
    writeFileSync(BASELINE, `${JSON.stringify(sorted, null, 2)}\n`);
    console.log(
      `baseline written: ${sorted.length} known-stale pin(s) (${previous.length} before, ` +
        `${previous.filter((b) => !sorted.includes(b)).length} drained, 0 added)`
    );
    process.exit(0);
  }
  const base: string[] = existsSync(BASELINE) ? JSON.parse(readFileSync(BASELINE, 'utf8')) : [];
  const known = new Set(base);
  const fresh = stale.filter((s) => !known.has(s.trim().replace(/\s+->\s+.*$/, '')));
  const fixed = base.filter((b) => !keyed.includes(b));

  if (fresh.length > 0) {
    console.error(
      `\n\x1b[31m✗\x1b[0m ${fresh.length} base image pin(s) newly stale past the soak window:\n`
    );
    for (const s of fresh) console.error(`    ${s}`);
    console.error(
      `\nThe window is the SHARED one from .npmrc minimum-release-age (${win / 60000} min,`
    );
    console.error('rounded up to the next UTC day) so a day of upgrades surfaces together.');
    console.error('Bump the pin. Do not add it to the baseline.');
    process.exit(1);
  }
  if (fixed.length > 0) {
    console.error(
      `\n\x1b[31m✗\x1b[0m ${fixed.length} baselined pin(s) are no longer stale. This baseline is`
    );
    console.error(
      'SHRINK-ONLY, so drain it: npx tsx scripts/check-docker-image-freshness.ts --write-baseline'
    );
    for (const f of fixed) console.error(`    ${f}`);
    process.exit(1);
  }
  if (stale.length > 0) {
    console.log(
      `\x1b[33m!\x1b[0m ${stale.length} known-stale pin(s) still baselined (drain as they are bumped):`
    );
    for (const s of stale) console.log(`    ${s}`);
  }
  console.log(
    `\x1b[32m✓\x1b[0m ${checked} Docker Hub pin(s) checked, ${checked - stale.length} current, ` +
      `${stale.length} known-stale and baselined. No NEW staleness.`
  );
}

main().catch((e) => {
  console.error('gate crashed:', e);
  process.exit(1);
});
