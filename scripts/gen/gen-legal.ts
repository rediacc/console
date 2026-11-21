#!/usr/bin/env tsx
/**
 * gen-legal -- one version and one hash per legal document, taken from the published text
 * (agent/plans/PLAN-terms-acceptance.md Design 2).
 *
 * INPUTS
 *   .ci/config/legal-documents.json   hand-edited: per document, its www page, its catalog key
 *                                     under `pages.` of en.json, and its versions
 *                                     {version, effective, material, sha256}
 *   packages/www/src/i18n/translations/<locale>.json
 *                                     the English text of every document, and the
 *                                     `legal.consent.*` notices of every locale
 *   packages/shared/src/legal/entity.generated.json
 *                                     the contracting entity (`./run.sh legal-entity sync`)
 *
 * OUTPUTS (--write)
 *   packages/www/public/legal/archive/<doc>-<version>.txt
 *       the canonical English text of a version, written once, never rewritten
 *   packages/shared/src/legal/documents.generated.ts
 *   packages/shared/src/legal/consent.generated.ts
 *   and the `sha256` of a version whose manifest entry has none, filled from its archive
 *
 * THE CANONICAL RENDER. A document renders the way its page reads: the hero title and effective
 * date, then each section in `orderedKeys` order (title, paragraphs, items, subsections in
 * `orderedKeys` order, trailing paragraphs), then the contact block. Entity tokens
 * (`{{legalName}}` ...) are substituted from the projection; tags are reduced to text and a link
 * keeps its target as `text <url>`; LF line endings, UTF-8. An unknown `{{token}}` refuses the
 * render rather than archiving a placeholder.
 *
 * `--from-ref <ref>` renders from `git show <ref>:packages/www/src/i18n/translations/en.json`,
 * so a version can be archived from the text it was published with (E4 archives the ToS as
 * 2026-03-15 from main, before the rewrite lands).
 *
 * Without --write it prints what it would write and exits 0. `check:ci-terms-version` imports
 * `buildOutputs` and compares, so the gate and the generator cannot disagree about a byte.
 *
 * Usage: npx tsx scripts/gen/gen-legal.ts [--write] [--from-ref <ref>]
 */
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

import { SITE_LOCALES } from '@rediacc/locales';

import { orderedKeys } from '../../packages/www/src/utils/legal-order.ts';

export const MANIFEST_REL = '.ci/config/legal-documents.json';
export const TRANSLATIONS_REL = 'packages/www/src/i18n/translations';
export const ENTITY_REL = 'packages/shared/src/legal/entity.generated.json';
export const ARCHIVE_REL = 'packages/www/public/legal/archive';
export const DOCUMENTS_TS_REL = 'packages/shared/src/legal/documents.generated.ts';
export const CONSENT_TS_REL = 'packages/shared/src/legal/consent.generated.ts';
export const WELL_KNOWN_REL = 'packages/shared/src/config/well-known.generated.ts';

/** The site locales, from the single source in packages/locales. */
export const LOCALES = SITE_LOCALES;

/** Acceptance method -> its notice key under `legal.consent` of every catalog. The unattended flag's notice is the refusal text that names the flag. */
export const CONSENT_KEYS = {
  'web-checkbox': 'webCheckbox',
  'cli-prompt': 'cliPrompt',
  'cli-flag-unattended': 'cliRefusal',
  'stripe-checkout': 'stripeCheckout',
} as const;
export type AcceptanceMethod = keyof typeof CONSENT_KEYS;

export interface ManifestVersion {
  version: string;
  effective: string;
  material: boolean;
  sha256?: string;
}
export interface ManifestDocument {
  page: string;
  catalogKey: string;
  versions: ManifestVersion[];
}
export interface Manifest {
  $comment?: string[];
  documents: Record<string, ManifestDocument>;
}

export interface Sources {
  root: string;
  manifest: Manifest;
  /** The English catalog the documents render from (the working tree, or `--from-ref`). */
  en: Record<string, unknown>;
  /** Every locale's catalog, for the consent notices (always the working tree). */
  catalogs: Record<string, Record<string, unknown>>;
  entity: Record<string, string>;
  siteOrigin: string;
  locales: readonly string[];
}

export class LegalError extends Error {}

export function sha256(text: string): string {
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

function readJson<T>(file: string): T {
  return JSON.parse(fs.readFileSync(file, 'utf8')) as T;
}

export function readSiteOrigin(root: string): string {
  const text = fs.readFileSync(path.join(root, WELL_KNOWN_REL), 'utf8');
  const m = /export const WK_SITE_ORIGIN = '([^']+)';/.exec(text);
  if (!m) throw new LegalError(`${WELL_KNOWN_REL} declares no WK_SITE_ORIGIN`);
  return m[1];
}

export function loadSources(
  root: string,
  opts: { fromRef?: string; locales?: readonly string[] } = {}
): Sources {
  const locales = opts.locales ?? LOCALES;
  const catalogs: Record<string, Record<string, unknown>> = {};
  for (const locale of locales) {
    catalogs[locale] = readJson(path.join(root, TRANSLATIONS_REL, `${locale}.json`));
  }
  const en = opts.fromRef
    ? (JSON.parse(
        execFileSync('git', ['-C', root, 'show', `${opts.fromRef}:${TRANSLATIONS_REL}/en.json`], {
          encoding: 'utf8',
          maxBuffer: 64 * 1024 * 1024,
        })
      ) as Record<string, unknown>)
    : catalogs.en;
  return {
    root,
    manifest: readJson<Manifest>(path.join(root, MANIFEST_REL)),
    en,
    catalogs,
    entity: readJson<Record<string, string>>(path.join(root, ENTITY_REL)),
    siteOrigin: readSiteOrigin(root),
    locales,
  };
}

function get(obj: unknown, dotted: string): unknown {
  return dotted.split('.').reduce<unknown>((cur, key) => {
    if (cur && typeof cur === 'object' && key in (cur as Record<string, unknown>)) {
      return (cur as Record<string, unknown>)[key];
    }
    return undefined;
  }, obj);
}

export function countryName(code: string, locale: string): string {
  return new Intl.DisplayNames([locale], { type: 'region' }).of(code) ?? code;
}

export function entityTokens(
  entity: Record<string, string>,
  locale: string
): Record<string, string> {
  return {
    legalName: entity.legalName,
    registryCode: entity.registryCode,
    registerName: entity.registerName,
    vatNumber: entity.vatNumber,
    registeredAddress: entity.registeredAddress,
    country: countryName(entity.countryCode, locale),
  };
}

/** `{{name}}` occurrences, in order of first appearance. */
export function tokensIn(text: string): string[] {
  const out: string[] = [];
  for (const m of text.matchAll(/\{\{\s*(\w+)\s*\}\}/g)) {
    if (!out.includes(m[1])) out.push(m[1]);
  }
  return out;
}

export function substitute(text: string, tokens: Record<string, string>, where: string): string {
  return text.replace(/\{\{\s*(\w+)\s*\}\}/g, (_m, name: string) => {
    if (!(name in tokens)) {
      throw new LegalError(
        `${where}: unknown token {{${name}}}; known: ${Object.keys(tokens).join(', ')}`
      );
    }
    return tokens[name];
  });
}

/**
 * Tags to text: a link keeps its target as `text <url>`, resolved against BASE (the page's own
 * English URL) so a relative href becomes absolute; `<br>` is a line break; every other tag is
 * dropped. The link target is parked behind control characters while the tags are stripped, so
 * `<https://...>` is not mistaken for a tag.
 */
export function toText(html: string, base: string): string {
  return html
    .replace(
      /<a\s[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/gi,
      (_m, href: string, inner: string) => {
        const text = inner.replace(/<[^>]+>/g, '');
        const target = href.startsWith('mailto:') ? href : new URL(href, base).toString();
        return `${text} \u0001${target}\u0002`;
      }
    )
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/\u0001/g, '<')
    .replace(/\u0002/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
}

type Block = {
  title?: unknown;
  content?: unknown;
  items?: unknown;
  subsections?: unknown;
  content2?: unknown;
};

function strings(value: unknown, where: string): string[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.some((v) => typeof v !== 'string')) {
    throw new LegalError(`${where} is not a list of strings`);
  }
  return value as string[];
}

/** The canonical English text of one document. */
export function renderDocument(
  en: Record<string, unknown>,
  catalogKey: string,
  entity: Record<string, string>,
  pageUrl: string
): string {
  const base = `pages.${catalogKey}`;
  const doc = get(en, base) as Record<string, unknown> | undefined;
  if (!doc || typeof doc !== 'object') throw new LegalError(`en.json has no ${base}`);
  const tokens = entityTokens(entity, 'en');
  const lines: string[] = [];
  const text = (s: unknown, where: string): string => {
    if (typeof s !== 'string') throw new LegalError(`${where} is not a string`);
    return toText(substitute(s, tokens, where), pageUrl);
  };
  const para = (s: string, where: string) => {
    lines.push(text(s, where), '');
  };
  const block = (b: Block, where: string, ref: Block | undefined) => {
    for (const [i, p] of strings(b.content, `${where}.content`).entries())
      para(p, `${where}.content[${i}]`);
    for (const [i, item] of strings(b.items, `${where}.items`).entries()) {
      lines.push(`- ${text(item, `${where}.items[${i}]`)}`);
    }
    if (b.items) lines.push('');
    if (b.subsections) {
      const subs = b.subsections as Record<string, Block>;
      const refSubs = ref?.subsections as Record<string, Block> | undefined;
      for (const key of orderedKeys(subs, refSubs)) {
        const sub = subs[key];
        lines.push(text(sub.title, `${where}.subsections.${key}.title`), '');
        block(sub, `${where}.subsections.${key}`, refSubs?.[key]);
      }
    }
    for (const [i, p] of strings(b.content2, `${where}.content2`).entries())
      para(p, `${where}.content2[${i}]`);
  };
  lines.push(text(get(doc, 'hero.title'), `${base}.hero.title`));
  const effective = get(doc, 'hero.effectiveDate');
  if (effective !== undefined) lines.push(text(effective, `${base}.hero.effectiveDate`));
  lines.push('');
  const sections = (doc.sections ?? {}) as Record<string, Block>;
  for (const key of orderedKeys(sections)) {
    const where = `${base}.sections.${key}`;
    lines.push(text(sections[key].title, `${where}.title`), '');
    block(sections[key], where, sections[key]);
  }
  const contactTitle = get(doc, 'contact.title');
  if (contactTitle !== undefined) {
    lines.push(text(contactTitle, `${base}.contact.title`), '');
    const desc = get(doc, 'contact.description');
    if (desc !== undefined) para(desc as string, `${base}.contact.description`);
  }
  while (lines.length > 0 && lines[lines.length - 1] === '') lines.pop();
  return `${lines.join('\n')}\n`;
}

/** The English page a document is published at; relative links in its text resolve against it. */
export function documentPageUrl(siteOrigin: string, page: string): string {
  return `${siteOrigin}/en/${page}`;
}

export function archiveRel(doc: string, version: string): string {
  return `${ARCHIVE_REL}/${doc}-${version}.txt`;
}

export function archiveUrl(siteOrigin: string, doc: string, version: string): string {
  return `${siteOrigin}/legal/archive/${doc}-${version}.txt`;
}

const BANNER = (source: string) =>
  `// AUTO-GENERATED by \`npx tsx scripts/gen/gen-legal.ts --write\` - DO NOT EDIT\n// Source: ${source}; check:ci-terms-version holds this file equal to its render.\n`;

function tsString(value: string): string {
  if (value.includes("'") && !value.includes('"')) return JSON.stringify(value);
  return `'${value.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n')}'`;
}

export function renderDocumentsTs(manifest: Manifest, _siteOrigin: string): string {
  const docs = Object.entries(manifest.documents);
  let body = '';
  for (const [id, doc] of docs) {
    body += `  '${id}': {\n    id: '${id}',\n    page: ${tsString(doc.page)},\n    versions: [\n`;
    for (const v of doc.versions) {
      body +=
        '      {\n' +
        `        version: '${v.version}',\n` +
        `        effective: '${v.effective}',\n` +
        `        material: ${v.material},\n` +
        `        sha256: '${v.sha256 ?? ''}',\n` +
        `        archiveUrl: \`\${WK_SITE_ORIGIN}${archiveUrl('', id, v.version)}\`,\n` +
        '      },\n';
    }
    body += '    ],\n  },\n';
  }
  return (
    BANNER(`${MANIFEST_REL} and the English text of each document`) +
    "\nimport { WK_SITE_ORIGIN } from '../config/well-known.generated.js';\n" +
    "import type { LegalDocument, LegalDocumentId } from './types.js';\n\n" +
    'export const LEGAL_DOCUMENTS: Readonly<Partial<Record<LegalDocumentId, LegalDocument>>> = {\n' +
    body +
    '};\n'
  );
}

/** Every locale's four consent notices, tokens substituted; '' where the catalog has none yet. */
export function consentNotices(src: Sources): Record<string, Record<AcceptanceMethod, string>> {
  const out: Record<string, Record<AcceptanceMethod, string>> = {};
  for (const locale of src.locales) {
    const tokens = {
      ...entityTokens(src.entity, locale),
      termsUrl: `${src.siteOrigin}/${locale}/terms-of-service`,
      privacyUrl: `${src.siteOrigin}/${locale}/privacy-policy`,
    };
    const notices = {} as Record<AcceptanceMethod, string>;
    for (const [method, key] of Object.entries(CONSENT_KEYS) as [AcceptanceMethod, string][]) {
      const raw = get(src.catalogs[locale], `legal.consent.${key}`);
      notices[method] =
        typeof raw === 'string'
          ? substitute(raw, tokens, `${locale}.json legal.consent.${key}`)
          : '';
    }
    out[locale] = notices;
  }
  return out;
}

/** The entity fields a notice may substitute, each emitted as its LEGAL_ENTITY field. `country` is locale-derived, not a LEGAL_ENTITY field. */
const ENTITY_SOURCE_FIELDS = [
  'legalName',
  'registryCode',
  'registerName',
  'vatNumber',
  'registeredAddress',
] as const;

/** Literal value -> the source expression that yields it, longest value first so no value is cut inside a longer one. */
export function noticeSubstitutions(
  siteOrigin: string,
  entity: Record<string, string>
): [string, string][] {
  if (!siteOrigin) {
    throw new LegalError(
      'the site origin is empty: every notice would be split between its characters'
    );
  }
  const subs: [string, string][] = [[siteOrigin, 'WK_SITE_ORIGIN']];
  for (const field of ENTITY_SOURCE_FIELDS) {
    const value = entity[field];
    if (value) subs.push([value, `LEGAL_ENTITY.${field}`]);
  }
  return subs.sort((a, b) => b[0].length - a[0].length);
}

/**
 * A notice as source text: each exact occurrence of the site origin becomes WK_SITE_ORIGIN and
 * of an entity value its LEGAL_ENTITY field. A host spelled any other way (for example without
 * `www`) is not an occurrence and stays literal.
 */
export function tsNotice(value: string, subs: [string, string][]): string {
  if (!value || !subs.some(([lit]) => value.includes(lit))) return tsString(value);
  let parts: (string | { expr: string })[] = [value];
  for (const [lit, expr] of subs) {
    parts = parts.flatMap((part) => {
      if (typeof part !== 'string' || !part.includes(lit)) return [part];
      return part.split(lit).flatMap((piece, i) => (i === 0 ? [piece] : [{ expr }, piece]));
    });
  }
  const escape = (text: string) =>
    text.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$\{/g, '\\${').replace(/\n/g, '\\n');
  return `\`${parts.map((p) => (typeof p === 'string' ? escape(p) : `\${${p.expr}}`)).join('')}\``;
}

export function renderConsentTs(
  notices: Record<string, Record<AcceptanceMethod, string>>,
  siteOrigin: string,
  entity: Record<string, string>
): string {
  const methods = Object.keys(CONSENT_KEYS) as AcceptanceMethod[];
  const subs = noticeSubstitutions(siteOrigin, entity);
  const block = (fn: (text: string) => string) =>
    Object.entries(notices)
      .map(
        ([locale, n]) =>
          `  ${locale}: {\n${methods.map((m) => `    '${m}': ${fn(n[m])},\n`).join('')}  },\n`
      )
      .join('');
  const source = block((t) => tsNotice(t, subs));
  const entityImport = source.includes('${LEGAL_ENTITY.')
    ? "import { LEGAL_ENTITY } from './entity.generated.js';\n"
    : '';
  return (
    BANNER(
      'the legal.consent.* keys of packages/www/src/i18n/translations/<locale>.json; the site origin and entity tokens are emitted as references to WK_SITE_ORIGIN and LEGAL_ENTITY'
    ) +
    "\nimport { WK_SITE_ORIGIN } from '../config/well-known.generated.js';\n" +
    entityImport +
    "import type { ConsentNotices } from './types.js';\n\n" +
    '/** The canonical consent notice per locale and method. An empty string is a notice no catalog carries yet. */\n' +
    'export const CONSENT_NOTICES: ConsentNotices = {\n' +
    source +
    '};\n\n' +
    '/** sha256 of each notice above (UTF-8); empty where the notice is empty. */\n' +
    'export const CONSENT_NOTICE_SHA256: ConsentNotices = {\n' +
    block((t) => `'${t ? sha256(t) : ''}'`) +
    '};\n'
  );
}

export interface Outputs {
  /** Manifest with every missing sha256 filled from its archive. */
  manifest: Manifest;
  /** Repo-relative path -> content, for every generated file (archives only where missing). */
  files: Map<string, string>;
  /** Per document, the render of the source text. */
  renders: Map<string, string>;
}

/**
 * Everything --write would write. An archive is written only for the NEWEST version of a document
 * and only when it does not exist yet; an older version without an archive cannot be rendered from
 * today's text and is refused (render it with --from-ref <the ref it was published at>).
 */
export function buildOutputs(src: Sources): Outputs {
  const manifest: Manifest = JSON.parse(JSON.stringify(src.manifest));
  const files = new Map<string, string>();
  const renders = new Map<string, string>();
  for (const [id, doc] of Object.entries(manifest.documents)) {
    const render = renderDocument(
      src.en,
      doc.catalogKey,
      src.entity,
      documentPageUrl(src.siteOrigin, doc.page)
    );
    renders.set(id, render);
    doc.versions.forEach((v, i) => {
      const rel = archiveRel(id, v.version);
      const exists = fs.existsSync(path.join(src.root, rel));
      const newest = i === doc.versions.length - 1;
      if (!exists) {
        if (!newest) {
          throw new LegalError(
            `${id} ${v.version} has no archive and is not the newest version; render it with --from-ref <the ref it was published at>`
          );
        }
        if (v.sha256 && v.sha256 !== sha256(render)) {
          throw new LegalError(
            `${id} ${v.version}: the manifest sha256 does not match the render of the text; the text changed after the version was declared`
          );
        }
        files.set(rel, render);
        v.sha256 = sha256(render);
      } else if (!v.sha256) {
        v.sha256 = sha256(fs.readFileSync(path.join(src.root, rel), 'utf8'));
      }
    });
  }
  files.set(MANIFEST_REL, `${JSON.stringify(manifest, null, 2)}\n`);
  files.set(DOCUMENTS_TS_REL, renderDocumentsTs(manifest, src.siteOrigin));
  files.set(CONSENT_TS_REL, renderConsentTs(consentNotices(src), src.siteOrigin, src.entity));
  return { manifest, files, renders };
}

function main(argv: string[]): number {
  const write = argv.includes('--write');
  const refAt = argv.indexOf('--from-ref');
  const fromRef = refAt >= 0 ? argv[refAt + 1] : undefined;
  if (refAt >= 0 && !fromRef) {
    console.error('gen-legal: --from-ref needs a ref');
    return 2;
  }
  const unknown = argv.filter((a, i) => !['--write', '--from-ref'].includes(a) && i !== refAt + 1);
  if (unknown.length > 0) {
    console.error(`gen-legal: unknown argument(s): ${unknown.join(' ')}`);
    return 2;
  }
  const root = path.resolve(import.meta.dirname, '..', '..');
  try {
    const out = buildOutputs(loadSources(root, { fromRef }));
    let changed = 0;
    for (const [rel, content] of out.files) {
      const file = path.join(root, rel);
      const current = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null;
      if (current === content) continue;
      changed += 1;
      if (write) {
        fs.mkdirSync(path.dirname(file), { recursive: true });
        fs.writeFileSync(file, content);
        console.log(`wrote ${rel}`);
      } else {
        console.log(`would write ${rel}`);
      }
    }
    console.log(
      `gen-legal: ${Object.keys(out.manifest.documents).length} document(s), ${changed} file(s) ${write ? 'written' : 'out of date'}${fromRef ? `, rendered from ${fromRef}` : ''}`
    );
    return 0;
  } catch (err) {
    if (err instanceof LegalError) {
      console.error(`gen-legal: ${err.message}`);
      return 1;
    }
    throw err;
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  process.exit(main(process.argv.slice(2)));
}
