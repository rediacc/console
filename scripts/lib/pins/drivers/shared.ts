/**
 * What the T8 drivers (actions, go-mod, os-ceph-host, ceph-image, real-provider, docker)
 * share: the network and process seams, the synthetic release a FAMILY driver answers with,
 * a version comparator, and a tracked-file lister.
 *
 * THE SEAMS ARE THE TEST. Every driver is a factory over `Deps`, so the selftest drives the
 * whole inspect and plan path with stub answers, and no driver reads the network, the clock
 * or a process except through this object. `realDeps` is the one place that does.
 *
 * A FAMILY'S SYNTHETIC RELEASE. The core judges one `Release` per entry, and a family
 * (actions, go-mod) bumps many members at once. The driver therefore answers with releases
 * that each STAND FOR A GROUP of members: version `1.<n>` for the n members that may move
 * now, the same shape for the members still inside the release-age window (publishedMs is
 * the newest of them, so `when` names the instant the whole group clears), and `2.<n>` for
 * the major moves. The current value is `1.0`, so the core reads `1.<n>` as in range (what
 * `apply-soaked` takes) and `2.<n>` as a major (taken only with `--major`). The members and
 * their real versions are in `PinPlan.changes`, never in the label.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { getMinReleaseAgeMs } from '../../release-age.js';
import { askUpstream, githubAsker, UnreadableListing } from '../../upstream.js';
import type { Release } from '../driver.js';

/**
 * The T8 selftest's mutants. A factory takes one as its second argument (production passes
 * none), and each disables one safety property so the selftest can prove the case that
 * relies on it goes red:
 *   actions-skip-sites     the registry's sha sites (UPLOAD_ARTIFACT_PIN, the allowlist) are not moved
 *   actions-no-defer       a release inside the window is treated as settled
 *   actions-skip-gate-bind the generated regions are not regenerated after the constant moves
 *   go-allow-major         a Go major is planned like a minor
 *   go-no-mirror           license-mint is not tidied against the bumped renet
 *   os-ignore-tag          a Leap EVR with no obs-mirror tag is taken
 *   os-ignore-series       a Leap EVR of another Ceph series is taken
 *   ceph-ignore-host       a dated tag of another Ceph patch level is taken
 *   docker-no-drain        a bumped pin stays in the shrink-only baseline
 *   docker-keep-digest     a bumped tag keeps the digest of the old tag beside it
 *   docker-skip-redigest   a pinned tag whose served digest moved offers no re-digest
 */
export const T8_MUTANTS = [
  'actions-skip-sites',
  'actions-no-defer',
  'actions-skip-gate-bind',
  'go-allow-major',
  'go-no-mirror',
  'os-ignore-tag',
  'os-ignore-series',
  'ceph-ignore-host',
  'docker-no-drain',
  'docker-keep-digest',
  'docker-skip-redigest',
] as const;
export type T8Mutant = (typeof T8_MUTANTS)[number];

export interface RunResult {
  rc: number;
  /** Both streams, for a message. */
  out: string;
  /** Stdout alone: the machine-readable answer of a probe (its warnings are on stderr). */
  stdout: string;
}

export interface Deps {
  nowMs(): number;
  windowMs(): number;
  /** A GitHub REST path (`/repos/o/r/releases/latest`), parsed JSON. Throws NotCompared when unanswered. */
  github(apiPath: string, who: string): Promise<unknown>;
  /** Any other JSON endpoint (quay, Docker Hub). */
  json(url: string, who: string): Promise<unknown>;
  /** A command line through bash from `cwdAbs`; used for the read-only probes (go_deps, obs_mirror). */
  run(cmd: string, cwdAbs: string): RunResult;
}

/**
 * The seam for the GitHub base is the one check-actions has, ACTIONS_API_BASE: set, the
 * requests go there and carry no token (scripts/lib/upstream.ts githubAsker). A stub server
 * in a test or an offline hand run points the driver and the gate at the same place.
 */
export function realDeps(root: string): Deps {
  const ghBase = process.env.ACTIONS_API_BASE || undefined;
  const gh = githubAsker('pins-command', ghBase);
  return {
    nowMs: () => Date.now(),
    windowMs: () => getMinReleaseAgeMs(path.join(root, '.ci/config/release-age.json')),
    github: (p, who) => gh(p, who),
    async json(url, who) {
      const { body } = await askUpstream({
        url,
        headers: { 'User-Agent': 'pins-command', Accept: 'application/json' },
        who,
      });
      try {
        return JSON.parse(body);
      } catch {
        throw new UnreadableListing('the response is not JSON');
      }
    },
    run(cmd, cwdAbs) {
      const r = spawnSync('bash', ['-c', cmd], {
        cwd: cwdAbs,
        encoding: 'utf8',
        maxBuffer: 256 * 1024 * 1024,
        stdio: ['ignore', 'pipe', 'pipe'],
      });
      return {
        rc: r.status ?? 1,
        out: `${r.stdout ?? ''}${r.stderr ?? ''}`,
        stdout: r.stdout ?? '',
      };
    },
  };
}

/** `1.0`: the current value of every family, so the core reads `1.<n>` as in range and `2.<n>` as a major. */
export const FAMILY_CURRENT = '1.0';

export interface Group<M> {
  members: M[];
  /** Publish instant of the group: the newest member's, so the group is as fresh as its freshest member. */
  publishedMs: number | null;
}

/**
 * The releases a family answers with: eligible members first by number, the still-too-new
 * group before them (the core records the first deferred release it meets and then takes
 * the first eligible one), then the majors with a verdict of their own.
 */
export function familyReleases(
  eligible: Group<unknown>,
  deferred: Group<unknown>,
  major: Group<unknown> & { verdict?: { eligible: boolean; why: string } }
): { releases: Release[]; versions: { eligible: string; deferred: string; major: string } } {
  const ne = eligible.members.length;
  const nd = deferred.members.length;
  const nm = major.members.length;
  const versions = {
    eligible: `1.${ne}`,
    deferred: `1.${ne + nd}`,
    major: `2.${nm}`,
  };
  const releases: Release[] = [];
  if (nd > 0) releases.push({ version: versions.deferred, publishedMs: deferred.publishedMs });
  if (ne > 0) releases.push({ version: versions.eligible, publishedMs: eligible.publishedMs });
  if (nm > 0)
    releases.push({
      version: versions.major,
      publishedMs: major.publishedMs,
      ...(major.verdict ? { verdict: major.verdict } : {}),
    });
  return { releases, versions };
}

/** Compare dotted numeric versions (a leading `v`, a `+suffix`, and a `-pre` tail are ignored): -1, 0, 1. */
export function cmpVersion(a: string, b: string): number {
  const nums = (v: string): number[] =>
    v
      .replace(/^v/, '')
      .split(/[-+]/)[0]
      .split('.')
      .map((x) => Number.parseInt(x, 10) || 0);
  const x = nums(a);
  const y = nums(b);
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const d = (x[i] ?? 0) - (y[i] ?? 0);
    if (d !== 0) return d < 0 ? -1 : 1;
  }
  return 0;
}

const SKIP_DIRS = new Set(['.git', 'node_modules']);

/** `*` within a segment, `**` across segments (and zero of them): the glob dialect of the registry's scopes. */
export function globRe(glob: string): RegExp {
  let src = '';
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === '*' && glob[i + 1] === '*') {
      i++;
      if (glob[i + 1] === '/') {
        i++;
        src += '(?:.*/)?';
      } else src += '.*';
    } else if (c === '*') src += '[^/]*';
    else if (c === '?') src += '[^/]';
    else src += c.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  }
  return new RegExp(`^${src}$`);
}

/**
 * The files of `repo` under `root` that match any of `globs`: git's tracked list when the
 * directory is a repository (what the completeness gate scans), the directory walk otherwise
 * (a fixture that was never `git init`ed).
 */
export function listFiles(root: string, repo: string, globs: string[]): string[] {
  const dir = path.join(root, repo);
  const res = spawnSync('git', ['-C', dir, 'ls-files', '-z'], {
    encoding: 'utf8',
    maxBuffer: 128 * 1024 * 1024,
  });
  let all: string[];
  if (res.status === 0 && res.stdout.length > 0) all = res.stdout.split('\0').filter(Boolean);
  else {
    all = [];
    const walk = (rel: string): void => {
      for (const e of fs.readdirSync(path.join(dir, rel), { withFileTypes: true })) {
        if (SKIP_DIRS.has(e.name)) continue;
        const r = rel === '' ? e.name : `${rel}/${e.name}`;
        if (e.isDirectory()) walk(r);
        else all.push(r);
      }
    };
    walk('');
  }
  if (all.length === 0)
    throw new Error(
      `VACUOUS: ${dir} lists no file at all (git and the directory walk both found none), so a match of ${globs.join(', ')} proves nothing`
    );
  const res2 = globs.map(globRe);
  return all
    .filter((f) => res2.some((re) => re.test(f)))
    .sort((a, b) => Number(a > b) - Number(a < b));
}

export const shq = (s: string): string => `'${s.replace(/'/g, `'\\''`)}'`;

/** The `Y-M-D` of an instant plus `days`, UTC. */
export function dateAfter(ms: number, days: number): string {
  return new Date(ms + days * 86_400_000).toISOString().slice(0, 10);
}

const hostPinFile = { repo: 'private/renet', file: '.ceph-image-pin' };

/** `host-version=` of renet's .ceph-image-pin: the Ceph series every Ceph pin must stay on. */
export function hostVersionOf(read: (p: { repo: string; file: string }) => string | null): string {
  const text = read(hostPinFile);
  const v = text === null ? null : /^host-version[ \t]*=[ \t]*(\S+)[ \t]*$/m.exec(text)?.[1];
  if (!v) throw new Error('private/renet/.ceph-image-pin has no host-version= line');
  return v;
}

/**
 * The Ceph series one host target must stay on: its `host-version.<target>` override when the pin file carries one WITH a
 * `host-version-reason.<target>` line, else the shared `host-version=`. An override without a reason is ignored, so the gate's refusal stands.
 */
export function hostVersionFor(
  read: (p: { repo: string; file: string }) => string | null,
  target: string
): string {
  const text = read(hostPinFile);
  const esc = target.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const override =
    text === null
      ? null
      : new RegExp(`^host-version\\.${esc}[ \\t]*=[ \\t]*(\\S+)[ \\t]*$`, 'm').exec(text)?.[1];
  const reason =
    text === null
      ? null
      : new RegExp(`^host-version-reason\\.${esc}[ \\t]*=[ \\t]*\\S`, 'm').test(text);
  return override && reason ? override : hostVersionOf(read);
}

/** Throw the BLOCKER reason of a `source: none` entry, so the pin reads "not compared: <reason>". */
export function requireSource(entry: {
  id: string;
  source: { type: string; reason?: string };
}): void {
  if (entry.source.type === 'none')
    throw new Error(entry.source.reason ?? `${entry.id} has no source`);
}

export const leafKey = (entry: { id: string }): string => entry.id.slice(entry.id.indexOf(':') + 1);
