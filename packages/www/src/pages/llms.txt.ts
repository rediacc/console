import { getCollection } from 'astro:content';
import type { APIRoute } from 'astro';
import { SITE_URL } from '../config/constants';
import { getBaseSlug } from '../utils/slug';

// Docs excluded from the LLM index (auto-generated references)
const EXCLUDED_SLUGS = [
  'en/cli-application',
  'en/cli-application-cloud',
  'en/web-application',
] as const;

// Category display order (matches DocsTopTabs / DocsSidebar)
const CATEGORY_ORDER: Record<string, number> = {
  Guides: 0,
  Concepts: 1,
  Reference: 2,
  'Use Cases': 3,
};

const ORDER_FALLBACK = 99;

export const GET: APIRoute = async () => {
  const docs = await getCollection(
    'docs',
    (d) => d.data.language === 'en' && !EXCLUDED_SLUGS.includes(d.slug)
  );

  // Group by category
  const byCategory = new Map<string, typeof docs>();
  for (const doc of docs) {
    const cat = doc.data.category;
    if (!byCategory.has(cat)) byCategory.set(cat, []);
    byCategory.get(cat)!.push(doc);
  }

  // Sort categories
  const sortedCategories = [...byCategory.keys()].sort((a, b) => {
    const pa = CATEGORY_ORDER[a] ?? ORDER_FALLBACK;
    const pb = CATEGORY_ORDER[b] ?? ORDER_FALLBACK;
    if (pa !== pb) return pa - pb;
    return a.localeCompare(b);
  });

  // Sort docs within each category by order
  for (const [, catDocs] of byCategory) {
    catDocs.sort((a, b) => (a.data.order ?? ORDER_FALLBACK) - (b.data.order ?? ORDER_FALLBACK));
  }

  // Build content
  let content = `# Rediacc

> Self-hosted infrastructure platform with encrypted repositories, container isolation, and automated disaster recovery.

Rediacc enables you to deploy and manage isolated, encrypted application environments on your own servers. Each repository gets its own Docker daemon, network namespace, and encrypted storage.

`;

  for (const category of sortedCategories) {
    const catDocs = byCategory.get(category)!;
    content += `## ${category}\n\n`;
    for (const doc of catDocs) {
      const slug = getBaseSlug(doc.slug);
      content += `- [${doc.data.title}](${SITE_URL}/en/docs/${slug}.txt): ${doc.data.description}\n`;
    }
    content += '\n';
  }

  content += `## Optional\n\n- [Full Documentation](${SITE_URL}/llms-full.txt): Complete documentation in a single file\n`;

  return new Response(content, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
