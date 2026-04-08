/**
 * ESLint rule to prevent trailing slashes in internal navigation links.
 *
 * The www site is configured with `trailingSlash: 'never'` in
 * astro.config.mjs, which means internal absolute paths must NOT end with `/`
 * (except for the root `/` itself). When they do:
 *   - Astro's dev server shows an error overlay on click
 *   - In production, the request triggers an extra redirect hop
 *   - JSON-LD breadcrumb URLs become inconsistent with canonical URLs,
 *     which Google Search Console flags
 *
 * Catches patterns like:
 *   <a href={`/${lang}/`}>Home</a>
 *   <a href="/en/blog/">Blog</a>
 *   { url: `/${currentLang}/docs/` }
 *
 * Allows:
 *   - The root `/` itself
 *   - External URLs (anything containing `://`)
 *   - Hash and query strings (the path is checked after stripping `#...` and `?...`)
 *   - Paths NOT starting with `/[a-z]` (e.g. `#anchor`, `mailto:`, relative paths)
 *
 * Modeled on `seo-no-hash-breadcrumb-url.js`. No autofixer — silent rewrites of
 * URLs in pre-commit/IDE save actions would mask author intent.
 */

/** Internal-path prefixes that route to a different system or static asset
 * tree, where trailing slashes are intentional or controlled elsewhere. */
const EXEMPT_PREFIXES = [
  '/account/',
  '/api/',
  '/releases/',
  '/bin/',
  '/var/',
  '/run/',
  '/assets/',
  '/fonts/',
  '/svg/',
  '/admin/',
  '/dev/',
  '/usr/',
  '/etc/',
  '/tmp/',
];

/** Attribute names that hold internal URLs in JSX. */
const URL_ATTR_NAMES = new Set(['href', 'to', 'src', 'action']);

/** Object property keys that hold internal URLs (breadcrumbs, link items). */
const URL_PROP_KEYS = new Set(['href', 'url', 'to']);

/** Strip `#fragment` and `?query` suffixes before evaluating the path. */
function stripFragmentAndQuery(value) {
  let result = value;
  const hashIdx = result.indexOf('#');
  if (hashIdx >= 0) result = result.slice(0, hashIdx);
  const queryIdx = result.indexOf('?');
  if (queryIdx >= 0) result = result.slice(0, queryIdx);
  return result;
}

/** Decide whether the given string is an internal path with a trailing slash. */
function hasTrailingSlashIssue(raw) {
  if (typeof raw !== 'string') return false;
  if (raw.includes('://')) return false; // external URL
  if (raw === '/') return false;          // bare root is fine
  const path = stripFragmentAndQuery(raw);
  if (path === '/' || path === '') return false;
  // Must start with `/` followed by a lowercase letter or template-literal
  // placeholder marker (we treat `${...}` as opaque). Otherwise it's not an
  // internal absolute path we care about (e.g. `mailto:`, `tel:`, `#anchor`).
  if (!/^\/(?:[a-z$])/.test(path)) return false;
  // Skip exempt prefixes (different systems / static asset trees).
  for (const prefix of EXEMPT_PREFIXES) {
    if (path.startsWith(prefix)) return false;
  }
  return path.endsWith('/');
}

/** Reduce a TemplateLiteral node to its raw string form by joining static
 * quasis with `${...}` placeholders. We don't evaluate expressions; we just
 * need to know what the resulting string looks like at the slash boundary. */
function templateLiteralRaw(node) {
  return node.quasis
    .map((q, i) => q.value.raw + (i < node.quasis.length - 1 ? '${...}' : ''))
    .join('');
}

/** @type {import('eslint').Rule.RuleModule} */
export const seoNoTrailingSlashInternalLink = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Disallow trailing slashes in internal navigation links (conflicts with trailingSlash: "never")',
      recommended: true,
    },
    messages: {
      trailingSlash:
        'Internal link "{{value}}" ends with "/". The site is configured with trailingSlash: "never" — drop the trailing slash to avoid an extra redirect hop and Astro dev-overlay errors.',
    },
    schema: [],
  },

  create(context) {
    function checkValueNode(valueNode) {
      if (!valueNode) return;

      // String literal: href="/en/"
      if (valueNode.type === 'Literal' && typeof valueNode.value === 'string') {
        if (hasTrailingSlashIssue(valueNode.value)) {
          context.report({
            node: valueNode,
            messageId: 'trailingSlash',
            data: { value: valueNode.value },
          });
        }
        return;
      }

      // Template literal: href={`/${lang}/`}
      if (valueNode.type === 'TemplateLiteral') {
        const raw = templateLiteralRaw(valueNode);
        if (hasTrailingSlashIssue(raw)) {
          context.report({
            node: valueNode,
            messageId: 'trailingSlash',
            data: { value: raw },
          });
        }
      }
    }

    return {
      // <a href={...}> / <Link to={...}> / <img src={...}>
      JSXAttribute(node) {
        const name =
          node.name?.type === 'JSXIdentifier' ? node.name.name : null;
        if (!name || !URL_ATTR_NAMES.has(name)) return;
        const value = node.value;
        if (!value) return;
        if (value.type === 'Literal') {
          checkValueNode(value);
        } else if (value.type === 'JSXExpressionContainer') {
          checkValueNode(value.expression);
        }
      },

      // { href: '/en/', url: `/${lang}/`, to: ... }
      Property(node) {
        if (node.computed) return;
        const keyName =
          node.key?.type === 'Identifier'
            ? node.key.name
            : node.key?.type === 'Literal'
              ? node.key.value
              : null;
        if (!keyName || !URL_PROP_KEYS.has(keyName)) return;
        checkValueNode(node.value);
      },
    };
  },
};
