import { getCollection } from 'astro:content';
import type { APIRoute } from 'astro';

// Docs excluded from LLM context (cloud-specific or auto-generated references)
const EXCLUDED_SLUGS = ['en/cli-application', 'en/web-application'] as const;

// Fallback sort order for docs without an explicit order (pushes them to end)
const ORDER_FALLBACK = 99;

export const GET: APIRoute = async () => {
  const docs = await getCollection(
    'docs',
    (d) => d.data.language === 'en' && !EXCLUDED_SLUGS.includes(d.slug)
  );
  docs.sort((a, b) => (a.data.order ?? ORDER_FALLBACK) - (b.data.order ?? ORDER_FALLBACK));

  let content = '# Rediacc - Full Documentation\n\n';

  for (const doc of docs) {
    content += `## ${doc.data.title}\n\n${doc.body}\n\n---\n\n`;
  }

  return new Response(content, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
