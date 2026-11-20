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
 * THE ID is `template:<app>.<image basename>` (`template:elasticsearch.kibana`), with the
 * service name appended when one template uses the same image twice. The hold key (the id
 * after its colon) therefore never collides with an `image:*` leaf's.
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

/** The template tree, console-relative. */
export const TEMPLATE_ROOT = 'packages/json/templates';
/** The id prefix every generated leaf carries, and no other entry may. */
export const TEMPLATE_PREFIX = 'template:';
/** The hold file every docker leaf names first. */
const HOLD_FILE = policyPath('.pins-upgrade-blocklist', '.');

/** A compose file by name, the shape check-docker-image-freshness reads too. */
export const isComposeFile = (file: string): boolean =>
  /(^|\/)(docker-)?compose[^/]*\.ya?ml$/.test(file);

/** A template's compose file: packages/json/templates/<category>/<app>/docker-compose.yaml. */
export const isTemplateCompose = (file: string): boolean =>
  new RegExp(`^${TEMPLATE_ROOT}/[^/]+/[^/]+/docker-compose\\.yaml$`).test(file);

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

/** The `<category>/<app>` of a template compose file. Pure. */
function appOf(file: string): { category: string; app: string } {
  const parts = file.slice(TEMPLATE_ROOT.length + 1).split('/');
  return { category: parts[0], app: parts[1] };
}

/** The non-Docker-Hub registry host of an image, for its BLOCKER reason. Pure. */
function hostOf(image: string): string {
  return image.split('/')[0];
}

/** The generated leaf of one pinned template reference; `id` is decided by the caller (collisions). Pure. */
export function templateEntry(img: ComposeImage, id: string): PinEntry {
  const { category, app } = appOf(img.file);
  const sites: PinSite[] = [];
  const lead = `^[ \\t]*image:[ \\t]*["']?`;
  if (img.tag !== null)
    sites.push({
      repo: '.',
      file: img.file,
      role: 'version',
      // The tag must start with a version, as isPinned requires: a line edited to `:latest` leaves the site matching nothing, which check:ci-pin-registry reports.
      match: `${lead}(?<value>${esc(img.image)}:v?\\d[^\\s"'@#]*)`,
      expect: 1,
    });
  if (img.digest !== null)
    sites.push({
      repo: '.',
      file: img.file,
      role: 'digest',
      match: `${lead}${esc(img.image)}(?::[^\\s"'@#]+)?@(?<value>sha256:[0-9a-f]{64})`,
      expect: 1,
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
    name: `${img.image} in the ${category}/${app} app template`,
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
  const ordered = [...files.keys()]
    .filter(isTemplateCompose)
    .sort((a, b) => Number(a > b) - Number(a < b));
  for (const file of ordered) {
    for (const img of composeImages(files.get(file) as string, file)) {
      if (isPinned(img)) pinned.push(img);
      else unpinned.push({ img, why: unpinnedWhy(img) });
    }
  }
  const baseId = (img: ComposeImage): string =>
    `${TEMPLATE_PREFIX}${slug(appOf(img.file).app)}.${slug(img.image.split('/').pop() as string)}`;
  const count = new Map<string, number>();
  for (const img of pinned) count.set(baseId(img), (count.get(baseId(img)) ?? 0) + 1);
  const entries: PinEntry[] = [];
  const seen = new Set<string>();
  for (const img of pinned) {
    let id = baseId(img);
    if ((count.get(id) ?? 0) > 1) id = `${id}-${slug(img.service ?? `line${img.line}`)}`;
    if (seen.has(id))
      throw new Error(
        `${img.file}:${img.line}: two template pins resolve to the id ${id}; give the services distinct names`
      );
    seen.add(id);
    entries.push(templateEntry(img, id));
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
  const have = new Map(
    reg.entries.filter((e) => e.id.startsWith(TEMPLATE_PREFIX)).map((e) => [e.id, e])
  );
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
  const first = reg.entries.findIndex((e) => e.id.startsWith(TEMPLATE_PREFIX));
  const rest = reg.entries.filter((e) => !e.id.startsWith(TEMPLATE_PREFIX));
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

/** The template compose files under `root`, read from disk (the caller lists them; a scan of `packages/json/templates/*\/*`). */
export function readTemplateFiles(root: string): Map<string, string> {
  const out = new Map<string, string>();
  const base = path.join(root, TEMPLATE_ROOT);
  if (!fs.existsSync(base)) return out;
  for (const category of fs.readdirSync(base, { withFileTypes: true })) {
    if (!category.isDirectory()) continue;
    for (const app of fs.readdirSync(path.join(base, category.name), { withFileTypes: true })) {
      if (!app.isDirectory()) continue;
      const rel = `${TEMPLATE_ROOT}/${category.name}/${app.name}/docker-compose.yaml`;
      const abs = path.join(root, rel);
      if (fs.existsSync(abs)) out.set(rel, fs.readFileSync(abs, 'utf8'));
    }
  }
  return out;
}

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
    name: 'CONTROL: a compose file outside the template tree is not scanned',
    ok:
      scanTemplates(new Map([['packages/cli/templates/x/docker-compose.yml', es]])).entries
        .length === 0 && !isTemplateCompose('packages/json/templates/a/b/c/docker-compose.yaml'),
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
