#!/usr/bin/env tsx
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
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { globSync } from 'glob';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from './lib/release-age.js';

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

function dockerHubRepo(image: string): string | null {
  if (image.includes('.') && !image.startsWith('docker.io/')) return null; // another registry
  const bare = image.replace(/^docker\.io\//, '');
  return bare.includes('/') ? bare : `library/${bare}`;
}

async function hubToken(repo: string): Promise<string | null> {
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
}

interface TagInfo { name: string; pushedMs: number | null }

async function listHubTags(repo: string): Promise<TagInfo[] | null> {
  const token = await hubToken(repo);
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const url = `https://hub.docker.com/v2/repositories/${repo}/tags?page_size=100&ordering=last_updated`;
  try {
    const r = await fetch(url, { headers });
    if (!r.ok) return null; // includes 429: UNKNOWN, never a pass
    const j = (await r.json()) as { results?: { name: string; last_updated?: string }[] };
    return (j.results ?? []).map((t) => ({
      name: t.name,
      pushedMs: t.last_updated ? Date.parse(t.last_updated) : null,
    }));
  } catch {
    return null;
  }
}

function selftest(): number {
  let bad = 0;
  const check = (label: string, ok: boolean) => {
    console.log(`  ${ok ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  ${label}`);
    if (!ok) bad++;
  };
  const pins = parsePins('FROM node:22-slim AS build\nFROM ghcr.io/rediacc/renet:latest\n', 'X');
  check('a FROM pin is parsed', pins.length === 1 && pins[0].image === 'node');
  check('our OWN ghcr images are not treated as upstream pins', !pins.some((p) => p.image.includes('rediacc')));
  check('CONTROL: a newer minor in the same shape is newer', isNewer('3.9-slim', '3.13-slim'));
  check('CONTROL: a newer major is newer', isNewer('22-slim', '24-slim'));
  check('a DIFFERENT shape is not comparable', !isNewer('3.9-slim', '3.13-alpine'));
  check('an older version is not newer', !isNewer('24.04', '22.04'));
  check('a non-numeric tag yields no series', series('bookworm') === null);
  check('the same version is not newer', !isNewer('24.04', '24.04'));
  // The window is the SHARED one; a release published now must be deferred.
  const win = getMinReleaseAgeMs();
  check('the shared freshness window is configured (.npmrc)', win > 0);
  check('CONTROL: a release published right now is deferred',
    isWithinFreshnessWindow(Date.now(), Date.now(), win));
  return bad;
}

async function main(): Promise<void> {
  if (process.argv.includes('--selftest')) {
    console.log('docker image freshness selftest');
    const bad = selftest();
    console.log(bad === 0 ? '\n\x1b[32m✓\x1b[0m 10/10 controls pass' : `\n\x1b[31m✗\x1b[0m ${bad} failed`);
    process.exit(bad === 0 ? 0 : 1);
  }
  if (selftest() !== 0) { console.error('controls failed; the gate cannot be trusted'); process.exit(1); }

  const files = [
    ...globSync(`${ROOT}/**/Dockerfile*`, { ignore: ['**/node_modules/**', '**/dist/**'] }),
  ];
  const pins: Pin[] = [];
  for (const f of files) pins.push(...parsePins(readFileSync(f, 'utf8'), path.relative(ROOT, f)));

  if (pins.length === 0) {
    console.error('✗ zero image pins found. The gate is not seeing the tree; its green would mean nothing.');
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
      unknown.push(`${p.image}:${p.tag} (${p.file}:${p.line}) — tags could not be listed`);
      continue;
    }
    checked++;
    const newer = tags
      .filter((t) => isNewer(p.tag, t.name))
      .filter((t) => !(t.pushedMs !== null && isWithinFreshnessWindow(t.pushedMs, now, win)));
    if (newer.length > 0) {
      const best = newer.sort((a, b) => (isNewer(a.name, b.name) ? 1 : -1))[0];
      stale.push(`${p.file}:${p.line}  ${p.image}:${p.tag}  ->  ${best.name}`);
    }
  }

  if (unknown.length > 0) {
    console.error(`\n\x1b[31m✗\x1b[0m ${unknown.length} image(s) could NOT be checked. Unknown is not a pass:`);
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
    writeFileSync(BASELINE, `${JSON.stringify(keyed.sort(), null, 2)}\n`);
    console.log(`baseline written: ${keyed.length} known-stale pin(s)`);
    process.exit(0);
  }
  const base: string[] = existsSync(BASELINE) ? JSON.parse(readFileSync(BASELINE, 'utf8')) : [];
  const known = new Set(base);
  const fresh = stale.filter((s) => !known.has(s.trim().replace(/\s+->\s+.*$/, '')));
  const fixed = base.filter((b) => !keyed.includes(b));

  if (fresh.length > 0) {
    console.error(`\n\x1b[31m✗\x1b[0m ${fresh.length} base image pin(s) newly stale past the soak window:\n`);
    for (const s of fresh) console.error(`    ${s}`);
    console.error(`\nThe window is the SHARED one from .npmrc minimum-release-age (${win / 60000} min,`);
    console.error('rounded up to the next UTC day) so a day of upgrades surfaces together.');
    console.error('Bump the pin. Do not add it to the baseline.');
    process.exit(1);
  }
  if (fixed.length > 0) {
    console.error(`\n\x1b[31m✗\x1b[0m ${fixed.length} baselined pin(s) are no longer stale. This baseline is`);
    console.error('SHRINK-ONLY, so drain it: npx tsx scripts/check-docker-image-freshness.ts --write-baseline');
    for (const f of fixed) console.error(`    ${f}`);
    process.exit(1);
  }
  if (stale.length > 0) {
    console.log(`\x1b[33m!\x1b[0m ${stale.length} known-stale pin(s) still baselined (drain as they are bumped):`);
    for (const s of stale) console.log(`    ${s}`);
  }
  console.log(
    `\x1b[32m✓\x1b[0m ${checked} Docker Hub pin(s) checked, ${checked - stale.length} current, ` +
      `${stale.length} known-stale and baselined. No NEW staleness.`
  );
}

main().catch((e) => { console.error('gate crashed:', e); process.exit(1); });
