/**
 * One slug algorithm for every heading anchor on the site.
 *
 * Every heading id in docs and blog derives from the ENGLISH source document,
 * positionally: the Nth heading of `ar/foo.md` gets the id of the Nth heading of
 * `en/foo.md`. Translated headings keep translated TEXT, but the URL fragment is
 * identical in all 13 locales (the docs.claude.com model), so a shared link
 * survives a language switch and a translation can never move a fragment.
 *
 * This module is the single source for those ids. It is consumed by:
 *   - src/plugins/rehype-stable-heading-ids.mjs (writes the ids into rendered HTML)
 *   - scripts/generate-search-index.js (writes the same ids into search fragments)
 *
 * Plain .mjs on purpose: the search generator runs under bare node, without a
 * TypeScript loader.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Slugger from 'github-slugger';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONTENT_ROOT = path.resolve(__dirname, '../content');
// {{t:namespace.key}} placeholders in headings resolve against the CLI locale
// catalogs, mirroring remark-resolve-translations. Only English is needed here,
// because only English text is ever slugged.
const CLI_EN_LOCALES = path.resolve(__dirname, '../../../cli/src/i18n/locales/en');

const TRANSLATION_KEY_PATTERN = /\{\{t:([a-zA-Z]+)\.([a-zA-Z0-9_.]+)\}\}/g;

const namespaceCache = new Map();

function loadNamespace(namespace) {
  if (!namespaceCache.has(namespace)) {
    const file = path.join(CLI_EN_LOCALES, `${namespace}.json`);
    namespaceCache.set(
      namespace,
      fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf-8')) : null
    );
  }
  return namespaceCache.get(namespace);
}

function resolveEnglishPlaceholders(text) {
  return text.replace(TRANSLATION_KEY_PATTERN, (match, namespace, keyPath) => {
    let current = loadNamespace(namespace);
    for (const key of keyPath.split('.')) {
      if (current === null || typeof current !== 'object') return match;
      current = current[key];
    }
    // An unresolved key stays visible, the same behaviour as
    // remark-resolve-translations, which already warns about it at build time.
    return typeof current === 'string' ? current : match;
  });
}

/**
 * Fence-aware ATX heading scan over a markdown body (frontmatter already
 * stripped). Returns ordered `{ depth, line, text }`.
 *
 * Deliberately NOT a full markdown parser: the corpus (1,107 files, 13 locales)
 * was validated to contain only ATX headings outside code fences, and the rehype
 * plugin hard-errors on any count drift, so a construct this scan cannot see
 * fails the build loudly instead of shipping a wrong anchor.
 */
export function scanHeadings(markdownBody) {
  const lines = markdownBody.split('\n');
  const headings = [];
  let fence = null; // { char, len } of the open fence
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fenceMatch = /^ {0,3}(`{3,}|~{3,})/.exec(line);
    if (fenceMatch) {
      const char = fenceMatch[1][0];
      const len = fenceMatch[1].length;
      if (!fence) {
        fence = { char, len };
      } else if (fence.char === char && len >= fence.len && /^ {0,3}(`{3,}|~{3,})\s*$/.test(line)) {
        fence = null;
      }
      continue;
    }
    if (fence) continue;
    const headingMatch = /^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$/.exec(line);
    if (headingMatch) {
      const text = (headingMatch[2] ?? '').replace(/[ \t]+#+[ \t]*$/, '');
      headings.push({ depth: headingMatch[1].length, line: i, text });
    }
  }
  return headings;
}

/** Strip frontmatter from a raw content file. */
export function stripFrontmatter(raw) {
  return raw.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '');
}

/**
 * Slug a heading's raw markdown text the way github-slugger slugs the rendered
 * text: resolve {{t:...}} to English, drop code-span backticks (their content is
 * rendered text), then slug. Astro trims a trailing hyphen; mirror that so
 * English ids stay byte-identical to the ones Astro has always emitted.
 */
function slugHeadingText(slugger, rawText) {
  const text = resolveEnglishPlaceholders(rawText).replace(/`+/g, '');
  let slug = slugger.slug(text);
  if (slug.endsWith('-')) slug = slug.slice(0, -1);
  return slug;
}

const englishAnchorCache = new Map();

/**
 * Ordered `{ depth, id }` for the English source of `<collection>/<filename>`,
 * e.g. ('docs', 'quick-start.md'). Throws when the English file does not exist:
 * a translated document with no English counterpart has no anchor identity, and
 * silently skipping it is how a whole locale went unchecked once before.
 */
export function englishAnchorsFor(collection, filename) {
  const file = path.join(CONTENT_ROOT, collection, 'en', filename);
  const stat = fs.statSync(file, { throwIfNoEntry: false });
  if (!stat) {
    throw new Error(
      `No English source at src/content/${collection}/en/${filename}. ` +
        `Heading anchors derive from the English document; a translation cannot exist without it.`
    );
  }
  const cacheKey = `${collection}/${filename}`;
  const cached = englishAnchorCache.get(cacheKey);
  if (cached && cached.mtimeMs === stat.mtimeMs) return cached.anchors;

  const body = stripFrontmatter(fs.readFileSync(file, 'utf-8'));
  const slugger = new Slugger();
  const anchors = scanHeadings(body).map((h) => ({
    depth: h.depth,
    id: slugHeadingText(slugger, h.text),
  }));
  englishAnchorCache.set(cacheKey, { mtimeMs: stat.mtimeMs, anchors });
  return anchors;
}

/**
 * Classify an absolute path as a content-collection document.
 * Returns `{ collection, locale, filename }` or null for anything else.
 */
export function contentFileInfo(absPath) {
  if (!absPath) return null;
  const match = /[\\/]src[\\/]content[\\/](docs|blog)[\\/]([a-z]{2})[\\/]([^\\/]+\.mdx?)$/.exec(
    absPath
  );
  if (!match) return null;
  return { collection: match[1], locale: match[2], filename: match[3] };
}
