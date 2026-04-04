/**
 * ESLint rule to detect when H1 text (hero.title) is effectively identical to meta.title.
 *
 * When H1 and title match, search engines see redundancy. The title should be optimized
 * for search (with brand name), and the H1 for on-page users.
 *
 * Checks siblings: if a page section has both "hero.title" and "meta.title", the H1 text
 * must not be a substring of the title (after stripping brand suffixes like " | Rediacc").
 */

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
        'H1 "{{h1}}" is identical to the title (after brand suffix removal) at "{{titleKey}}". Make H1 and title distinct for better SEO.',
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
    const collectAndCheck = (node, path = '') => {
      if (!node || node.type !== 'Object') return;

      let heroTitle = null;
      let heroTitleNode = null;
      let metaTitle = null;
      let metaTitleKey = null;

      for (const member of node.members || []) {
        if (member.type !== 'Member') continue;

        const key =
          member.name?.type === 'String' ? member.name.value : member.name?.name;
        if (!key) continue;

        const fullPath = path ? `${path}.${key}` : key;
        const value = member.value;
        if (!value) continue;

        if (value.type === 'Object') {
          // Check if this is the "hero" or "meta" subobject
          if (key === 'hero') {
            for (const sub of value.members || []) {
              if (sub.type !== 'Member') continue;
              const subKey = sub.name?.type === 'String' ? sub.name.value : sub.name?.name;
              if (subKey === 'title' && sub.value?.type === 'String') {
                heroTitle = sub.value.value;
                heroTitleNode = sub.value;
              }
            }
          } else if (key === 'meta') {
            for (const sub of value.members || []) {
              if (sub.type !== 'Member') continue;
              const subKey = sub.name?.type === 'String' ? sub.name.value : sub.name?.name;
              if (subKey === 'title' && sub.value?.type === 'String') {
                metaTitle = sub.value.value;
                metaTitleKey = `${fullPath}.title`;
              }
            }
          }

          // Always recurse
          collectAndCheck(value, fullPath);
        }
      }

      // If both exist at this level, compare them
      if (heroTitle && metaTitle && heroTitleNode && !isExempt(path)) {
        const cleanedTitle = stripBrand(metaTitle);
        const cleanedH1 = heroTitle.trim().toLowerCase();

        if (cleanedH1 === cleanedTitle) {
          context.report({
            node: heroTitleNode,
            messageId: 'duplicate',
            data: { h1: heroTitle, titleKey: metaTitleKey },
          });
        }
      }
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
