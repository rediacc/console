import { defineCollection, z } from 'astro:content';
import { LANGUAGES } from '../i18n/types';
import { DOC_SUBCATEGORY_VALUES, DOC_TAGS, subcategoriesFor } from '../utils/docs-categories';

const blogCollection = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    description: z.string(),
    author: z.string(),
    publishedDate: z.date(),
    updatedDate: z.date().optional(),
    category: z.enum(['tutorial', 'announcement', 'guide', 'case-study', 'other']),
    tags: z.array(z.string()),
    featured: z.boolean().default(false),
    image: z.string().optional(),
    language: z.enum(LANGUAGES).default('en'),
    sourceHash: z.string().optional(),
  }),
});

const docsCollection = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    description: z.string(),
    // The English category vocabulary, in EVERY locale. The category is an
    // identifier (tab routing, sorting, key lookup), not display text; the
    // translated label lives under documentation.categories.* in the locale
    // catalogs. A translated value here once shipped a seventh docs tab whose
    // label appeared twice in Arabic.
    category: z.enum(['Tutorials', 'Guides', 'Concepts', 'Reference', 'Use Cases', 'Legal']),
    // The English TAG vocabulary, in EVERY locale, for the same reason `category` is: a
    // tag is an identifier the browse filter matches on, not display text. The single
    // source is `utils/docs-categories.ts`; the translated label lives under
    // documentation.tags.* in the locale catalogs.
    tags: z.array(z.enum(DOC_TAGS)).default([]),
    // The per-category SHELF, single-valued on purpose (66 of 79 docs carry two tags,
    // so grouping the sidebar on tags would file one doc under two headings). The
    // vocabulary and each category's shelf list live in `utils/docs-categories.ts`;
    // the superRefine below is what makes an illegal (category, subcategory) pair
    // fail the content build instead of silently rendering an unknown heading.
    subcategory: z.enum(DOC_SUBCATEGORY_VALUES).optional(),
    order: z.number().optional(),
    toc: z.boolean().default(true),
    // Render the page as a printable cheat-sheet card grid instead of a
    // regular article (see components/CheatSheetGrid.astro).
    cardGrid: z.boolean().default(false),
    language: z.enum(LANGUAGES).default('en'),
    sourceHash: z.string().optional(),
  }).superRefine((doc, ctx) => {
    if (doc.subcategory && !subcategoriesFor(doc.category).includes(doc.subcategory)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['subcategory'],
        message: `subcategory '${doc.subcategory}' is not on the '${doc.category}' shelf list; see DOC_SUBCATEGORIES in utils/docs-categories.ts`,
      });
    }
  }),
});

export const collections = {
  blog: blogCollection,
  docs: docsCollection,
};
