/**
 * The docs category vocabulary, in ONE place.
 *
 * The values are the English `z.enum` members from `content/config.ts`, which are
 * IDENTIFIERS rather than display text and are therefore identical in every locale. The
 * translated label lives under `documentation.categories.*` in the locale catalogs, and
 * this module is the only thing that knows how one maps to the other.
 *
 * It exists because the same map was about to be written a second time, for the docs
 * browse page, alongside the copy in `DocsSidebar.astro`. Two copies of a lookup keyed by
 * an enum is exactly the shape that rots: adding a seventh category updates one of them,
 * the other silently falls back to the raw identifier, and nothing fails. A translated
 * value in this vocabulary has already shipped a duplicate Arabic tab once.
 */

/** Display order for browse and navigation surfaces. Learning path first, law last. */
export const CATEGORY_ORDER = [
  'Tutorials',
  'Guides',
  'Concepts',
  'Reference',
  'Use Cases',
  'Legal',
] as const;

export type DocCategory = (typeof CATEGORY_ORDER)[number];

/**
 * The in-page anchor id for a category section on the browse page.
 *
 * `DocsTopTabs.astro:76` builds `href="#<category lowercased, spaces hyphenated>"` when its
 * `variant` is `index`, and nothing ever defined those ids: all six fragments on all
 * thirteen browse pages resolved to no element, which `check:ci-anchor-integrity` reports
 * as 78 dead in-page links. The transform lives here so the two ends of that contract read
 * from one definition rather than agreeing by coincidence, which is the exact shape of the
 * site's existing heading-anchor defect (two slug algorithms, 8,013 dead fragments).
 */
export function categoryAnchor(category: string): string {
  return category.toLowerCase().replaceAll(' ', '-');
}

/** Category identifier -> translation key for its display label. */
export const CATEGORY_KEYS: Record<DocCategory, string> = {
  Tutorials: 'documentation.categories.tutorials',
  Guides: 'documentation.categories.guides',
  Concepts: 'documentation.categories.concepts',
  Reference: 'documentation.categories.reference',
  'Use Cases': 'documentation.categories.useCases',
  Legal: 'documentation.categories.legal',
};

/**
 * Build a label resolver from a translator. Unknown categories fall back to the raw
 * identifier, which is English and readable, rather than to an empty string.
 */
export function makeCategoryLabel(t: (key: string) => string) {
  return (category: string): string => {
    const key = CATEGORY_KEYS[category as DocCategory];
    return key ? t(key) : category;
  };
}

/**
 * Group docs by category in CATEGORY_ORDER, dropping empty groups so a browse page never
 * renders a heading with nothing under it.
 */
export function groupByCategory<
  T extends { data: { category: string; order?: number }; slug: string },
>(docs: T[]): { category: DocCategory; docs: T[] }[] {
  return CATEGORY_ORDER.map((category) => ({
    category,
    docs: docs
      .filter((doc) => doc.data.category === category)
      .sort(
        (a, b) =>
          (a.data.order ?? Number.MAX_SAFE_INTEGER) - (b.data.order ?? Number.MAX_SAFE_INTEGER)
      ),
  })).filter((group) => group.docs.length > 0);
}

/**
 * The docs TAG vocabulary, in ONE place, under the same English-everywhere rule as
 * CATEGORY_ORDER above.
 *
 * `category` is the FORMAT axis (is this a tutorial, a reference page, a legal note);
 * `tags` is the TOPIC axis (what is it about). They are deliberately independent, which is
 * what makes a two-axis filter worth having: "Tutorials" plus "backup" is a question the
 * category alone cannot answer.
 *
 * The values are identifiers, NOT display text, and are identical in all thirteen locales.
 * `content/config.ts` builds its `z.enum` from this array, so a value added here is the
 * only edit needed to make it legal in frontmatter, and a value that is NOT here fails the
 * build rather than silently creating a filter nobody can reach.
 */
export const DOC_TAGS = [
  'getting-started',
  'cli',
  'repositories',
  'forking',
  'backup',
  'storage',
  'containers',
  'networking',
  'migration',
  'security',
  'compliance',
  'operations',
  'account',
  'ai-agents',
] as const;

export type DocTag = (typeof DOC_TAGS)[number];

/**
 * Tag identifier -> translation key, plus the English text used as `t`'s fallback.
 *
 * The literal key strings matter beyond the lookup. `check-dead-translation-keys.ts` counts
 * any dotted three-plus-segment string in a source file as a reference, and writing them out
 * here is the ONLY thing keeping the fourteen `documentation.tags.*` keys off its dead list:
 * the lookup itself is by variable, so the t()-call scan cannot see them. Verified, not
 * assumed: the gate reports all 6,943 English keys reachable with this map in place.
 */
const TAG_KEYS: Record<DocTag, { key: string; en: string }> = {
  'getting-started': { key: 'documentation.tags.gettingStarted', en: 'Getting Started' },
  cli: { key: 'documentation.tags.cli', en: 'CLI' },
  repositories: { key: 'documentation.tags.repositories', en: 'Repositories' },
  forking: { key: 'documentation.tags.forking', en: 'Forking' },
  backup: { key: 'documentation.tags.backup', en: 'Backup' },
  storage: { key: 'documentation.tags.storage', en: 'Storage' },
  containers: { key: 'documentation.tags.containers', en: 'Containers' },
  networking: { key: 'documentation.tags.networking', en: 'Networking' },
  migration: { key: 'documentation.tags.migration', en: 'Migration' },
  security: { key: 'documentation.tags.security', en: 'Security' },
  compliance: { key: 'documentation.tags.compliance', en: 'Compliance' },
  operations: { key: 'documentation.tags.operations', en: 'Operations' },
  account: { key: 'documentation.tags.account', en: 'Accounts' },
  'ai-agents': { key: 'documentation.tags.aiAgents', en: 'AI Agents' },
};

/**
 * Build a tag label resolver from a translator.
 *
 * The English text is passed as `t`'s fallback argument rather than left to the
 * key-not-found path, which returns the raw key AND logs a warning: a browse page that
 * renders `documentation.tags.backup` on a filter button is worse than one that renders
 * `Backup` in English while a locale catches up.
 */
export function makeTagLabel(t: (key: string, fallback?: string) => string) {
  return (tag: string): string => {
    // Typed as possibly-undefined on purpose. `tag` arrives as a plain string, so the
    // cast is a claim rather than a guarantee and an unknown tag really does miss the
    // table. Without the annotation TypeScript reads the lookup as total and calls the
    // guard below "always truthy" -- deleting it to satisfy that would crash on exactly
    // the input the guard exists for.
    const entry = (TAG_KEYS as Partial<Record<string, (typeof TAG_KEYS)[DocTag]>>)[tag];
    return entry ? t(entry.key, entry.en) : tag;
  };
}

/** Tags actually present in a set of docs, in DOC_TAGS order, with their counts. */
export function tagCounts<T extends { data: { tags?: readonly string[] } }>(
  docs: T[]
): { tag: DocTag; count: number }[] {
  return DOC_TAGS.map((tag) => ({
    tag,
    count: docs.filter((doc) => doc.data.tags?.includes(tag)).length,
  })).filter((entry) => entry.count > 0);
}

/**
 * The docs SUBCATEGORY vocabulary, in ONE place, under the same English-everywhere rule
 * as CATEGORY_ORDER and DOC_TAGS above.
 *
 * `subcategory` is the third axis and it is PER-CATEGORY: where `category` is the format
 * and `tags` the topic, `subcategory` is the SHELF a document sits on inside its
 * category's sidebar group. It is single-valued on purpose (66 of 79 docs carry two
 * tags, so grouping the sidebar on tags would file one doc under two headings), and each
 * category has its own ordered shelf list because "Setup" means nothing inside Legal and
 * "Regulations" means nothing inside Guides.
 *
 * The values are identifiers, NOT display text, identical in all thirteen locales. An
 * identifier may appear under several categories when the concept genuinely repeats
 * (`ai-agents` shelves exist in Guides, Concepts and Reference); it is still ONE label
 * key. `content/config.ts` builds its `z.enum` from DOC_SUBCATEGORY_VALUES and checks
 * per-category legality against this table, so an illegal (category, subcategory) pair
 * fails the content build rather than silently rendering an unknown heading.
 */
export const DOC_SUBCATEGORY_VALUES = [
  'essentials',
  'advanced',
  'setup',
  'cli-tools',
  'workloads',
  'data-protection',
  'operations',
  'account',
  'ai-agents',
  'architecture',
  'platform',
  'commands',
  'resilience',
  'scaling',
  'development',
  'foundations',
  'regulations',
  'frameworks',
] as const;

export type DocSubcategory = (typeof DOC_SUBCATEGORY_VALUES)[number];

/**
 * Which shelves each category has, in display order. Typed against DocSubcategory so a
 * shelf added here without a VALUES entry (and therefore without schema legality and a
 * label) is a compile error, not a runtime fallback.
 */
export const DOC_SUBCATEGORIES: Record<DocCategory, readonly DocSubcategory[]> = {
  Tutorials: ['essentials', 'advanced'],
  Guides: [
    'setup',
    'cli-tools',
    'workloads',
    'data-protection',
    'operations',
    'account',
    'ai-agents',
  ],
  Concepts: ['architecture', 'platform', 'ai-agents'],
  Reference: ['commands', 'ai-agents', 'platform'],
  'Use Cases': ['resilience', 'scaling', 'development'],
  Legal: ['foundations', 'regulations', 'frameworks'],
};

/** The ordered shelf list for a category; empty for anything unknown. */
export function subcategoriesFor(category: string): readonly DocSubcategory[] {
  // Typed as possibly-undefined on purpose, exactly as makeTagLabel below: `category`
  // arrives as a plain string, so the cast is a claim rather than a guarantee and an
  // unknown category really does miss the record.
  const shelves = (
    DOC_SUBCATEGORIES as Partial<Record<string, readonly DocSubcategory[]>>
  )[category];
  return shelves ?? [];
}

/**
 * Subcategory identifier -> translation key, plus the English fallback text, written as
 * literals for the same reason TAG_KEYS above spells its keys out: the dead-key scanner
 * counts these strings as references, and the lookup itself is by variable.
 */
const SUBCATEGORY_KEYS: Record<DocSubcategory, { key: string; en: string }> = {
  essentials: { key: 'documentation.subcategories.essentials', en: 'Essentials' },
  advanced: { key: 'documentation.subcategories.advanced', en: 'Advanced' },
  setup: { key: 'documentation.subcategories.setup', en: 'Setup' },
  'cli-tools': { key: 'documentation.subcategories.cliTools', en: 'CLI & Tools' },
  workloads: { key: 'documentation.subcategories.workloads', en: 'Apps & Services' },
  'data-protection': { key: 'documentation.subcategories.dataProtection', en: 'Backup & Migration' },
  operations: { key: 'documentation.subcategories.operations', en: 'Operations' },
  account: { key: 'documentation.subcategories.account', en: 'Account & Licensing' },
  'ai-agents': { key: 'documentation.subcategories.aiAgents', en: 'AI Agents' },
  architecture: { key: 'documentation.subcategories.architecture', en: 'Architecture' },
  platform: { key: 'documentation.subcategories.platform', en: 'Platform' },
  commands: { key: 'documentation.subcategories.commands', en: 'Commands' },
  resilience: { key: 'documentation.subcategories.resilience', en: 'Resilience & Recovery' },
  scaling: { key: 'documentation.subcategories.scaling', en: 'Scaling' },
  development: { key: 'documentation.subcategories.development', en: 'Development' },
  foundations: { key: 'documentation.subcategories.foundations', en: 'Foundations' },
  regulations: { key: 'documentation.subcategories.regulations', en: 'Regulations' },
  frameworks: { key: 'documentation.subcategories.frameworks', en: 'Standards & Frameworks' },
};

/**
 * Build a subcategory label resolver from a translator, English text as the fallback
 * argument for the same reason makeTagLabel passes one: a raw key on a sidebar heading
 * is worse than English while a locale catches up.
 */
export function makeSubcategoryLabel(t: (key: string, fallback?: string) => string) {
  return (subcategory: string): string => {
    const entry = (
      SUBCATEGORY_KEYS as Partial<Record<string, (typeof SUBCATEGORY_KEYS)[DocSubcategory]>>
    )[subcategory];
    return entry ? t(entry.key, entry.en) : subcategory;
  };
}

/**
 * One glyph per category, as a bare SVG path on a 24x24 grid.
 *
 * One consumer today: the browse card renders it inline as the category chip's icon,
 * where it inherits colour from CSS. It is path DATA rather than a component because a
 * second consumer used to bake it into standalone files; that generator is gone, replaced
 * by hand-authored thumbnails under public/img/docs-thumbs/. Kept stroke-only so any
 * future consumer can colour it however its context allows.
 */
export const CATEGORY_GLYPHS: Record<DocCategory, string> = {
  // A play triangle: something you follow along with.
  Tutorials: 'M9 6.5 17.5 12 9 17.5Z',
  // An open book.
  Guides: 'M3 5.5h6a2 2 0 0 1 2 2v11a2 2 0 0 0-2-2H3ZM21 5.5h-6a2 2 0 0 0-2 2v11a2 2 0 0 1 2-2h6Z',
  // Connected nodes: an idea and what it relates to.
  Concepts: 'M12 4.5v5m0 5v5M7.5 12h-3m15 0h-3M12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5Z',
  // A list of entries.
  Reference: 'M4 7h16M4 12h16M4 17h10',
  // Stacked layers: a scenario built out of parts.
  'Use Cases': 'm12 4 8 4-8 4-8-4Zm8 8-8 4-8-4m16 4-8 4-8-4',
  // A shield.
  Legal: 'M12 4l7 2.5v5c0 4-3 7-7 8.5-4-1.5-7-4.5-7-8.5v-5Z',
};
