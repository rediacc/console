/**
 * Everything an embed-asset upgrade must move together.
 *
 * `check-embed-asset-freshness.ts --upgrade` used to rewrite only
 * `ARG <BASE>_VERSION`. A component is pinned in more places than that: the
 * Dockerfile also holds `ARG <BASE>_COMMIT` (a git clone is asserted against it)
 * and `ARG <BASE>_SHA256[_<ARCH>]` (a download is verified against it),
 * embed-assets.lock.json repeats the version in URLs and carries the same commit
 * and digests, and a few Go constants name the version. Bumping the VERSION alone
 * left a Dockerfile whose own commit check failed the build (csi-provisioner
 * 6.3.0 -> 6.4.0, 2026-10-11).
 *
 * This module is pure: the network sits behind `Fetchers`, so the gate test can
 * drive it with fixtures. An upgrade that cannot resolve a tied pin REFUSES; it
 * never leaves the pin at the old value.
 */

export interface Fetchers {
  /** Commit sha a tag points at (annotated tags dereferenced). */
  commitOf(repo: string, tag: string): Promise<string>;
  /** Body of a text URL (a published checksum file). */
  text(url: string): Promise<string>;
}

export interface UpgradeFiles {
  dockerfile: string;
  /** embed-assets.lock.json text, or null when absent. */
  lock: string | null;
  /** renet-relative path -> content, for every file in SOURCE_CONSTS the caller could read. */
  consts: Record<string, string>;
}

export interface Bump {
  base: string;
  display: string;
  pinned: string;
  latest: string;
  repo?: string;
}

export type UpgradeResult =
  | { ok: true; files: UpgradeFiles; changes: string[] }
  | { ok: false; reason: string };

/** Where a published checksum for a downloaded release binary lives. Absent base = no published checksum, so its sha256 pin cannot be resolved here. */
const SHA256_SOURCES: Record<
  string,
  (version: string, arch: string) => { url: string; file: string }
> = {
  zot: (v, arch) => ({
    url: `https://github.com/project-zot/zot/releases/download/v${v}/checksums.sha256.txt`,
    file: `zot-linux-${arch}`,
  }),
  k3s: (v, arch) => ({
    url: `https://github.com/k3s-io/k3s/releases/download/v${v}/sha256sum-${arch}.txt`,
    file: arch === 'amd64' ? 'k3s' : `k3s-${arch}`,
  }),
};

interface ConstSite {
  /** Path relative to private/renet. */
  file: string;
  /** Group 1 = text kept before the version, group 2 (optional) = text kept after. */
  re: RegExp;
  /** The version as the site spells it. */
  render: (version: string) => string;
}

/** Source and golden files that spell a pinned version outside the Dockerfile and the lockfile. A bump that finds no match REFUSES: the site moved and this table is stale. */
export const SOURCE_CONSTS: Record<string, ConstSite[]> = {
  k3s: [
    {
      file: 'pkg/embed/embed.go',
      re: /(const AssetK3sVersion = ")[^"]*(")/,
      render: (v) => v,
    },
  ],
  csiprovisioner: [
    {
      file: 'pkg/kube/csidriver/units.go',
      re: /(\bProvisionerVersion\s*=\s*")[^"]*(")/,
      render: (v) => `v${v}`,
    },
    {
      file: 'pkg/kube/csidriver/testdata/rediacc-csi-provisioner.service',
      re: /(CSI external-provisioner \()[^,)]*(,)/,
      render: (v) => `v${v}`,
    },
  ],
  csisnapshotter: [
    {
      file: 'pkg/kube/csidriver/units.go',
      re: /(\bSnapshotterVersion\s*=\s*")[^"]*(")/,
      render: (v) => `v${v}`,
    },
  ],
  snapshotcontroller: [
    {
      file: 'pkg/kube/csidriver/units.go',
      re: /(\bSnapshotControllerVersion\s*=\s*")[^"]*(")/,
      render: (v) => `v${v}`,
    },
  ],
};

export const CONST_FILES: string[] = [
  ...new Set(Object.values(SOURCE_CONSTS).flatMap((sites) => sites.map((s) => s.file))),
];

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export interface TiedPin {
  arg: string;
  kind: 'commit' | 'sha256';
  /** Lowercase arch suffix of a `_SHA256_<ARCH>` ARG, if any. */
  arch?: string;
}

/** Every `ARG <BASE>_COMMIT=` / `ARG <BASE>_SHA256[_<ARCH>]=` the Dockerfile ties to a component. */
export function tiedPins(dockerfile: string, base: string): TiedPin[] {
  const b = escapeRe(base.toUpperCase());
  const re = new RegExp(`^ARG\\s+(${b}_(COMMIT|SHA256)(?:_([A-Z0-9]+))?)=`, 'gm');
  const seen = new Set<string>();
  const out: TiedPin[] = [];
  for (const m of dockerfile.matchAll(re)) {
    if (seen.has(m[1])) continue;
    seen.add(m[1]);
    out.push({
      arg: m[1],
      kind: m[2] === 'COMMIT' ? 'commit' : 'sha256',
      arch: m[3]?.toLowerCase(),
    });
  }
  return out;
}

/** Set every occurrence of `ARG <arg>=`; false when the ARG is absent. */
function setArg(dockerfile: string, arg: string, value: string): string {
  return dockerfile.replace(new RegExp(`(^ARG\\s+${escapeRe(arg)}=)\\S+`, 'gm'), `$1${value}`);
}

/** Pull the digest for `file` out of a `<sha256>  <name>` checksum listing. */
export function digestFor(listing: string, file: string): string | null {
  for (const line of listing.split('\n')) {
    const parts = line.trim().split(/\s+/);
    if (parts.length < 2) continue;
    const name = parts[parts.length - 1].replace(/^\*/, '').replace(/^\.\//, '');
    if (name === file && /^[0-9a-f]{64}$/i.test(parts[0])) return parts[0].toLowerCase();
  }
  return null;
}

interface LockComponent {
  version?: string;
  upstreamSourceUrl?: string;
  plannedMirrorUrl?: string;
  source?: {
    tag?: string;
    url?: string;
    commit?: string;
    sha256?: string;
    kind?: string;
    signature?: { url?: string };
  };
  arches?: Record<string, { url?: string; sha256?: string }>;
}

function swap(value: string | undefined, from: string, to: string): string | undefined {
  return value === undefined ? value : value.split(from).join(to);
}

/** Resolve `memo`-ized checksum listings so two arches of one release fetch once. */
function listingFetcher(fetchers: Fetchers): (url: string) => Promise<string> {
  const memo = new Map<string, Promise<string>>();
  return (url) => {
    let hit = memo.get(url);
    if (!hit) {
      hit = fetchers.text(url);
      memo.set(url, hit);
    }
    return hit;
  };
}

/**
 * Move one component from `bump.pinned` to `bump.latest` in the Dockerfile, the
 * lockfile and the Go constants, resolving every commit and digest pin tied to it.
 * Returns a refusal (and no files) when any tied pin cannot be resolved or any
 * site cannot be found.
 */
export async function upgradeComponent(
  files: UpgradeFiles,
  bump: Bump,
  fetchers: Fetchers
): Promise<UpgradeResult> {
  const { base, pinned, latest, repo } = bump;
  const fail = (why: string): UpgradeResult => ({
    ok: false,
    reason: `${bump.display} ${pinned} -> ${latest}: ${why}`,
  });
  const changes: string[] = [];
  let dockerfile = files.dockerfile.replace(
    new RegExp(`(^ARG\\s+${escapeRe(base.toUpperCase())}_VERSION=)\\S+`, 'gm'),
    `$1${latest}`
  );
  changes.push(`Dockerfile ARG ${base.toUpperCase()}_VERSION = ${latest}`);

  let lockObj: { components?: Record<string, LockComponent> } | null = null;
  let comp: LockComponent | undefined;
  if (files.lock !== null) {
    lockObj = JSON.parse(files.lock);
    const table = lockObj?.components;
    comp = table && Object.hasOwn(table, base) ? table[base] : undefined;
    if (!comp) return fail(`embed-assets.lock.json has no components.${base} entry to move`);
  } else {
    return fail('embed-assets.lock.json is absent, so the lockfile pin cannot be moved');
  }
  if (comp.version !== pinned) {
    return fail(
      `embed-assets.lock.json carries version ${comp.version ?? '(none)'}, not the Dockerfile's ${pinned}; reconcile them first (npm run check:ci-embed-credits)`
    );
  }

  const listing = listingFetcher(fetchers);

  // ---- commit pins -------------------------------------------------------------
  const pins = tiedPins(dockerfile, base);
  const lockWantsCommit = comp.source?.kind === 'git' || comp.source?.commit !== undefined;
  const commitArg = pins.find((p) => p.kind === 'commit');
  if (commitArg || lockWantsCommit) {
    if (!repo) return fail('the commit pin cannot be resolved: the component has no GitHub repo');
    let sha: string;
    try {
      sha = (await fetchers.commitOf(repo, `v${latest}`)).trim().toLowerCase();
    } catch (err) {
      return fail(`cannot resolve the commit of ${repo} v${latest} (${(err as Error).message})`);
    }
    if (!/^[0-9a-f]{40}$/.test(sha))
      return fail(`${repo} v${latest} resolved to '${sha}', not a 40-hex commit`);
    if (commitArg) {
      dockerfile = setArg(dockerfile, commitArg.arg, sha);
      changes.push(`Dockerfile ARG ${commitArg.arg} = ${sha}`);
    }
    if (comp.source) {
      comp.source.commit = sha;
      changes.push(`lockfile components.${base}.source.commit = ${sha}`);
    }
  }

  // ---- digest pins -------------------------------------------------------------
  const shaArgs = pins.filter((p) => p.kind === 'sha256');
  const lockSha: Array<{ arch?: string; set: (d: string) => void }> = [];
  if (comp.source?.sha256 !== undefined) {
    lockSha.push({
      set: (d) => {
        if (comp?.source) comp.source.sha256 = d;
      },
    });
  }
  for (const [arch, entry] of Object.entries(comp.arches ?? {})) {
    if (entry.sha256 !== undefined) lockSha.push({ arch, set: (d) => (entry.sha256 = d) });
  }
  const resolved = new Map<string, string>();
  const archesNeeded = new Set<string | undefined>([
    ...shaArgs.map((p) => p.arch),
    ...lockSha.map((p) => p.arch),
  ]);
  if (archesNeeded.size > 0) {
    const source = Object.hasOwn(SHA256_SOURCES, base) ? SHA256_SOURCES[base] : undefined;
    if (!source) {
      return fail(
        `its sha256 pin cannot be resolved: upstream publishes no checksum file this tool reads. Update the digest by hand against upstream's own signature or checksum, in the Dockerfile ARG and embed-assets.lock.json, then re-run`
      );
    }
    for (const arch of archesNeeded) {
      if (!arch)
        return fail('its sha256 pin names no architecture, so no checksum file line can be chosen');
      const { url, file } = source(latest, arch);
      let text: string;
      try {
        text = await listing(url);
      } catch (err) {
        return fail(`cannot fetch ${url} (${(err as Error).message})`);
      }
      const digest = digestFor(text, file);
      if (!digest) return fail(`${url} has no valid sha256 line for '${file}'`);
      resolved.set(arch, digest);
    }
    for (const p of shaArgs) {
      const digest = resolved.get(p.arch as string) as string;
      dockerfile = setArg(dockerfile, p.arg, digest);
      changes.push(`Dockerfile ARG ${p.arg} = ${digest}`);
    }
    for (const l of lockSha) {
      const digest = resolved.get(l.arch as string) as string;
      l.set(digest);
      changes.push(
        `lockfile components.${base}.${l.arch ? `arches.${l.arch}` : 'source'}.sha256 = ${digest}`
      );
    }
  }

  // ---- lockfile version strings (URLs, tag), never the free-text fields ----------
  comp.version = latest;
  comp.upstreamSourceUrl = swap(comp.upstreamSourceUrl, pinned, latest);
  comp.plannedMirrorUrl = swap(comp.plannedMirrorUrl, pinned, latest);
  if (comp.source) {
    comp.source.url = swap(comp.source.url, pinned, latest);
    if (comp.source.tag !== undefined) comp.source.tag = `v${latest}`;
    if (comp.source.signature)
      comp.source.signature.url = swap(comp.source.signature.url, pinned, latest);
  }
  for (const entry of Object.values(comp.arches ?? {})) entry.url = swap(entry.url, pinned, latest);
  changes.push(`lockfile components.${base}: version, tag and URLs moved`);

  // ---- Go constants and goldens ---------------------------------------------------
  const consts = { ...files.consts };
  const sites = Object.hasOwn(SOURCE_CONSTS, base) ? SOURCE_CONSTS[base] : [];
  for (const site of sites) {
    const text = consts[site.file];
    if (text === undefined)
      return fail(`${site.file} is absent, so its pinned version cannot be moved`);
    if (!site.re.test(text)) {
      return fail(
        `${site.file} no longer matches ${site.re}; update SOURCE_CONSTS in scripts/lib/embed-pin-upgrade.ts`
      );
    }
    consts[site.file] = text.replace(
      site.re,
      (_m, pre: string, post: string | undefined) => `${pre}${site.render(latest)}${post ?? ''}`
    );
    changes.push(`${site.file} = ${site.render(latest)}`);
  }

  return {
    ok: true,
    files: { dockerfile, lock: `${JSON.stringify(lockObj, null, 2)}\n`, consts },
    changes,
  };
}

/** snapshotter and snapshot-controller build from ONE clone guarded by ONE commit ARG, so their versions must never differ. Returns a message when they do. */
export function sharedCloneDrift(dockerfile: string): string | null {
  const grab = (name: string): string | undefined =>
    new RegExp(`^ARG\\s+${name}_VERSION=(\\S+)`, 'm').exec(dockerfile)?.[1];
  const a = grab('CSISNAPSHOTTER');
  const b = grab('SNAPSHOTCONTROLLER');
  if (a !== undefined && b !== undefined && a !== b) {
    return `CSISNAPSHOTTER_VERSION=${a} and SNAPSHOTCONTROLLER_VERSION=${b} differ, but both build from the one external-snapshotter clone checked against CSISNAPSHOTTER_COMMIT; bump them together (do not hold only one)`;
  }
  return null;
}

/** The freshness fixture's entry for `base`, or undefined. An OWN-property lookup: a base named like an Object.prototype key (`constructor`, `toString`) must read as absent, never as the inherited function. */
export function fixtureEntry<T>(fixture: Record<string, T>, base: string): T | undefined {
  return Object.hasOwn(fixture, base) ? fixture[base] : undefined;
}
