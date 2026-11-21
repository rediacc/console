/**
 * The app templates' image pins: every exact `image:` reference in
 * packages/json/templates/<category>/<app>/docker-compose.yaml is a `docker` leaf of
 * .ci/config/pins.json, generated here, never written by hand.
 *
 * WHY. The registry listed every Dockerfile FROM image and no compose image at all, so the
 * search template sat on elasticsearch:8.11.0 and kibana:8.11.0 (a 2023 image) with every
 * freshness gate green: no gate knew the pin existed. A template leaf puts each pin where
 * check:ci-pin-freshness judges it (the docker driver lists the image's newer series on
 * Docker Hub, the release-age window and the major grace apply), and check:ci-pin-registry's
 * `compose-image` scanner refuses a template pin no leaf claims, while each leaf's `expect`
 * count refuses a leaf whose line is gone.
 *
 * WHAT COUNTS AS A PIN. A literal reference (no `${...}`) whose tag starts with a version
 * number (`8.11.0`, `3.11`, `16-alpine`, `v2.1.4`, `2022-CU21-ubuntu-22.04`) or that carries
 * a `@sha256:` digest. A major-only tag such as `16-alpine` is a pin by the registry's own
 * convention (image:ci-node pins `node:26-bookworm-slim`, and the docker driver compares
 * series of that shape). `latest`, a word tag (`alpine`, `bookworm`) and an untagged
 * reference name no version, so they are reported as UNPINNED by `npm run pins --
 * sync-templates` and check:ci-pin-freshness, and are never leaves: no driver could compare
 * them with anything.
 *
 * THE SOURCE. A Docker Hub image reads `dockerhub`. An image of another registry (ghcr.io,
 * mcr.microsoft.com) gets `source: none` with a BLOCKER reason: the OCI tag list those serve
 * carries no publish date, so the release-age window cannot be applied to it. check:ci-pin-
 * freshness names every such leaf on every run, so it is visible, never counted as current.
 *
 * THE TREES. `TREES` below is the one list of scan roots: the app templates (`template:`),
 * packages/cli/templates (`cli-template:`), .ci/tutorials/apps (`tutorial:`), compose/
 * (`compose:`) and renet's proxy compose file (`renet:`, a site in the private/renet repo).
 * Every tree gets the same leaves, the same drift gate both ways and the same freshness
 * verdict; a new tree is one entry there.
 *
 * THE ID is `<prefix><app>.<image basename>` (`template:elasticsearch.kibana`), with the
 * service name appended when one file uses one image at two different tags (one reference
 * on two lines is one leaf whose sites expect both). The hold key (the id after its colon)
 * never collides with an `image:*` leaf's, and two trees never share one: a later tree's
 * app then carries its tree name (`tutorial:tutorial-heartbeat.node`, as the app template
 * `template:heartbeat.node` owns the bare key).
 *
 * Usage:
 *   npx tsx scripts/lib/pins/templates.ts --selftest
 *   npm run pins -- sync-templates [--write]     (scripts/pins/pins.ts)
 */
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { type ControlCase, runControls } from '../controls.js';
import { hubRepo } from '../docker-hub.js';
import { isEntryPoint } from '../entry-point.js';
import { policyPath } from '../policy-paths.js';
import type { PinEntry, PinRegistry, PinSite } from './registry.js';

/** The workspace root segment, spelled through a constant so a fixture path is not read as a real path literal. */
const PKG_DIR = 'packages';

/** The template tree, console-relative. */
export const TEMPLATE_ROOT = 'packages/json/templates';
/** The hold file every docker leaf names first. */
const HOLD_FILE = policyPath('.pins-upgrade-blocklist', '.');

/** A compose file by name, the shape check-docker-image-freshness reads too. */
export const isComposeFile = (file: string): boolean =>
  /(^|\/)(docker-)?compose[^/]*\.ya?ml$/.test(file);

/**
 * One tree of compose files whose exact image pins are generated into `<prefix>` leaves.
 * THE LIST OF TREES, `TREES` below, is the one place a scan root is declared: adding a tree
 * there brings its pins under the generator, the drift gate and the freshness gate.
 */
export interface PinTree {
  /** The id prefix of every leaf of the tree, and of no other tree (`template:`). */
  prefix: string;
  /** The repo the tree lives in: `.` for the console, a submodule path otherwise. */
  repo: string;
  /** The tree's directory, console-relative. */
  root: string;
  /** Whether a console-relative path is a compose file of this tree. */
  test(file: string): boolean;
  /** The app name the leaf ids carry. */
  app(file: string): string;
  /** What the leaf's `name` calls the carrier. */
  label(file: string): string;
}

/** The path under the tree root, split on `/`. */
const under = (t: Pick<PinTree, 'root'>, file: string): string[] =>
  file.slice(t.root.length + 1).split('/');
const inRoot = (t: Pick<PinTree, 'root'>, file: string): boolean =>
  file.startsWith(`${t.root}/`) && isComposeFile(file);

/** Every tree, in id order of precedence: the first tree to own a hold key keeps it bare. */
export const TREES: readonly PinTree[] = [
  {
    prefix: 'template:',
    repo: '.',
    root: TEMPLATE_ROOT,
    test(file) {
      return new RegExp(`^${TEMPLATE_ROOT}/[^/]+/[^/]+/docker-compose\\.yaml$`).test(file);
    },
    app: (file) => under({ root: TEMPLATE_ROOT }, file)[1],
    label: (file) => `${under({ root: TEMPLATE_ROOT }, file).slice(0, 2).join('/')} app template`,
  },
  {
    prefix: 'cli-template:',
    repo: '.',
    root: 'packages/cli/templates',
    test(file) {
      return inRoot(this, file);
    },
    app(file) {
      return under(this, file).slice(0, -1).join('-');
    },
    label(file) {
      return `${this.app(file)} CLI template`;
    },
  },
  {
    prefix: 'tutorial:',
    repo: '.',
    root: '.ci/tutorials/apps',
    test(file) {
      return inRoot(this, file) && under(this, file).length === 2;
    },
    app(file) {
      return under(this, file)[0];
    },
    label(file) {
      return `${this.app(file)} tutorial app`;
    },
  },
  {
    prefix: 'compose:',
    repo: '.',
    root: 'compose',
    test(file) {
      return inRoot(this, file);
    },
    app(file) {
      return under(this, file).slice(0, -1).join('-');
    },
    label(file) {
      return `${this.app(file)} compose file`;
    },
  },
  {
    prefix: 'renet:',
    repo: 'private/renet',
    root: 'private/renet/proxy',
    test(file) {
      return file === 'private/renet/proxy/docker-compose.yml';
    },
    app: () => 'proxy',
    label: () => 'renet proxy compose file',
  },
];

/** The tree a console-relative path belongs to, or null. Pure. */
export const treeOf = (file: string): PinTree | null => TREES.find((t) => t.test(file)) ?? null;

/** A compose file of any generated tree. */
export const isTemplateCompose = (file: string): boolean => treeOf(file) !== null;

/** Whether a registry id is a generated tree leaf. Pure. */
export const isTreeId = (id: string): boolean => TREES.some((t) => id.startsWith(t.prefix));

/** A site's console-relative file, from the repo it is in. Pure. */
export const consolePath = (repo: string, file: string): string =>
  repo === '.' ? file : `${repo}/${file}`;

/** One literal `image:` reference in a compose file. */
export interface ComposeImage {
  file: string;
  line: number;
  /** The raw line. */
  text: string;
  /** The compose service the reference sits under, or null when none precedes it. */
  service: string | null;
  /** The whole reference as written (`elasticsearch:8.11.0`). */
  ref: string;
  image: string;
  tag: string | null;
  digest: string | null;
}

const IMAGE_LINE = /^([ \t]*)image:[ \t]*(["']?)([^\s"'#]+)\2[ \t]*(?:#.*)?$/;
const SERVICE_LINE = /^([ \t]*)([A-Za-z0-9._-]+):[ \t]*$/;

/** `<image>[:<tag>][@sha256:<hex>]`, the tag read only after the last `/` (a registry port is not a tag). Pure. */
export function splitRef(ref: string): {
  image: string;
  tag: string | null;
  digest: string | null;
} {
  const at = ref.indexOf('@');
  const digest = at >= 0 ? ref.slice(at + 1) : null;
  const named = at >= 0 ? ref.slice(0, at) : ref;
  const colon = named.lastIndexOf(':');
  const tagged = colon > named.lastIndexOf('/');
  return {
    image: tagged ? named.slice(0, colon) : named,
    tag: tagged ? named.slice(colon + 1) : null,
    digest,
  };
}

/** Every literal `image:` reference of a compose file, comments and `${...}` references excepted. Pure. */
export function composeImages(text: string, file: string): ComposeImage[] {
  const lines = text.split('\n');
  const out: ComposeImage[] = [];
  lines.forEach((raw, i) => {
    const m = IMAGE_LINE.exec(raw);
    if (!m || m[3].includes('$')) return;
    const indent = m[1].length;
    let service: string | null = null;
    for (let j = i - 1; j >= 0; j--) {
      const s = SERVICE_LINE.exec(lines[j]);
      if (s && s[1].length < indent) {
        service = s[2];
        break;
      }
    }
    out.push({ file, line: i + 1, text: raw, service, ref: m[3], ...splitRef(m[3]) });
  });
  return out;
}

/** Whether a reference names an exact version: a digest, or a tag that starts with a version number. Pure. */
export function isPinned(img: Pick<ComposeImage, 'tag' | 'digest'>): boolean {
  if (img.digest !== null && /^sha256:[0-9a-f]{64}$/.test(img.digest)) return true;
  return img.tag !== null && /^v?\d/.test(img.tag);
}

/** Why a reference is not a pin, for the UNPINNED report. Pure. */
export function unpinnedWhy(img: Pick<ComposeImage, 'tag'>): string {
  if (img.tag === null) return 'untagged, so it pulls whatever `latest` is';
  if (img.tag === 'latest') return '`latest` names no version';
  return `the tag \`${img.tag}\` names no version`;
}

const esc = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const slug = (s: string): string =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9.+-]+/g, '-')
    .replace(/^-+|-+$/g, '');

/** A console-relative path as the repo-relative file a site names. Pure. */
const repoFile = (tree: Pick<PinTree, 'repo'>, file: string): string =>
  tree.repo === '.' ? file : file.slice(tree.repo.length + 1);

/** The non-Docker-Hub registry host of an image, for its BLOCKER reason. Pure. */
function hostOf(image: string): string {
  return image.split('/')[0];
}

/** The generated leaf of one pinned template reference; `id` is decided by the caller (collisions). Pure. */
export function templateEntry(img: ComposeImage, id: string, copies = 1): PinEntry {
  const tree = treeOf(img.file) as PinTree;
  const sites: PinSite[] = [];
  const lead = `^[ \\t]*image:[ \\t]*["']?`;
  if (img.tag !== null)
    sites.push({
      repo: tree.repo,
      file: repoFile(tree, img.file),
      role: 'version',
      // The tag must start with a version, as isPinned requires: a line edited to `:latest` leaves the site matching nothing, which check:ci-pin-registry reports.
      match: `${lead}(?<value>${esc(img.image)}:v?\\d[^\\s"'@#]*)`,
      expect: copies,
    });
  if (img.digest !== null)
    sites.push({
      repo: tree.repo,
      file: repoFile(tree, img.file),
      role: 'digest',
      match: `${lead}${esc(img.image)}(?::[^\\s"'@#]+)?@(?<value>sha256:[0-9a-f]{64})`,
      expect: copies,
    });
  const hub = hubRepo(img.image) !== null;
  const source: PinEntry['source'] =
    img.tag === null
      ? {
          type: 'none',
          reason: `BLOCKER: the reference pins a digest with no tag, so it names no version a newer release could be compared with; a tag beside the digest (${img.image}:<tag>@sha256:...) is the change that lets the docker driver judge it`,
        }
      : hub
        ? { type: 'dockerhub', image: img.image }
        : {
            type: 'none',
            reason: `BLOCKER: ${hostOf(img.image)} serves this image, and the OCI tag list it answers carries no publish date, so the release-age window cannot be applied and no pins source type reads it (dockerhub and quay-tags cover the registries the other images use); a dated source for ${hostOf(img.image)} is the change that would judge it`,
          };
  return {
    id,
    kind: 'leaf',
    name: `${img.image} in the ${tree.label(img.file)}`,
    driver: 'docker',
    source,
    safety: { mode: 'assisted', major: 'assisted' },
    holds: [HOLD_FILE],
    gates: ['check:ci-pin-registry', 'check:ci-pin-freshness'],
    sites,
    derive: [],
    literals: [],
  };
}

/** What a template scan finds: the leaves it implies and the references that are not pins. */
export interface TemplateScan {
  entries: PinEntry[];
  unpinned: Array<{ img: ComposeImage; why: string }>;
}

/**
 * The leaves the given template compose files imply, in file and line order, and the
 * unpinned references. `files` maps a console-relative path to its text; a path that is not
 * a template compose file is ignored. Throws on two leaves with one id. Pure.
 */
export function scanTemplates(files: Map<string, string>): TemplateScan {
  const pinned: ComposeImage[] = [];
  const unpinned: TemplateScan['unpinned'] = [];
  const treeIndex = (f: string): number => TREES.indexOf(treeOf(f) as PinTree);
  const ordered = [...files.keys()]
    .filter(isTemplateCompose)
    .sort((a, b) => treeIndex(a) - treeIndex(b) || Number(a > b) - Number(a < b));
  for (const file of ordered) {
    for (const img of composeImages(files.get(file) as string, file)) {
      if (isPinned(img)) pinned.push(img);
      else unpinned.push({ img, why: unpinnedWhy(img) });
    }
  }
  // One file may write the same reference on several lines (two services of one image): one leaf, its sites counting every line, since one regex cannot tell identical lines apart.
  const copiesOf = new Map<string, number>();
  for (const img of pinned) {
    const key = `${img.file}\0${img.ref}`;
    copiesOf.set(key, (copiesOf.get(key) ?? 0) + 1);
  }
  const firstOf = new Set<string>();
  const distinct = pinned.filter((img) => {
    const key = `${img.file}\0${img.ref}`;
    if (firstOf.has(key)) return false;
    firstOf.add(key);
    return true;
  });
  // The hold key is the id after its colon, so two trees may not share one: the first tree keeps the bare name and a later tree's app carries its tree name (`tutorial-heartbeat.node`), or a hold for one pin would silently hold the other.
  const keyOwner = new Map<string, PinTree>();
  const baseId = (img: ComposeImage): string => {
    const tree = treeOf(img.file) as PinTree;
    const local = `${slug(tree.app(img.file))}.${slug(img.image.split('/').pop() as string)}`;
    const owner = keyOwner.get(local);
    if (owner === undefined) keyOwner.set(local, tree);
    const key =
      owner === undefined || owner === tree
        ? local
        : `${slug(tree.prefix.replace(/:$/, ''))}-${local}`;
    return `${tree.prefix}${key}`;
  };
  const baseIds = new Map<ComposeImage, string>(distinct.map((img) => [img, baseId(img)]));
  const count = new Map<string, number>();
  for (const id of baseIds.values()) count.set(id, (count.get(id) ?? 0) + 1);
  const entries: PinEntry[] = [];
  const seen = new Set<string>();
  for (const img of distinct) {
    let id = baseIds.get(img) as string;
    if ((count.get(id) ?? 0) > 1) id = `${id}-${slug(img.service ?? `line${img.line}`)}`;
    if (seen.has(id))
      throw new Error(
        `${img.file}:${img.line}: two template pins resolve to the id ${id}; give the services distinct names`
      );
    seen.add(id);
    entries.push(templateEntry(img, id, copiesOf.get(`${img.file}\0${img.ref}`)));
  }
  return { entries, unpinned };
}

/** How the registry's template leaves differ from the generated ones. */
export interface TemplateDrift {
  added: string[];
  removed: string[];
  changed: string[];
}

/** The ids the generated set adds, the registry ids it drops and the ids whose entry differs. Pure. */
export function templateDrift(reg: PinRegistry, want: PinEntry[]): TemplateDrift {
  const have = new Map(reg.entries.filter((e) => isTreeId(e.id)).map((e) => [e.id, e]));
  const wanted = new Map(want.map((e) => [e.id, e]));
  return {
    added: [...wanted.keys()].filter((id) => !have.has(id)),
    removed: [...have.keys()].filter((id) => !wanted.has(id)),
    changed: [...wanted.keys()].filter(
      (id) => have.has(id) && JSON.stringify(have.get(id)) !== JSON.stringify(wanted.get(id))
    ),
  };
}

/**
 * The registry with its template leaves replaced by `want`: the generated block takes the
 * place of the first existing template leaf, or follows the last entry when there is none.
 * Every other entry keeps its position and its bytes. Pure.
 */
export function withTemplates(reg: PinRegistry, want: PinEntry[]): PinRegistry {
  const first = reg.entries.findIndex((e) => isTreeId(e.id));
  const rest = reg.entries.filter((e) => !isTreeId(e.id));
  const at = first < 0 ? rest.length : first;
  return { ...reg, entries: [...rest.slice(0, at), ...want, ...rest.slice(at)] };
}

/**
 * The registry TEXT with its `entries` array rebuilt for `next`: an entry `prev` already held
 * keeps its bytes exactly (pins.json is hand-formatted in places, and biome does not format
 * it), and a new or changed entry is written as `JSON.stringify(entry, null, 2)` at the
 * array's indent. Throws when the text's entry objects cannot be located one for one with
 * `prev.entries`, so a layout this does not understand is refused, never rewritten blind. Pure.
 */
export function spliceEntries(text: string, prev: PinRegistry, next: PinRegistry): string {
  const lines = text.split('\n');
  const open = lines.indexOf('  "entries": [');
  if (open < 0) throw new Error('no `  "entries": [` line');
  const spans: Array<{ id: string; body: string[] }> = [];
  let close = -1;
  for (let i = open + 1; i < lines.length; i++) {
    if (/^ {2}\],?$/.test(lines[i])) {
      close = i;
      break;
    }
    if (lines[i] !== '    {') throw new Error(`line ${i + 1}: expected an entry to open`);
    let end = i;
    while (end < lines.length && !/^ {4}\},?$/.test(lines[end])) end++;
    const body = lines.slice(i, end + 1);
    body[body.length - 1] = '    }';
    const id = /^ {6}"id": "([^"]+)",?$/.exec(body[1] ?? '')?.[1];
    if (id === undefined) throw new Error(`line ${i + 2}: an entry whose first key is not "id"`);
    spans.push({ id, body });
    i = end;
  }
  if (close < 0) throw new Error('the entries array never closes');
  if (spans.map((s) => s.id).join('\n') !== prev.entries.map((e) => e.id).join('\n'))
    throw new Error('the entry objects in the text do not match the parsed registry one for one');
  const kept = new Map(
    spans.map((s, i) => [s.id, { body: s.body, json: JSON.stringify(prev.entries[i]) }])
  );
  const bodies = next.entries.map((e) => {
    const old = kept.get(e.id);
    if (old && old.json === JSON.stringify(e)) return old.body.join('\n');
    return JSON.stringify(e, null, 2)
      .split('\n')
      .map((l) => `    ${l}`)
      .join('\n');
  });
  return [...lines.slice(0, open + 1), bodies.join(',\n'), ...lines.slice(close)].join('\n');
}

/**
 * The fewest compose files a scan of a tree that is not the real one may find: the distinct
 * files the registry's template leaves cite, capped at MIN_TEMPLATE_COMPOSE_FILES and never
 * below 1. A fixture tree may be small, but one that holds fewer files than its own registry
 * cites (or none) is a moved or emptied root, and `sync-templates --write` must refuse it
 * rather than splice the missing leaves out. Pure.
 */
export function fixtureFloor(reg: PinRegistry): number {
  const cited = new Set<string>();
  for (const e of reg.entries)
    if (isTreeId(e.id)) for (const s of e.sites) cited.add(`${s.repo}/${s.file}`);
  return Math.min(MIN_TEMPLATE_COMPOSE_FILES, Math.max(1, cited.size));
}

/** Every compose file of every tree under `root`, read from disk; `floor` is the fewest files a scan may find (the real tree takes the default, a fixture tree `fixtureFloor`). A submodule tree that is not on disk throws: a scan that skipped it would report its leaves as removed. */
export function readTemplateFiles(
  root: string,
  floor: number = MIN_TEMPLATE_COMPOSE_FILES
): Map<string, string> {
  const out = new Map<string, string>();
  for (const tree of TREES) {
    const base = path.join(root, tree.root);
    if (!fs.existsSync(base)) {
      if (tree.repo !== '.')
        throw new Error(
          `${tree.root} is not on disk, so the ${tree.prefix}* leaves cannot be generated or checked (is ${tree.repo} checked out?)`
        );
      continue;
    }
    for (const ent of fs.readdirSync(base, { withFileTypes: true, recursive: true })) {
      if (!ent.isFile()) continue;
      const rel = path
        .relative(root, path.join(ent.parentPath, ent.name))
        .split(path.sep)
        .join('/');
      if (rel.includes('/node_modules/') || !tree.test(rel)) continue;
      out.set(rel, fs.readFileSync(path.join(root, rel), 'utf8'));
    }
  }
  // A scan that reads a handful of files reads as a clean registry; the floor makes a moved or
  // emptied scan root a refusal (38 template compose files on 2026-11-21). A fixture tree gets
  // `fixtureFloor` instead of the real tree's 30, and is refused below that too.
  if (out.size < floor)
    throw new Error(
      `only ${out.size} template compose file(s) found under ${TREES.map((t) => t.root).join(', ')} (floor ${floor}): a scan root moved or is empty`
    );
  return out;
}

export const MIN_TEMPLATE_COMPOSE_FILES = 30;

// ---- controls --------------------------------------------------------------------------------

export function selftestCases(): ControlCase[] {
  const cases: ControlCase[] = [];
  const F = `${TEMPLATE_ROOT}/search/elasticsearch/docker-compose.yaml`;
  const es = [
    'services:',
    '  elasticsearch:',
    '    image: elasticsearch:8.11.0',
    '  kibana:',
    '    image: "kibana:8.11.0"  # the UI',
    '  web:',
    '    image: nginx:latest',
    '  tool:',
    '    image: phpmyadmin',
    '  own:',
    '    image: ${REGISTRY}/x:${TAG}',
    '  db:',
    '    image: postgres:16-alpine',
    '  mirror:',
    `    image: ghcr.io/acme/app:v2.1.4@sha256:${'a'.repeat(64)}`,
    '#    image: redis:7.0.0',
  ].join('\n');
  const imgs = composeImages(es, F);
  cases.push({
    name: 'composeImages reads each literal image line with its service, quotes and trailing comment dropped, and skips ${...} and comment lines',
    ok:
      JSON.stringify(imgs.map((i) => [i.line, i.service, i.image, i.tag])) ===
      JSON.stringify([
        [3, 'elasticsearch', 'elasticsearch', '8.11.0'],
        [5, 'kibana', 'kibana', '8.11.0'],
        [7, 'web', 'nginx', 'latest'],
        [9, 'tool', 'phpmyadmin', null],
        [13, 'db', 'postgres', '16-alpine'],
        [15, 'mirror', 'ghcr.io/acme/app', 'v2.1.4'],
      ]),
    detail: JSON.stringify(imgs.map((i) => [i.line, i.service, i.image, i.tag])),
  });
  cases.push({
    name: 'splitRef reads a registry port as part of the image, not as a tag',
    ok:
      JSON.stringify(splitRef('localhost:5000/app')) ===
        JSON.stringify({ image: 'localhost:5000/app', tag: null, digest: null }) &&
      splitRef('localhost:5000/app:1.2').tag === '1.2',
  });
  cases.push({
    name: 'CONTROL: a version tag, a major-only series tag, a v-prefixed tag and a digest are pins',
    ok:
      isPinned({ tag: '8.11.0', digest: null }) &&
      isPinned({ tag: '16-alpine', digest: null }) &&
      isPinned({ tag: 'v2.1.4', digest: null }) &&
      isPinned({ tag: null, digest: `sha256:${'b'.repeat(64)}` }),
  });
  cases.push({
    name: 'CONTROL: latest, a word tag and an untagged reference are not pins',
    ok:
      !isPinned({ tag: 'latest', digest: null }) &&
      !isPinned({ tag: 'alpine', digest: null }) &&
      !isPinned({ tag: null, digest: null }),
  });
  const scan = scanTemplates(new Map([[F, es]]));
  cases.push({
    name: 'scanTemplates makes one leaf per pin and reports latest and untagged as unpinned',
    ok:
      scan.entries.map((e) => e.id).join() ===
        'template:elasticsearch.elasticsearch,template:elasticsearch.kibana,template:elasticsearch.postgres,template:elasticsearch.app' &&
      scan.unpinned.map((u) => u.img.ref).join() === 'nginx:latest,phpmyadmin',
    detail: `${scan.entries.map((e) => e.id).join()} | ${scan.unpinned.map((u) => u.img.ref).join()}`,
  });
  const esLeaf = scan.entries[0];
  const site = esLeaf.sites[0];
  const re = new RegExp(site.match as string, 'gm');
  const hits = [...es.matchAll(re)].map((m) => m.groups?.value);
  cases.push({
    name: 'a generated version site matches its own line exactly once, with the image:tag value the docker driver reads',
    ok:
      hits.length === 1 &&
      hits[0] === 'elasticsearch:8.11.0' &&
      esLeaf.source.type === 'dockerhub' &&
      esLeaf.source.image === 'elasticsearch' &&
      esLeaf.driver === 'docker',
    detail: JSON.stringify(hits),
  });
  const kib = new RegExp(scan.entries[1].sites[0].match as string, 'gm');
  cases.push({
    name: 'a quoted reference is matched inside its quotes',
    ok: [...es.matchAll(kib)].map((m) => m.groups?.value).join() === 'kibana:8.11.0',
  });
  cases.push({
    name: 'CONTROL: a site anchored with [ \\t]* never starts on the blank line above, so its line is the image line',
    ok: !(site.match as string).startsWith('^\\s'),
  });
  const ghcr = scan.entries[3];
  cases.push({
    name: 'another registry is source none with a BLOCKER, and a tag-plus-digest line has a version and a digest site',
    ok:
      ghcr.source.type === 'none' &&
      (ghcr.source.reason ?? '').startsWith('BLOCKER: ghcr.io serves') &&
      ghcr.sites.map((s) => s.role).join() === 'version,digest' &&
      [...es.matchAll(new RegExp(ghcr.sites[1].match as string, 'gm'))][0]?.groups?.value ===
        `sha256:${'a'.repeat(64)}`,
  });
  const twice = scanTemplates(
    new Map([
      [
        `${TEMPLATE_ROOT}/a/app/docker-compose.yaml`,
        'services:\n  one:\n    image: postgres:16\n  two:\n    image: postgres:17\n',
      ],
    ])
  );
  cases.push({
    name: 'one template using one image twice gets the service in each id',
    ok:
      twice.entries.map((e) => e.id).join() ===
      'template:app.postgres-one,template:app.postgres-two',
  });
  cases.push({
    name: 'CONTROL: a compose file outside every tree is not scanned, and a nested file of the template tree is not a template',
    ok:
      scanTemplates(new Map([[`${PKG_DIR}/e2e-tests/fixtures/x/docker-compose.yml`, es]])).entries
        .length === 0 &&
      !isTemplateCompose(`${PKG_DIR}/json/templates/a/b/c/docker-compose.yaml`) &&
      !isTemplateCompose('.ci/tutorials/apps/a/b/docker-compose.yml'),
  });
  const planted = new Map([
    [
      `${PKG_DIR}/cli/templates/app-x/docker-compose.yml`,
      'services:\n  api:\n    image: node:20.20.2-alpine\n',
    ],
    [
      `${PKG_DIR}/cli/templates/multi/project-a/docker-compose.yml`,
      'services:\n  db:\n    image: postgres:16.14-alpine\n',
    ],
    [
      '.ci/tutorials/apps/heart/docker-compose.yaml',
      'services:\n  db:\n    image: postgres:16.14-alpine\n',
    ],
    [
      `${TEMPLATE_ROOT}/web/heart/docker-compose.yaml`,
      'services:\n  db:\n    image: postgres:16-alpine\n',
    ],
    [
      `${TEMPLATE_ROOT}/web/heart2/docker-compose.yaml`,
      'services:\n  db:\n    image: postgres:16-alpine\n',
    ],
    [
      'compose/otel-collector/docker-compose.yml',
      'services:\n  o:\n    image: otel/opentelemetry-collector-contrib:0.111.0\n',
    ],
    ['private/renet/proxy/docker-compose.yml', 'services:\n  p:\n    image: traefik:v3.7.16\n'],
    [
      'packages/cli/templates/elite/docker-compose.yml',
      `services:\n  a:\n    image: rustfs/rustfs@sha256:${'c'.repeat(64)}\n  b:\n    image: rustfs/rustfs@sha256:${'c'.repeat(64)}\n`,
    ],
  ]);
  const multi = scanTemplates(planted);
  cases.push({
    name: 'every tree yields leaves prefixed by its tree, one reference on two lines is one leaf counting both, and a hold key shared by two trees is made distinct',
    ok:
      multi.entries.map((e) => e.id).join() ===
      [
        'template:heart.postgres',
        'template:heart2.postgres',
        'cli-template:app-x.node',
        'cli-template:elite.rustfs',
        'cli-template:multi-project-a.postgres',
        'tutorial:tutorial-heart.postgres',
        'compose:otel-collector.opentelemetry-collector-contrib',
        'renet:proxy.traefik',
      ].join(),
    detail: multi.entries.map((e) => e.id).join(),
  });
  cases.push({
    name: 'the leaf of a reference written on two lines expects both, and a second tag of the same image in one file gets its service',
    ok:
      multi.entries.find((e) => e.id === 'cli-template:elite.rustfs')?.sites[0].expect === 2 &&
      scanTemplates(
        new Map([
          [
            `${PKG_DIR}/cli/templates/t/docker-compose.yml`,
            'services:\n  a:\n    image: redis:7.4.9\n  b:\n    image: redis:8.0.1\n',
          ],
        ])
      )
        .entries.map((e) => e.id)
        .join() === 'cli-template:t.redis-a,cli-template:t.redis-b',
  });
  const holdKeys = multi.entries.map((e) => e.id.slice(e.id.indexOf(':') + 1));
  cases.push({
    name: 'CONTROL: no two generated leaves share a hold key',
    ok: new Set(holdKeys).size === holdKeys.length,
    detail: holdKeys.join(),
  });
  const proxy = multi.entries.find((e) => e.id === 'renet:proxy.traefik') as PinEntry;
  cases.push({
    name: 'a submodule tree writes the submodule as the site repo and the repo-relative file',
    ok:
      proxy.sites[0].repo === 'private/renet' &&
      proxy.sites[0].file === 'proxy/docker-compose.yml' &&
      proxy.name === 'traefik in the renet proxy compose file',
    detail: JSON.stringify(proxy.sites),
  });
  cases.push({
    name: 'a planted pin in a CLI template the registry lacks is drift (added), and a leaf with no carrier is drift (removed)',
    ok: (() => {
      const base = scanTemplates(new Map([...planted]));
      const without = new Map([...planted]);
      without.delete(`${PKG_DIR}/cli/templates/app-x/docker-compose.yml`);
      const reg2 = withTemplates(
        {
          version: 1,
          submodules: { scanned: [], unscanned: [] },
          literalExclude: [],
          ignores: [],
          entries: [],
        } as PinRegistry,
        scanTemplates(without).entries
      );
      const d = templateDrift(reg2, base.entries);
      const gone = new Map([...planted]);
      gone.delete('compose/otel-collector/docker-compose.yml');
      const d2 = templateDrift(reg2, scanTemplates(gone).entries);
      return (
        d.added.join() === 'cli-template:app-x.node' &&
        d.removed.length === 0 &&
        d2.removed.join() === 'compose:otel-collector.opentelemetry-collector-contrib'
      );
    })(),
  });
  cases.push({
    name: 'CONTROL: the shipped tree list holds each prefix once and each prefix ends with a colon',
    ok:
      new Set(TREES.map((t) => t.prefix)).size === TREES.length &&
      TREES.every((t) => t.prefix.endsWith(':')),
  });
  const reg = {
    version: 1,
    submodules: { scanned: [], unscanned: [] },
    literalExclude: [],
    ignores: [],
    entries: [
      { ...esLeaf, id: 'image:x' },
      { ...esLeaf, id: 'template:gone.x' },
      { ...scan.entries[1], name: 'edited by hand' },
      { ...esLeaf, id: 'image:y' },
    ],
  } as PinRegistry;
  const drift = templateDrift(reg, scan.entries);
  cases.push({
    name: 'templateDrift names the added, the removed and the hand-edited leaf',
    ok:
      drift.added.join() ===
        'template:elasticsearch.elasticsearch,template:elasticsearch.postgres,template:elasticsearch.app' &&
      drift.removed.join() === 'template:gone.x' &&
      drift.changed.join() === 'template:elasticsearch.kibana',
    detail: JSON.stringify(drift),
  });
  cases.push({
    name: 'CONTROL: a registry that already holds the generated set has no drift',
    ok: (() => {
      const d = templateDrift(withTemplates(reg, scan.entries), scan.entries);
      return d.added.length + d.removed.length + d.changed.length === 0;
    })(),
  });
  const merged = withTemplates(reg, scan.entries).entries.map((e) => e.id);
  cases.push({
    name: 'withTemplates puts the generated block where the first template leaf stood and keeps every other entry in place',
    ok: merged.join() === ['image:x', ...scan.entries.map((e) => e.id), 'image:y'].join(),
    detail: merged.join(),
  });
  // The splice keeps a hand-formatted entry's bytes and writes the generated ones.
  const small = {
    ...reg,
    entries: [{ ...esLeaf, id: 'image:x', gates: ['check:ci-pin-registry'] }],
  } as PinRegistry;
  const handText = JSON.stringify(small, null, 2).replace(
    /"gates": \[\n\s+"check:ci-pin-registry"\n\s+\]/,
    '"gates": ["check:ci-pin-registry"]'
  );
  const spliced = spliceEntries(handText, small, withTemplates(small, scan.entries));
  cases.push({
    name: 'spliceEntries keeps a hand-formatted entry byte for byte and the result parses to the generated registry',
    ok:
      spliced.includes('"gates": ["check:ci-pin-registry"]') &&
      JSON.stringify(JSON.parse(spliced)) === JSON.stringify(withTemplates(small, scan.entries)),
  });
  cases.push({
    name: 'a scan whose roots exist but hold fewer template compose files than the floor is refused',
    ok: (() => {
      const empty = fs.mkdtempSync(path.join(fs.realpathSync('/tmp'), 'tpl-floor-'));
      try {
        for (const tree of TREES) fs.mkdirSync(path.join(empty, tree.root), { recursive: true });
        readTemplateFiles(empty);
        return false;
      } catch (e) {
        return String(e).includes(`floor ${MIN_TEMPLATE_COMPOSE_FILES}`);
      } finally {
        fs.rmSync(empty, { recursive: true, force: true });
      }
    })(),
  });
  cases.push({
    name: 'fixtureFloor: a bare registry floors at 1, a registry citing files floors at their count, capped at the real-tree floor',
    ok: (() => {
      const leaf = (id: string, file: string): PinEntry =>
        ({
          ...small.entries[0],
          id,
          sites: [{ repo: '.', file, role: 'r', expect: 1 }],
        }) as PinEntry;
      const two = withTemplates(small, [
        leaf('template:a.x', 'a/docker-compose.yaml'),
        leaf('template:a.y', 'a/docker-compose.yaml'),
        leaf('template:b.x', 'b/docker-compose.yaml'),
      ]);
      const many = withTemplates(
        small,
        Array.from({ length: MIN_TEMPLATE_COMPOSE_FILES + 5 }, (_, i) =>
          leaf(`template:n${i}.x`, `n${i}/docker-compose.yaml`)
        )
      );
      return (
        fixtureFloor(withTemplates(small, [])) === 1 &&
        fixtureFloor(two) === 2 &&
        fixtureFloor(many) === MIN_TEMPLATE_COMPOSE_FILES
      );
    })(),
  });
  cases.push({
    name: 'a fixture tree holding fewer compose files than its registry cites is refused at fixtureFloor, and one holding exactly that many is read',
    ok: (() => {
      const dir = fs.mkdtempSync(path.join(fs.realpathSync('/tmp'), 'tpl-fixfloor-'));
      try {
        for (const tree of TREES) fs.mkdirSync(path.join(dir, tree.root), { recursive: true });
        const f = (n: string) => path.join(dir, TEMPLATE_ROOT, 'cat', n, 'docker-compose.yaml');
        for (const n of ['a', 'b']) {
          fs.mkdirSync(path.dirname(f(n)), { recursive: true });
          fs.writeFileSync(f(n), 'services:\n  s:\n    image: redis:7.4.9\n');
        }
        const cites = (files: string[]): PinRegistry =>
          withTemplates(
            small,
            files.map(
              (file, i) =>
                ({
                  ...small.entries[0],
                  id: `template:c${i}.x`,
                  sites: [{ repo: '.', file, role: 'r', expect: 1 }],
                }) as PinEntry
            )
          );
        const three = cites(['p/1.yaml', 'p/2.yaml', 'p/3.yaml']);
        const silent =
          readTemplateFiles(dir, fixtureFloor(cites(['p/1.yaml', 'p/2.yaml']))).size === 2;
        let refused = false;
        try {
          readTemplateFiles(dir, fixtureFloor(three));
        } catch (e) {
          refused = String(e).includes('floor 3');
        }
        return silent && refused;
      } finally {
        fs.rmSync(dir, { recursive: true, force: true });
      }
    })(),
  });
  cases.push({
    name: 'CONTROL: a text whose entries do not line up with the parsed registry is refused',
    ok: (() => {
      try {
        spliceEntries(handText, { ...small, entries: [] }, small);
        return false;
      } catch {
        return true;
      }
    })(),
  });
  return cases;
}

if (isEntryPoint(import.meta.filename)) {
  if (process.argv.includes('--selftest')) process.exit(runControls(selftestCases()) === 0 ? 0 : 1);
  const scan = scanTemplates(readTemplateFiles(process.cwd()));
  console.log(
    `${scan.entries.length} template image pin(s), ${scan.unpinned.length} unpinned reference(s)`
  );
}
