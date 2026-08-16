/**
 * Card-grid splitter for cheat-sheet style documents.
 *
 * Takes a rendered HTML string (an Astro slot render of a markdown document)
 * and cuts it into "cards" at every TOP-LEVEL `<h2>` boundary.  Everything
 * before the first such heading becomes the leading card (the document title
 * plus its intro paragraph), which the stylesheet renders as the branding
 * header.
 *
 * The scanner is tag-aware rather than a naive `split()`, so an `<h2>` that
 * appears inside a code fence, inside a comment, or nested in another element
 * never starts a new card.
 */

/** Elements that never have a closing tag, so they must not change nesting depth. */
const VOID_ELEMENTS = new Set([
  'area',
  'base',
  'br',
  'col',
  'embed',
  'hr',
  'img',
  'input',
  'link',
  'meta',
  'param',
  'source',
  'track',
  'wbr',
]);

/** Elements whose content is text, not markup — anything tag-shaped inside is data. */
const RAW_TEXT_ELEMENTS = new Set(['pre', 'script', 'style', 'textarea']);

/** Matches an HTML comment, or a start/end tag with quote-aware attributes. */
const TOKEN_PATTERN = /<!--[\s\S]*?-->|<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:"[^"]*"|'[^']*'|[^>])*)>/g;

/** What a matched token does to nesting depth. */
type TokenKind = 'comment' | 'close' | 'open' | 'void';

function classify(
  token: string,
  closingSlash: string,
  name: string,
  attributes: string
): TokenKind {
  if (token.startsWith('<!--')) return 'comment';
  if (closingSlash === '/') return 'close';
  if (VOID_ELEMENTS.has(name) || attributes.trimEnd().endsWith('/')) return 'void';
  return 'open';
}

/**
 * Index just past a raw-text element's opening tag, jumped to its closing tag
 * so that tag-shaped text inside a code fence is never read as markup.
 */
function endOfRawText(html: string, name: string, from: number): number {
  const closeIndex = html.toLowerCase().indexOf(`</${name}`, from);
  return closeIndex === -1 ? html.length : closeIndex;
}

/**
 * Nesting depth after this token. A comment carries no structure and a void
 * element has no closing tag, so neither moves the count; a closing tag for a
 * void element is malformed input and must not unbalance it either.
 */
function nextDepth(kind: TokenKind, name: string, depth: number): number {
  if (kind === 'open') return depth + 1;
  if (kind === 'close' && !VOID_ELEMENTS.has(name)) return Math.max(0, depth - 1);
  return depth;
}

/** Offsets of every `<h2>` that opens at nesting depth zero. */
function topLevelH2Offsets(html: string): number[] {
  const offsets: number[] = [];
  const pattern = new RegExp(TOKEN_PATTERN.source, 'g');
  let depth = 0;

  for (let match = pattern.exec(html); match !== null; match = pattern.exec(html)) {
    const [token, closingSlash, rawName, attributes] = match;
    const name = rawName.toLowerCase();
    const kind = classify(token, closingSlash, name, attributes);

    if (kind === 'open' && name === 'h2' && depth === 0) offsets.push(match.index);
    depth = nextDepth(kind, name, depth);
    if (kind === 'open' && RAW_TEXT_ELEMENTS.has(name)) {
      pattern.lastIndex = endOfRawText(html, name, pattern.lastIndex);
    }
  }

  return offsets;
}

/**
 * Split rendered HTML into cards at top-level `<h2>` boundaries.
 *
 * @param html - Rendered HTML, typically `await Astro.slots.render('default')`
 * @returns One trimmed HTML fragment per card; empty fragments are dropped
 */
export function splitIntoCards(html: string): string[] {
  if (html.trim() === '') return [];

  const boundaries = topLevelH2Offsets(html);
  if (boundaries.length === 0) return [html.trim()];

  const cuts = boundaries[0] === 0 ? boundaries : [0, ...boundaries];
  return cuts
    .map((cut, i) => html.slice(cut, cuts[i + 1] ?? html.length).trim())
    .filter((chunk) => chunk !== '');
}
