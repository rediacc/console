import { defineCollection, z } from 'astro:content';
import { LANGUAGES } from '../i18n/types';

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
  }),
});

const docsCollection = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    description: z.string(),
    category: z.string(),
    order: z.number().optional(),
    toc: z.boolean().default(true),
    language: z.enum(LANGUAGES).default('en'),
  }),
});

export const collections = {
  blog: blogCollection,
  docs: docsCollection,
};
