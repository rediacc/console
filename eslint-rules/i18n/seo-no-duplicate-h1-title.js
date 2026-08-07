/**
 * ESLint rule to detect when H1 text (hero.title) is effectively identical to meta.title.
 *
 * When H1 and title match, search engines see redundancy. The title should be optimized
 * for search (with brand name), and the H1 for on-page users.
 *
 * Checks siblings: if a page section has both "hero.title" and "meta.title", the H1 text
 * must not be a substring of the title (after stripping brand suffixes like " | Rediacc").
 */

import { memberKey, objectMembers, joinPath } from './shared/json-ast.js';

/**
 * The String node of an object's `title` member, or null. Last one wins, as
 * the original inline loop did -- duplicate keys are json/no-duplicate-keys'
 * problem, not this rule's.
 */
const findTitleString = (objNode) => {
  let found = null;
  for (const sub of objectMembers(objNode)) {
    if (sub.type !== 'Member') continue;
    if (memberKey(sub) === 'title' && sub.value?.type === 'String') {
      found = sub.value;
    }
  }
  return found;
};

/** @type {import('eslint').Rule.RuleModule} */
export const seoNoDuplicateH1Title = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Prevent H1 (hero.title) from being identical to meta title',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          brandSuffixes: {
            type: 'array',
            items: { type: 'string' },
            default: [' | Rediacc', ' — Rediacc', ' - Rediacc'],
            description: 'Brand suffixes stripped from title before comparison',
          },
          exemptKeys: {
            type: 'array',
            items: { type: 'string' },
            default: [],
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      duplicate:
        'H1 "{{h1}}" is identical to the title (after brand suffix removal) at "{{titleKey}}". Make H1 and title distinct for better SEO. See docs/i18n/CONVENTIONS.md.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const brandSuffixes = options.brandSuffixes || [' | Rediacc', ' \u2014 Rediacc', ' - Rediacc'];
    const exemptKeys = options.exemptKeys || [];

    function isExempt(path) {
      return exemptKeys.some((exempt) => path.includes(exempt));
    }

    /**
     * Strip brand suffixes from a title string for comparison.
     */
    function stripBrand(title) {
      let cleaned = title;
      for (const suffix of brandSuffixes) {
        if (cleaned.endsWith(suffix)) {
          cleaned = cleaned.slice(0, -suffix.length);
          break;
        }
      }
      return cleaned.trim().toLowerCase();
    }

    /**
     * Walk the JSON tree, collecting hero.title and meta.title pairs within
     * each page section, then comparing them.
     */
    /**
     * Record the hero/meta title carried by one subobject, if it is one.
     */
    const captureTitles = (found, key, value, fullPath) => {
      if (key === 'hero') {
        const title = findTitleString(value);
        if (title) {
          found.heroTitle = title.value;
          found.heroTitleNode = title;
        }
        return;
      }

      if (key === 'meta') {
        const title = findTitleString(value);
        if (title) {
          found.metaTitle = title.value;
          found.metaTitleKey = `${fullPath}.title`;
        }
      }
    };

    /** If both titles exist at this level, compare them. */
    const reportIfDuplicate = (found, path) => {
      if (!found.heroTitle || !found.metaTitle || !found.heroTitleNode) return;
      if (isExempt(path)) return;

      const cleanedTitle = stripBrand(found.metaTitle);
      const cleanedH1 = found.heroTitle.trim().toLowerCase();
      if (cleanedH1 !== cleanedTitle) return;

      context.report({
        node: found.heroTitleNode,
        messageId: 'duplicate',
        data: { h1: found.heroTitle, titleKey: found.metaTitleKey },
      });
    };

    const collectAndCheck = (node, path = '') => {
      const found = {
        heroTitle: null,
        heroTitleNode: null,
        metaTitle: null,
        metaTitleKey: null,
      };

      for (const member of objectMembers(node)) {
        if (member.type !== 'Member') continue;

        const key = memberKey(member);
        const value = member.value;
        if (!key || !value || value.type !== 'Object') continue;

        const fullPath = joinPath(path, key);
        // Check if this is the "hero" or "meta" subobject
        captureTitles(found, key, value, fullPath);

        // Always recurse
        collectAndCheck(value, fullPath);
      }

      reportIfDuplicate(found, path);
    };

    return {
      Document(node) {
        if (node.body?.type === 'Object') {
          collectAndCheck(node.body);
        }
      },
    };
  },
};

export default seoNoDuplicateH1Title;
