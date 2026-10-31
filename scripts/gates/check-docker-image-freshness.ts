#!/usr/bin/env tsx
// ---- gate ----
// step: Docker image freshness
// env-DOCKERHUB_TOKEN: ${{ env.BWS_DOCKERHUB_TOKEN }}
// needs: node
// selftest: true
// lane: quality-content
// ---- end gate ----

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
 * THE FIX LINE. A newly stale pin names `npm run pins -- bump <id> --major --reason "<why>"`,
 * the `docker` leaf of .ci/config/pins.json whose site matches that very FROM line
 * (scripts/lib/pins/remedy.ts builds it; the docker driver takes a series move only as a
 * major). Every FROM image has its own leaf (operator ruling 2026-10-14T20:56Z, "Add entries"),
 * so a FROM line no leaf site matches is RED on every run, stale or not, with the leaf shape
 * to add: a fix line that cannot name its pin is the gap that ruling closed. A file with
 * several FROM images (private/renet/Dockerfile carries debian, ubuntu and golang) is matched
 * by line, never by file, so each finding names its own leaf.
 *
 * THE DIGEST AGREES WITH THE TAG. A line that pins `<image>:<tag>@sha256:<digest>` names two
 * things, and only the digest is what a build pulls. `node:26.13.0-slim@<the 26.12.0 index>`
 * sat in workers/proxy/Dockerfile with every gate green, because the bump moved the tag alone
 * and nothing compared the two (#d4b2a051). So every such line in a tracked Dockerfile or
 * compose file (`git ls-files --recurse-submodules`, dot directories included) is checked
 * against the index digest Docker Hub serves for its tag (scripts/lib/docker-hub.ts). It FAILS
 * CLOSED: a mismatch is red, and so is a lookup that cannot answer (a 429, a 5xx, a 404, an
 * answer with no top-level `digest` or a malformed one), because an unchecked digest is not
 * an agreeing one. A digest with no tag on its line (`COPY --from=<image>@sha256:...`, a compose
 * `image: <image>@sha256:...`) names nothing to agree with, so it is LISTED every run as
 * untagged, with no verdict either way; a digest of another registry is listed the same way.
 *
 * DOCKER_HUB_API_BASE points the tag listings at another host (a stub in the remedy test);
 * set, no credential is sent. DOCKER_FRESHNESS_ROOT points the scan and the baseline at a
 * fixture git tree.
 *
 * Usage:
 *   npx tsx scripts/gates/check-docker-image-freshness.ts [--selftest] [--json]
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import { WK_IMAGE_REGISTRY } from '../../packages/shared/src/config/well-known.generated.js';
import { errorLines, GREEN, NC, RED, YELLOW } from '../lib/console.js';
import { HUB_DEFAULT_BASE, hubRepo, hubTagUrl, parseTagDigest } from '../lib/docker-hub.js';
import { loadRegistry, type PinEntry, siteRegex } from '../lib/pins/registry.js';
import { bumpRemedy } from '../lib/pins/remedy.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from '../lib/release-age.js';
import {
  baselineAdditions,
  renderRefusal,
  sharedSelftestCases,
  writeBaselineVerdict,
} from '../lib/shrink-only-baseline.js';

// The seam: DOCKER_FRESHNESS_ROOT stands a fixture git tree (its Dockerfiles and its baseline) in for the console, so the remedy test can plant a newly stale pin without writing to this tree.
const ROOT = process.env.DOCKER_FRESHNESS_ROOT || path.resolve(import.meta.dirname, '..', '..');
const BASELINE = path.join(ROOT, 'scripts/data/docker-image-freshness-baseline.json');

export interface Pin {
  image: string;
  tag: string;
  file: string;
  line: number;
  /** The FROM line itself, which the leaf's site must match. */
  text: string;
  /** The `sha256:<hex>` pinned beside the tag (`<image>:<tag>@sha256:...`), when the line carries one. */
  digest?: string;
}

/** `FROM [--flag=value ...] <image>:<tag>` pins, ignoring build stages and our own ghcr.io images. A FROM whose image is a variable (`$ARG`) or carries no tag has no literal pin to check and is not returned. */
export function parsePins(src: string, file: string): Pin[] {
  const out: Pin[] = [];
  src.split('\n').forEach((raw, i) => {
    const m = raw.match(
      /^\s*FROM\s+(?:--[A-Za-z0-9-]+=\S+\s+)*([A-Za-z0-9._/-]+):([A-Za-z0-9._-]+)(?:@(sha256:[0-9a-f]{64}))?/
    );
    if (!m) return;
    const [, image, tag, digest] = m;
    // Our own published images are not an upstream freshness question; they are outputs.
    if (image.startsWith(`${WK_IMAGE_REGISTRY}/`)) return;
    out.push({ image, tag, file, line: i + 1, text: raw, ...(digest ? { digest } : {}) });
  });
  return out;
}

/** One `<image>[:<tag>]@sha256:<hex>` reference in a Dockerfile or compose file. */
export interface DigestRef {
  image: string;
  /** Null when the line names no tag, so there is nothing to agree with. */
  tag: string | null;
  digest: string;
  file: string;
  line: number;
  text: string;
}

const DIGEST_REF =
  /(?<=^|[\s="'])([A-Za-z0-9._/-]+)(?::([A-Za-z0-9._-]+))?@(sha256:[0-9a-f]{64})\b/g;

/**
 * Every digest-pinned image reference in `src`, from any instruction (`FROM`, `COPY --from=`,
 * a compose `image:`), comment lines excepted. The image must start at a word boundary (the
 * line start, a space, `=` or a quote), so `node:26.13.0-slim@sha256:...` is read as image
 * `node` with tag `26.13.0-slim`, never as an image named `26.13.0-slim`. Pure.
 */
export function digestRefs(src: string, file: string): DigestRef[] {
  const out: DigestRef[] = [];
  src.split('\n').forEach((raw, i) => {
    if (/^\s*#/.test(raw)) return;
    for (const m of raw.matchAll(DIGEST_REF))
      out.push({ image: m[1], tag: m[2] ?? null, digest: m[3], file, line: i + 1, text: raw });
  });
  return out;
}

/** What Docker Hub answered for one `<image>:<tag>`: its index digest, or null with the cause. */
export interface TagAnswer {
  digest: string | null;
  why?: string;
}

/**
 * The agreement verdicts over `refs`, keyed in `answers` by `<image>:<tag>`. A tagged Docker
 * Hub reference whose digest differs from the answer is a finding, and so is one with no
 * answer or a null one (unknown is never agreement). Untagged and other-registry references
 * are returned as `unjudged`, never judged. `leafOf` names the pins leaf that moves a line,
 * or null. Pure.
 */
export function digestFindings(
  refs: DigestRef[],
  answers: Map<string, TagAnswer>,
  leafOf: (r: DigestRef) => string | null
): { findings: string[]; agreed: number; unjudged: string[] } {
  const findings: string[] = [];
  const unjudged: string[] = [];
  let agreed = 0;
  for (const r of refs) {
    const at = `${r.file}:${r.line}`;
    if (r.tag === null) {
      unjudged.push(`${at}  ${r.image}@${r.digest}: untagged, agreement not checkable`);
      continue;
    }
    if (hubRepo(r.image) === null) {
      unjudged.push(
        `${at}  ${r.image}:${r.tag}@${r.digest}: not a Docker Hub image, agreement not checked`
      );
      continue;
    }
    const ref = `${r.image}:${r.tag}`;
    const a = answers.get(ref);
    if (a === undefined || a.digest === null) {
      findings.push(
        `${at}  ${ref}@${r.digest}: the index digest of ${ref} could NOT be read from Docker Hub (${a?.why ?? 'no lookup was made'}). Unknown is not agreement.`
      );
      continue;
    }
    if (a.digest === r.digest) {
      agreed++;
      continue;
    }
    const leaf = leafOf(r);
    findings.push(
      `${at}  ${ref}@${r.digest}: Docker Hub serves ${a.digest} for ${ref}, so this line pulls another image than its tag names. ` +
        (leaf === null
          ? 'No docker leaf of .ci/config/pins.json claims the line; give the leaf that pins it a site with role digest, then bump it.'
          : `Move the tag and the digest together: npm run pins -- bump ${leaf} --to ${ref} --major --reason "<why>" (the core refuses a target equal to the pinned tag, so with no newer tag this waits on a re-digest path; never hand-edit the digest).`)
    );
  }
  return { findings, agreed, unjudged };
}

/** A numeric series, so `3.9-slim` and `3.13-slim` are comparable but `bookworm` is not. */
export function series(tag: string): number[] | null {
  const m = /^v?(\d+)(?:\.(\d+))?/.exec(tag);
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
export function staleEvidence(tag: string, tags: TagInfo[], now: number, win: number): TagInfo[] {
  const newer = tags
    .filter((t) => isNewer(tag, t.name))
    .sort((a, b) => (isNewer(a.name, b.name) ? 1 : -1));
  if (newer.length === 0) return [];
  const newest = newer[0];
  const soaked = newest.pushedMs !== null && isWithinFreshnessWindow(newest.pushedMs, now, win);
  return soaked ? newer.slice(1) : newer;
}

// No repo parameter: Docker Hub login is account-wide, not per-repository. The repo argument this used to take was never read, and this config's policy is to delete an unused parameter rather than underscore it. Memoised for the same reason there is no repo parameter: login is account-wide, so the per-image call site was paying one extra login round-trip PER IMAGE for a value that
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

const HUB_BASE = process.env.DOCKER_HUB_API_BASE;

/**
 * One Docker Hub API read, parsed JSON, or null with its cause recorded in `lastFailure` under
 * `key`.
 *
 * A REJECTED CREDENTIAL MUST NOT BE WORSE THAN NO CREDENTIAL.
 *
 * Measured on CI run 32200906643: the job received DOCKERHUB_TOKEN (the step env shows it masked), every one of the five images failed to list, and the same gate had listed them anonymously in earlier runs of this branch. So the token was being rejected and sending it unconditionally turned a working anonymous path into a total failure.
 *
 * A token still buys the higher rate limit when it is valid, so it is tried FIRST. On a 401 or 403 the request is retried without it; anything else, 429 included, stays a failure, because a rate limit is genuinely unknown and unknown is never a pass.
 */
async function hubGetJson(url: string, key: string): Promise<unknown | null> {
  const token = HUB_BASE ? null : await hubToken();
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
        const j: unknown = await r.json();
        lastFailure.delete(key);
        return j;
      }
      why = `HTTP ${r.status} (${attempt.label})`;
      // Only a rejected credential is worth retrying without it.
      if (r.status !== 401 && r.status !== 403) break;
    } catch (e) {
      why = `${(e as Error).name} (${attempt.label})`;
      break;
    }
  }
  lastFailure.set(key, why);
  return null;
}

async function listHubTags(repo: string): Promise<TagInfo[] | null> {
  const url = `${HUB_BASE || HUB_DEFAULT_BASE}/v2/repositories/${repo}/tags?page_size=100&ordering=last_updated`;
  const j = (await hubGetJson(url, repo)) as {
    results?: { name: string; last_updated?: string }[];
  } | null;
  if (j === null) return null;
  return (j.results ?? []).map((t) => ({
    name: t.name,
    pushedMs: t.last_updated ? Date.parse(t.last_updated) : null,
  }));
}

/** The index digest Docker Hub serves for `<image>:<tag>`, or a null digest with the cause. */
async function hubTagDigest(repo: string, tag: string): Promise<TagAnswer> {
  const key = `${repo}:${tag}`;
  const j = await hubGetJson(hubTagUrl(HUB_BASE || HUB_DEFAULT_BASE, repo, tag), key);
  if (j === null) return { digest: null, why: lastFailure.get(key) ?? 'the lookup failed' };
  const digest = parseTagDigest(j);
  return digest === null
    ? { digest: null, why: 'the answer carries no top-level sha256 index digest' }
    : { digest };
}

/**
 * The Dockerfiles and compose files git can see, which both scans read: every tracked one
 * (submodules included, dot directories included), plus untracked ones git does not ignore.
 * Two reads, because `--recurse-submodules` refuses `--others`.
 *
 * WHY GIT AND NOT A WALK. A path git IGNORES must stay out, because CI cannot see it and a
 * baseline entry it cannot reproduce is a permanent red. Measured: `private/growth` is a git
 * repo under `private/` that is NOT a console submodule and IS gitignored, so it exists only
 * on the operator's machine; its stale `youtube-transcripts/Dockerfile` pin went into this
 * baseline and then failed CI with "1 baselined pin(s) are no longer stale". Submodule
 * contents, by contrast, ARE checked out in CI, and `--recurse-submodules` lists them.
 *
 * The walk this replaced (a hand-rolled copy of `glob` with its `dot: false` default) skipped
 * every directory whose name starts with a dot, so .ci/docker/*, .ci/media/tts and
 * .devcontainer were never judged, although .ci/config/pins.json claims sites in all of them.
 */
function gitVisibleImageFiles(): string[] {
  const ls = (args: string[]): string[] => {
    const r = spawnSync('git', ['ls-files', '-z', ...args], {
      cwd: ROOT,
      encoding: 'utf8',
      maxBuffer: 256 * 1024 * 1024,
    });
    if (r.error || r.status !== 0) {
      console.error(
        `\u2717 git ls-files ${args.join(' ')} could not answer (status ${r.status}): ${r.stderr?.trim()}`
      );
      process.exit(1);
    }
    return r.stdout.split('\0');
  };
  const isImageFile = (f: string): boolean =>
    /(^|\/)(Dockerfile[^/]*|(docker-)?compose[^/]*\.ya?ml)$/.test(f);
  const tracked = ls(['--recurse-submodules']).filter(isImageFile);
  const untracked = ls(['--others', '--exclude-standard']).filter(isImageFile);
  const trackedParts = partitionExisting(tracked, (f) => existsSync(path.join(ROOT, f)));
  if (trackedParts.missing.length > 0) {
    console.error(
      `\u2717 ${trackedParts.missing.length} tracked image file(s) are listed by git but missing from the tree, so the gate cannot judge them:\n${trackedParts.missing.map((f) => `  ${f}`).join('\n')}`
    );
    process.exit(1);
  }
  // `ls-files --recurse-submodules` lists nothing inside an UNINITIALISED submodule, so its image
  // files never reach `missing`; name each such submodule as unjudged rather than claim coverage.
  const subStatus = spawnSync('git', ['submodule', 'status', '--recursive'], {
    cwd: ROOT,
    encoding: 'utf8',
  });
  if (subStatus.error || subStatus.status !== 0 || typeof subStatus.stdout !== 'string') {
    const why = subStatus.error
      ? `could not start git: ${subStatus.error.message}`
      : `exit ${subStatus.status}: ${(subStatus.stderr ?? '').toString().trim() || 'no output'}`;
    console.error(
      `\u2717 \`git submodule status --recursive\` failed (${why}), so the gate cannot tell which submodules are uninitialised and refuses a verdict; fix git or the checkout and re-run.`
    );
    process.exit(1);
  }
  let uninit: string[];
  try {
    uninit = uninitialisedSubmodules(subStatus.stdout);
  } catch (e) {
    console.error(`\u2717 ${e instanceof Error ? e.message : String(e)}`);
    process.exit(1);
  }
  for (const sub of uninit) {
    console.log(`! ${sub}: uninitialised submodule, its image files are not judged`);
  }
  const untrackedParts = partitionExisting(untracked, (f) => existsSync(path.join(ROOT, f)));
  return [...new Set([...trackedParts.present, ...untrackedParts.present])].sort(
    (a, b) => Number(a > b) - Number(a < b)
  );
}

/**
 * Splits a file list by presence on disk. Pure: `exists` is injected. A TRACKED file in `missing`
 * fails the gate; an untracked candidate that vanished is exempt (the caller ignores its `missing`).
 */
export function partitionExisting(
  files: string[],
  exists: (f: string) => boolean
): { present: string[]; missing: string[] } {
  const present: string[] = [];
  const missing: string[] = [];
  for (const f of files) (exists(f) ? present : missing).push(f);
  return { present, missing };
}

/**
 * The paths of UNINITIALISED submodules in `git submodule status --recursive` output (lines
 * starting with `-`); initialised (` `), modified (`+`) and conflicted (`U`) lines are not named.
 * A line that cannot be parsed throws, so a format change is loud rather than silently empty. Pure.
 */
export function uninitialisedSubmodules(out: string): string[] {
  const paths: string[] = [];
  for (const line of out.split('\n')) {
    if (line.trim() === '' || !line.startsWith('-')) continue;
    // A SHA-1 (40) or SHA-256 (64) object name; the path runs to the end of the line, or to the
    // ` (<describe>)` git appends, so a path with a space is named whole.
    const m = /^-(?:[0-9a-f]{64}|[0-9a-f]{40}) (.+?)(?: \([^()]*\))?$/.exec(line);
    if (!m) throw new Error(`unparseable \`git submodule status\` line: ${JSON.stringify(line)}`);
    paths.push(m[1]);
  }
  return paths;
}

/**
 * The `docker` leaf whose site matches this pin's FROM line in its file (the file is
 * repo-relative to the console; a site in a submodule is `<repo>/<file>`), or null. Pure.
 */
export function leafFor(p: Pin, entries: PinEntry[]): string | null {
  for (const e of entries) {
    if (e.kind !== 'leaf' || e.driver !== 'docker') continue;
    for (const s of e.sites) {
      if ((s.repo === '.' ? s.file : `${s.repo}/${s.file}`) !== p.file) continue;
      const re = siteRegex(s, '');
      if (re?.test(p.text)) return e.id;
    }
  }
  return null;
}

/** The FROM pins no docker leaf's site matches, each with the entry shape that would claim it. Pure. */
export function unclaimedPins(pins: Pin[], entries: PinEntry[]): string[] {
  return pins
    .filter((p) => leafFor(p, entries) === null)
    .map(
      (p) =>
        `${p.file}:${p.line}  ${p.image}:${p.tag}: no docker leaf of .ci/config/pins.json has a site matching this FROM line; add one (driver docker, source dockerhub with image ${p.image}, a version site whose match covers the whole line text, including any leading whitespace or --platform flag; image:proxy-node is the shape) so \`npm run pins -- bump <its id>\` can move it`
    );
}

function selftest(): { bad: number; total: number } {
  let bad = 0;
  let total = 0;
  const check = (label: string, ok: boolean) => {
    console.log(`  ${ok ? `${GREEN}PASS${NC}` : `${RED}FAIL${NC}`}  ${label}`);
    total++;
    if (!ok) bad++;
  };
  const pins = parsePins(
    `FROM node:22-slim AS build\nFROM ${WK_IMAGE_REGISTRY}/renet:latest\n`,
    'X'
  );
  check('a FROM pin is parsed', pins.length === 1 && pins[0].image === 'node');
  const flagged = parsePins(
    'FROM --platform=$BUILDPLATFORM node:20 AS build\nFROM --platform=linux/amd64 --other=x golang:1.26\nFROM $BASE:1\n',
    'F'
  );
  check(
    'CONTROL: a FROM with --flag=value options is still parsed (an unparsed one is neither claimed nor checked)',
    flagged.length === 2 && flagged[0].image === 'node' && flagged[1].image === 'golang'
  );
  check(
    'an indented FROM is parsed with its whitespace kept, so a leaf match must cover it',
    parsePins('  FROM node:20\n', 'F')[0]?.text === '  FROM node:20'
  );
  check(
    'our OWN ghcr images are not treated as upstream pins',
    !pins.some((p) => p.image.includes('rediacc'))
  );
  const sha = 'a'.repeat(40);
  const subOut = `-${sha} private/one\n ${sha} private/two (v1)\n+${sha} private/three\n`;
  check(
    'CONTROL: an uninitialised submodule (- line) is named, an initialised (space) or modified (+) one is not',
    uninitialisedSubmodules(subOut).join() === 'private/one'
  );
  check(
    'CONTROL: a nested uninitialised submodule line (recursive output) is named by its full path',
    uninitialisedSubmodules(` ${sha} private/two\n-${sha} private/two/nested\n`).join() ===
      'private/two/nested'
  );
  check(
    'CONTROL: a malformed - line is refused, not skipped',
    (() => {
      try {
        uninitialisedSubmodules('-garbage\n');
        return false;
      } catch {
        return true;
      }
    })()
  );
  check('CONTROL: empty output names nothing', uninitialisedSubmodules('').length === 0);
  check(
    'a path with a space is named whole, without the describe suffix (review d8a578fc.1)',
    uninitialisedSubmodules(`-${sha} private/my repo (v1.2-3-gabc)\n`).join() === 'private/my repo'
  );
  check(
    'a SHA-256 object name parses (review d8a578fc.2)',
    uninitialisedSubmodules(`-${'a'.repeat(64)} private/three\n`).join() === 'private/three'
  );
  check('CONTROL: a newer minor in the same shape is newer', isNewer('3.9-slim', '3.13-slim'));
  check('CONTROL: a newer major is newer', isNewer('22-slim', '24-slim'));
  check('a DIFFERENT shape is not comparable', !isNewer('3.9-slim', '3.13-alpine'));
  check('an older version is not newer', !isNewer('24.04', '22.04'));

  // --- the soak clock: rebuild age is not release age ----------------------- Measured against library/python on 2026-08-25: a rebuild wave re-stamped every supported minor within the same minute, which under the old filter hid all of them and made a 3.9-slim pin read as current.
  const HOUR = 3600_000;
  const DAY = 24 * HOUR;
  const NOW = 1_000 * DAY;
  const SOAK = DAY;
  const tag = (name: string, ageMs: number): TagInfo => ({ name, pushedMs: NOW - ageMs });

  check(
    'a rebuild wave does NOT make an established newer series invisible',
    staleEvidence('3.9-slim', [tag('3.14-slim', HOUR), tag('3.10-slim', HOUR)], NOW, SOAK).length >
      0
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
  check('the shared freshness window is configured (.ci/config/release-age.json)', win > 0);
  check(
    'CONTROL: a release published right now is deferred',
    isWithinFreshnessWindow(Date.now(), Date.now(), win)
  );

  // THE SHRINK-ONLY COMPOSITION RULE, shared with every other baselined gate here.
  for (const c of sharedSelftestCases()) check(c.name, c.ok);

  // A TRACKED file missing from the tree must be reported, never silently dropped.
  const planted = partitionExisting(['a/Dockerfile', 'b/Dockerfile'], (f) => f === 'a/Dockerfile');
  check(
    'CONTROL: a planted missing tracked path lands in missing, naming it',
    planted.missing.join(',') === 'b/Dockerfile' && planted.present.join(',') === 'a/Dockerfile'
  );
  check(
    'a present tracked path leaves missing empty',
    partitionExisting(['a/Dockerfile'], () => true).missing.length === 0
  );

  // THE SEED PATH, and its control. A grow path that admits anything is not a grow path, it is the absence of a gate.
  const seedFilter = (additions: string[], seed?: string): string[] =>
    additions.filter((a) => a !== seed);
  check('a seeded entry is admitted', seedFilter(['a:1  img'], 'a:1  img').length === 0);
  check(
    'CONTROL: a second addition alongside the seed is STILL refused',
    seedFilter(['a:1  img', 'b:2  other'], 'a:1  img').join(',') === 'b:2  other'
  );
  check('CONTROL: no seed admits nothing', seedFilter(['a:1  img'], undefined).length === 1);

  // EVERY FROM IMAGE HAS ITS LEAF, matched by LINE: the console's own registry, three images in one renet Dockerfile.
  const real = loadRegistry(
    path.resolve(import.meta.dirname, '..', '..', '.ci/config/pins.json')
  ).entries;
  const renet = parsePins(
    'FROM debian:bookworm AS criu-source\nFROM ubuntu:24.04 AS rsync-builder-amd64\nFROM golang:1.26-bookworm AS csi-builder\n',
    'private/renet/Dockerfile'
  );
  check(
    'one Dockerfile, three FROM images: each line finds its own leaf, not the first leaf of the file',
    renet.map((p) => leafFor(p, real)).join(',') ===
      'image:renet-debian,image:renet-ubuntu,image:renet-csi-golang'
  );
  check(
    'CONTROL: every FROM with a leaf leaves nothing unclaimed',
    unclaimedPins(renet, real).length === 0
  );
  const strays = [
    ...parsePins('FROM node:24-slim\n', 'tools/Dockerfile'),
    ...parsePins('FROM alpine:3.20 AS extra\n', 'private/renet/Dockerfile'),
  ];
  const un = unclaimedPins(strays, real);
  check(
    'a FROM in an unclaimed file, and a new FROM line in a claimed file, are both unclaimed, by file and line',
    un.length === 2 &&
      un[0].startsWith('tools/Dockerfile:1  node:24-slim') &&
      un[1].startsWith('private/renet/Dockerfile:1  alpine:3.20')
  );

  // THE DIGEST AGREES WITH THE TAG (#d4b2a051).
  const dA = `sha256:${'a'.repeat(64)}`;
  const dB = `sha256:${'b'.repeat(64)}`;
  check(
    'a FROM pinned by tag and digest parses both',
    parsePins(`FROM node:26.13.0-slim@${dA}\n`, 'D')[0]?.digest === dA &&
      parsePins(`FROM node:26.13.0-slim@${dA}\n`, 'D')[0]?.tag === '26.13.0-slim'
  );
  check(
    'CONTROL: a FROM with no digest carries none',
    parsePins('FROM node:26\n', 'D')[0]?.digest === undefined
  );
  const refs = [
    ...digestRefs(
      `FROM node:26.13.0-slim@${dA}\n# tsl0922/ttyd:1.7.8-alpine@${dB}\nCOPY --from=tsl0922/ttyd@${dB} /usr/bin/ttyd /usr/bin/ttyd\n`,
      'Dockerfile'
    ),
    ...digestRefs(
      `services:\n  s3:\n    image: rustfs/rustfs@${dA}\n  db:\n    image: "postgres:17@${dB}"\n`,
      'compose.yml'
    ),
  ];
  check(
    'digest refs: a tagged FROM is image node with its tag, an untagged COPY --from and compose image have no tag, a quoted compose ref keeps its tag, a comment is skipped',
    JSON.stringify(refs.map((r) => [r.file, r.line, r.image, r.tag])) ===
      JSON.stringify([
        ['Dockerfile', 1, 'node', '26.13.0-slim'],
        ['Dockerfile', 3, 'tsl0922/ttyd', null],
        ['compose.yml', 3, 'rustfs/rustfs', null],
        ['compose.yml', 5, 'postgres', '17'],
      ])
  );
  check(
    'parseTagDigest reads the top-level index digest',
    parseTagDigest({ digest: dA, images: [{ digest: dB }] }) === dA
  );
  check(
    'CONTROL: an images[]-only answer, a malformed digest and a non-object all read null',
    parseTagDigest({ images: [{ digest: dB }] }) === null &&
      parseTagDigest({ digest: 'sha256:abc' }) === null &&
      parseTagDigest(null) === null
  );
  check(
    'hubRepo: an official image gains library/, docker.io/ is dropped, another registry is null',
    hubRepo('node') === 'library/node' &&
      hubRepo('docker.io/tsl0922/ttyd') === 'tsl0922/ttyd' &&
      hubRepo('mcr.microsoft.com/x') === null
  );
  const proxy = digestRefs(`FROM node:26.13.0-slim@${dA}\n`, 'workers/proxy/Dockerfile');
  const leafOf = () => 'image:proxy-node';
  const mismatch = digestFindings(proxy, new Map([['node:26.13.0-slim', { digest: dB }]]), leafOf);
  check(
    'CONTROL: a digest that differs from the one Hub serves for the tag is a finding naming the bump',
    mismatch.findings.length === 1 &&
      mismatch.findings[0].startsWith('workers/proxy/Dockerfile:1') &&
      mismatch.findings[0].includes('npm run pins -- bump image:proxy-node --to node:26.13.0-slim')
  );
  check(
    'CONTROL: no answer, and a failed lookup, are both findings (unknown is not agreement)',
    digestFindings(proxy, new Map(), leafOf).findings.length === 1 &&
      digestFindings(
        proxy,
        new Map([['node:26.13.0-slim', { digest: null, why: 'HTTP 429' }]]),
        leafOf
      ).findings[0]?.includes('HTTP 429') === true
  );
  const agree = digestFindings(proxy, new Map([['node:26.13.0-slim', { digest: dA }]]), leafOf);
  check(
    'a digest equal to the one Hub serves agrees',
    agree.findings.length === 0 && agree.agreed === 1
  );
  const unj = digestFindings(refs.slice(1, 3), new Map(), leafOf);
  check(
    'untagged refs are listed unjudged, never a finding and never agreement',
    unj.findings.length === 0 &&
      unj.agreed === 0 &&
      unj.unjudged.length === 2 &&
      unj.unjudged.every((u) => u.includes('untagged, agreement not checkable'))
  );

  return { bad, total };
}

async function main(): Promise<void> {
  if (process.argv.includes('--selftest')) {
    console.log('docker image freshness selftest');
    const { bad, total } = selftest();
    console.log(
      bad === 0
        ? `\n${GREEN}✓${NC} ${total}/${total} controls pass`
        : `\n${RED}✗${NC} ${bad} of ${total} failed`
    );
    process.exit(bad === 0 ? 0 : 1);
  }
  if (selftest().bad !== 0) {
    console.error('controls failed; the gate cannot be trusted');
    process.exit(1);
  }

  const imageFiles = gitVisibleImageFiles();
  const pins: Pin[] = [];
  for (const f of imageFiles.filter((x) => /(^|\/)Dockerfile[^/]*$/.test(x)))
    pins.push(...parsePins(readFileSync(path.join(ROOT, f), 'utf8'), f));

  if (pins.length === 0) {
    console.error(
      '✗ zero image pins found. The gate is not seeing the tree; its green would mean nothing.'
    );
    process.exit(1);
  }

  // Every FROM image has its own docker leaf, read from the registry of the tree being scanned.
  const entries = loadRegistry(path.join(ROOT, '.ci/config/pins.json')).entries;
  const unclaimed = unclaimedPins(pins, entries);
  if (unclaimed.length > 0) {
    console.error(
      `\n${RED}✗${NC} ${unclaimed.length} FROM image pin(s) have no docker leaf, so no \`npm run pins\` command can move them:\n`
    );
    for (const u of unclaimed) console.error(`    ${u}`);
    process.exit(1);
  }

  const win = getMinReleaseAgeMs();
  const now = Date.now();
  const stale: string[] = [];
  const stalePins: Pin[] = [];
  // BASELINE IDENTITY, kept separate from the DISPLAY string above it. `stale[i]` embeds `file:line` for a human to find the pin; `staleKeys[i]` (same index, same order) is `image:tag` alone, which `seen` already proves is globally unique. A baseline keyed on the display string re-keys itself on any Dockerfile edit that shifts the FROM line -- a comment added above it, an
  // unrelated stage inserted earlier in the file -- reporting the SAME unresolved debt as simultaneously "newly stale" (new key, not in the old baseline) and "no longer stale" (old key, missing from the new run). Same
  // shape as the CSS-selector re-keying trap this repo already paid for once;
  // this baseline's key must not depend on anything that can move independent of the finding itself.
  const staleKeys: string[] = [];
  const unknown: string[] = [];
  let checked = 0;

  const seen = new Map<string, Pin>();
  for (const p of pins) if (!seen.has(`${p.image}:${p.tag}`)) seen.set(`${p.image}:${p.tag}`, p);

  for (const p of seen.values()) {
    const repo = hubRepo(p.image);
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
      staleKeys.push(`${p.image}:${p.tag}`);
      stalePins.push(p);
    }
  }

  // THE DIGEST AGREES WITH THE TAG, over every tracked Dockerfile and compose file.
  if (imageFiles.length === 0) {
    console.error(
      '✗ zero tracked Dockerfiles or compose files. The digest scan is not seeing the tree; its green would mean nothing.'
    );
    process.exit(1);
  }
  const refs: DigestRef[] = [];
  for (const f of imageFiles) refs.push(...digestRefs(readFileSync(path.join(ROOT, f), 'utf8'), f));
  const answers = new Map<string, TagAnswer>();
  for (const r of refs) {
    const repo = hubRepo(r.image);
    if (r.tag === null || repo === null || answers.has(`${r.image}:${r.tag}`)) continue;
    answers.set(`${r.image}:${r.tag}`, await hubTagDigest(repo, r.tag));
  }
  const digests = digestFindings(refs, answers, (r) =>
    leafFor({ image: r.image, tag: r.tag ?? '', file: r.file, line: r.line, text: r.text }, entries)
  );
  for (const u of digests.unjudged) console.log(`${YELLOW}!${NC} ${u}`);
  if (digests.findings.length > 0) {
    console.error(
      `\n${RED}✗${NC} ${digests.findings.length} digest-pinned line(s) do not agree with the tag they name:\n`
    );
    for (const f of digests.findings) console.error(`    ${f}`);
  }

  if (unknown.length > 0) {
    console.error(
      `\n${RED}✗${NC} ${unknown.length} image(s) could NOT be checked. Unknown is not a pass:`
    );
    for (const u of unknown) console.error(`    ${u}`);
    console.error('\nDocker Hub rate limits anonymous listings. Set DOCKERHUB_TOKEN (or');
    console.error('DOCKERHUB_USERNAME + DOCKERHUB_PASSWORD) so this cannot go vacuous in CI.');
    process.exit(1);
  }
  if (digests.findings.length > 0) process.exit(1);
  // SHRINK-ONLY BASELINE, the same shape the other debt gates here use. Adding this gate must not turn `npm run ci` red on staleness that predates it, and bumping a base image across a major (ubuntu 24.04 -> 26.10, python 3.9 -> 3.14) is a decision with real blast radius, not a side effect of installing a watchdog. So today's debt is frozen and NEW staleness fails immediately.
  // Drain with --write-baseline as pins move.
  const keyed = staleKeys;
  if (process.argv.includes('--write-baseline')) {
    // COMPOSITION. "Drain with --write-baseline as pins move" was an unconditional reseed, so a drain could retire two pins that had been bumped and quietly enshrine a third that had just gone stale, while printing a smaller number. A newly stale pin is the exact finding this gate exists to raise, so absorbing one silently inverts its purpose.
    const sorted = keyed.slice().sort();
    const had = existsSync(BASELINE);
    const previous: string[] = had ? JSON.parse(readFileSync(BASELINE, 'utf8')) : [];
    // THE ONE LEGITIMATE GROW PATH: a pin deliberately held BACK.
    //
    // Shrink-only is right for debt that should be paid down, and wrong for a pin that must not move. Measured on 2026-08-24: renet's CSI sidecar stage tracked upstream Go to 1.27, and under 1.27 the upstream sidecars' own VENDORED grpc stops compiling (`undefined: http2.TrailerPrefix`). The only fix available to us is to stay on 1.26, and with no grow path that decision could not
    // be recorded at all -- so the gate would demand a bump that breaks the build, every run, forever.
    //
    // `--seed-image <entry>` names the exact entry being admitted, so admitting one cannot smuggle in a second: anything else that went stale in the same run is still refused.
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
        `\n${RED}✗${NC} --seed-image named ${JSON.stringify(seedImage)}, which is not ` +
          "among this run's additions. A seed that matches nothing is a typo, and accepting " +
          'it would let the next real addition through unnoticed.'
      );
      process.exit(1);
    }
    if (verdict !== null) {
      console.error(
        `\n${RED}✗${NC} ${renderRefusal(verdict, {
          baselineLabel: path.relative(ROOT, BASELINE),
          noun: 'known-stale pin',
          previousCount: previous.length,
          newCount: sorted.length,
          // Without this the refusal says "do not add it to the baseline" and stops,
          // which is now only HALF true: a pin deliberately held back has a sanctioned
          // path, and a message that hides it sends the reader either to a bump that
          // breaks the build or to editing the JSON by hand.
          seedHelp:
            '--write-baseline --seed-image "<image>:<tag>"  (ONE deliberately ' +
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
  // Filtered by INDEX against staleKeys, not re-derived from the display string: `stale[i]` and `staleKeys[i]` are the same pin, one for a human, one for identity.
  const freshIdx = stale.flatMap((_, i) => (known.has(staleKeys[i]) ? [] : [i]));
  const fresh = freshIdx.map((i) => stale[i]);
  const fixed = base.filter((b) => !keyed.includes(b));

  if (fresh.length > 0) {
    console.error(
      `\n${RED}✗${NC} ${fresh.length} base image pin(s) newly stale past the soak window:\n`
    );
    for (const i of freshIdx) {
      console.error(`    ${stale[i]}`);
      console.error(bumpRemedy(leafFor(stalePins[i], entries) as string, { major: true }));
    }
    errorLines(
      `\nThe window is the SHARED one from .ci/config/release-age.json (${win / 60000} min,`,
      'rounded up to the next UTC day) so a day of upgrades surfaces together.',
      'Bump the pin. Do not add it to the baseline.'
    );
    process.exit(1);
  }
  if (fixed.length > 0) {
    console.error(
      `\n${RED}✗${NC} ${fixed.length} baselined pin(s) are no longer stale. This baseline is`
    );
    console.error(
      'SHRINK-ONLY, so drain it: npx tsx scripts/gates/check-docker-image-freshness.ts --write-baseline'
    );
    for (const f of fixed) console.error(`    ${f}`);
    process.exit(1);
  }
  if (stale.length > 0) {
    console.log(
      `${YELLOW}!${NC} ${stale.length} known-stale pin(s) still baselined (drain as they are bumped):`
    );
    for (const s of stale) console.log(`    ${s}`);
  }
  console.log(
    `${GREEN}✓${NC} ${checked} Docker Hub pin(s) checked, ${checked - stale.length} current, ` +
      `${stale.length} known-stale and baselined. No NEW staleness. ${pins.length} literal image:tag FROM line(s) (variable-image FROMs carry no pin), each claimed by a docker leaf. ` +
      `${refs.length} digest-pinned reference(s) in ${imageFiles.length} tracked Dockerfile/compose file(s): ${digests.agreed} agree with Docker Hub, ${digests.unjudged.length} listed unjudged.`
  );
}

main().catch((e) => {
  console.error('gate crashed:', e);
  process.exit(1);
});
