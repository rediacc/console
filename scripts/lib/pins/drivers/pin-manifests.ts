/**
 * The declared ranges follow a moved syncpack pin (worklist #3fc8b8cb).
 *
 * `npm run pins -- bump npm` moves a `.syncpackrc.json` versionGroup's `pinVersion` when a member
 * package moves (scripts/lib/deps/pin-sync.ts), but `npm update` never rewrites a declared range,
 * so on 2026-10-19 (4ba8aab48) the "Pin i18next for CLI" group went to ^26.5.2 while
 * packages/cli/package.json still declared ^26.4.4, and `check:version` (syncpack lint) went red
 * only in the next ci:quick (`DiffersToPin`). This module plans the second half of that move: every
 * manifest the group covers declares the group's new pin.
 *
 * Pure apart from `sourceManifests`, which globs the rc file's `source` list: the npm driver
 * declares the files a rewrite may touch at plan time (`predictManifests`), and the sync step
 * (npm-steps.ts sync) writes what `planManifestPins` answers inside the pins transaction.
 *
 * A group covers a manifest when its `packages` globs admit the manifest's `name`, and a
 * dependency field when its `dependencyTypes` admit it (prod, dev, optional, peer; a missing list
 * admits all four, as syncpack does). Only literal `dependencies` entries are followed, the same
 * rule pin-sync applies to the pin itself. A declared range that is not a plain `^x.y.z`, `~x.y.z`
 * or `x.y.z` is not rewritten blind: it is an error naming the manifest, so the run stays red
 * instead of leaving syncpack to fail later.
 */
import fs from 'node:fs';
import path from 'node:path';
import { globSync } from 'glob';

const TYPE_FIELDS: Record<string, string> = {
  prod: 'dependencies',
  dev: 'devDependencies',
  optional: 'optionalDependencies',
  peer: 'peerDependencies',
};
const ALL_FIELDS = Object.values(TYPE_FIELDS);
const PLAIN_RANGE = /^[\^~]?\d+\.\d+\.\d+$/;
const CARET_PIN = /^\^\d+\.\d+\.\d+$/;

export interface PinGroup {
  label: string;
  /** The versionGroups index, so a before/after comparison pairs the same group. */
  index: number;
  packages: unknown;
  /** Literal dependency names only; globs and negations are not expanded. */
  deps: string[];
  fields: string[];
  pin: string;
}

export interface ManifestText {
  /** Path relative to the console root, `/`-separated. */
  file: string;
  text: string;
}

function globRe(glob: string): RegExp {
  const body = glob
    .split(/(\*\*|\*|\?)/)
    .map((p) =>
      p === '**'
        ? '.*'
        : p === '*'
          ? '[^/]*'
          : p === '?'
            ? '.'
            : p.replace(/[.+^${}()|[\]\\]/g, '\\$&')
    )
    .join('');
  return new RegExp(`^${body}$`);
}

/** syncpack's `packages` filter: a missing list admits every package, `!x` excludes. */
function admitsPackage(globs: unknown, name: string): boolean {
  if (!Array.isArray(globs)) return true;
  const list = globs.filter((g): g is string => typeof g === 'string');
  const pos = list.filter((g) => !g.startsWith('!'));
  const neg = list.filter((g) => g.startsWith('!')).map((g) => g.slice(1));
  if (neg.some((g) => globRe(g).test(name))) return false;
  return pos.length === 0 || pos.some((g) => globRe(g).test(name));
}

/** The manifest fields a group's `dependencyTypes` admit. */
function fieldsOf(types: unknown): string[] {
  if (!Array.isArray(types)) return ALL_FIELDS;
  const list = types.filter((t): t is string => typeof t === 'string');
  const neg = new Set(list.filter((t) => t.startsWith('!')).map((t) => TYPE_FIELDS[t.slice(1)]));
  const pos = list.filter((t) => !t.startsWith('!')).map((t) => TYPE_FIELDS[t]);
  const base = pos.length > 0 ? pos.filter((f): f is string => f !== undefined) : ALL_FIELDS;
  return base.filter((f) => !neg.has(f));
}

/** Every versionGroup with a caret `pinVersion` and at least one literal dependency. */
export function pinGroups(rcText: string): PinGroup[] {
  const rc = JSON.parse(rcText) as { versionGroups?: Record<string, unknown>[] };
  const out: PinGroup[] = [];
  (rc.versionGroups ?? []).forEach((g, index) => {
    const pin = g.pinVersion;
    if (typeof pin !== 'string' || !CARET_PIN.test(pin) || !Array.isArray(g.dependencies)) return;
    const deps = g.dependencies.filter(
      (d): d is string => typeof d === 'string' && !/[*?!]/.test(d)
    );
    if (deps.length === 0) return;
    out.push({
      label: typeof g.label === 'string' ? g.label : `versionGroups[${index}]`,
      index,
      packages: g.packages,
      deps,
      fields: fieldsOf(g.dependencyTypes),
      pin,
    });
  });
  return out;
}

/** The groups whose `pinVersion` the rewrite from `before` to `after` moved, with their new pin. */
export function movedPinGroups(before: string, after: string): PinGroup[] {
  const old = new Map(pinGroups(before).map((g) => [g.index, g.pin]));
  return pinGroups(after).filter((g) => old.has(g.index) && old.get(g.index) !== g.pin);
}

/** The manifests syncpack lints, from the rc file's `source` globs (syncpack's default when absent), relative to `root`. */
export function sourceManifests(root: string, rcText: string | null): string[] {
  let source: unknown;
  try {
    source = rcText === null ? undefined : (JSON.parse(rcText) as { source?: unknown }).source;
  } catch {
    source = undefined;
  }
  const globs =
    Array.isArray(source) && source.every((s) => typeof s === 'string')
      ? (source as string[])
      : ['package.json', 'packages/*/package.json'];
  const out = new Set<string>();
  for (const g of globs)
    for (const f of globSync(g, { cwd: root, nodir: true, posix: true }))
      if (path.basename(f) === 'package.json') out.add(f);
  return [...out].sort((a, b) => Number(a > b) - Number(a < b));
}

const readManifest = (m: ManifestText): Record<string, unknown> | null => {
  try {
    return JSON.parse(m.text) as Record<string, unknown>;
  } catch {
    return null;
  }
};

/**
 * The manifests a sync of the groups holding a moved package could rewrite: every source
 * manifest a caret group covers that declares one of that group's literal members. A superset of
 * what `planManifestPins` writes, so the step's declared writes never miss a file.
 */
export function predictManifests(
  rcText: string,
  moved: ReadonlySet<string>,
  manifests: ManifestText[]
): string[] {
  const groups = pinGroups(rcText).filter((g) => g.deps.some((d) => moved.has(d)));
  const out: string[] = [];
  for (const m of manifests) {
    const pkg = readManifest(m);
    if (pkg === null) continue;
    const name = typeof pkg.name === 'string' ? pkg.name : '';
    const hit = groups.some(
      (g) =>
        admitsPackage(g.packages, name) &&
        g.fields.some((f) => {
          const table = pkg[f] as Record<string, unknown> | undefined;
          return !!table && g.deps.some((d) => table[d] !== undefined);
        })
    );
    if (hit) out.push(m.file);
  }
  return out;
}

export interface ManifestPinPlan {
  writes: ManifestText[];
  rewrites: string[];
  errors: string[];
}

/**
 * Rewrite every declared range of a moved group's members, in every manifest the group covers, to
 * the group's new pin. A manifest a rewrite would reformat (not two-space JSON with a trailing
 * newline) and a range that is not plain are errors, and nothing is written when any error is
 * found. `skip` is the selftest's `no-manifest-pin` mutant: the behaviour before 2026-10-19, the
 * pin moved and the manifests left behind.
 */
export function planManifestPins(
  groups: PinGroup[],
  manifests: ManifestText[],
  skip = false
): ManifestPinPlan {
  const out: ManifestPinPlan = { writes: [], rewrites: [], errors: [] };
  if (skip || groups.length === 0) return out;
  for (const m of manifests) {
    const pkg = readManifest(m);
    if (pkg === null) {
      out.errors.push(`${m.file}: not valid JSON`);
      continue;
    }
    const name = typeof pkg.name === 'string' ? pkg.name : '';
    let touched = false;
    for (const g of groups) {
      if (!admitsPackage(g.packages, name)) continue;
      for (const f of g.fields) {
        const table = pkg[f] as Record<string, unknown> | undefined;
        if (!table || typeof table !== 'object') continue;
        for (const d of g.deps) {
          const range = table[d];
          if (range === undefined || range === g.pin) continue;
          if (typeof range !== 'string' || !PLAIN_RANGE.test(range)) {
            out.errors.push(
              `${m.file}: ${f}["${d}"] is ${JSON.stringify(range)}, not a plain range, so it is not rewritten to the "${g.label}" pin ${g.pin} blind; set it by hand`
            );
            continue;
          }
          table[d] = g.pin;
          touched = true;
          out.rewrites.push(`${m.file}: ${f}["${d}"] "${range}" -> "${g.pin}" ("${g.label}")`);
        }
      }
    }
    if (!touched) continue;
    if (`${JSON.stringify(JSON.parse(m.text), null, 2)}\n` !== m.text) {
      out.errors.push(
        `${m.file}: not two-space JSON with a trailing newline, so a rewrite would reformat it; set its ranges by hand`
      );
      continue;
    }
    out.writes.push({ file: m.file, text: `${JSON.stringify(pkg, null, 2)}\n` });
  }
  if (out.errors.length > 0) out.writes = [];
  return out;
}

/** The nearest directory at or above `manifest`'s (inside `root`) that holds a package-lock.json, relative to `root`; null when none does. */
export function lockfileOf(root: string, manifest: string): string | null {
  let dir = path.posix.dirname(manifest);
  for (;;) {
    const rel = dir === '.' ? 'package-lock.json' : `${dir}/package-lock.json`;
    if (fs.existsSync(path.join(root, rel))) return rel;
    if (dir === '.') return null;
    dir = path.posix.dirname(dir);
  }
}

/** The package whose version biome.json's `$schema` URL names. */
export const BIOME_PACKAGE = '@biomejs/biome';
export const BIOME_CONFIG = 'biome.json';
const BIOME_SCHEMA_RE = /("\$schema":\s*"https:\/\/biomejs\.dev\/schemas\/)[^/"]+(\/schema\.json")/;

/**
 * biome.json with its `$schema` moved to the version a plan installs, or null when the plan does not move @biomejs/biome (or the file carries no schema URL of that shape, or it already names the version). Biome prints a schema-version mismatch note on every run when the two differ, so the bump and the URL move in one plan.
 */
export function planBiomeSchema(
  text: string,
  steps: ReadonlyArray<{ packages: ReadonlyArray<{ name: string; latest: string }> }>
): string | null {
  const to = steps
    .flatMap((s) => s.packages)
    .filter((p) => p.name === BIOME_PACKAGE)
    .map((p) => p.latest)
    .at(-1);
  if (to === undefined || !BIOME_SCHEMA_RE.test(text)) return null;
  const after = text.replace(BIOME_SCHEMA_RE, `$1${to}$2`);
  return after === text ? null : after;
}
