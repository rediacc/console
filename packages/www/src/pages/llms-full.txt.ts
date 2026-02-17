import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';

// Docs excluded from LLM context (cloud-specific or auto-generated references)
const EXCLUDED_SLUGS = ['en/cli-application', 'en/web-application'];

export const GET: APIRoute = async () => {
  const docs = await getCollection(
    'docs',
    (d) => d.data.language === 'en' && !EXCLUDED_SLUGS.includes(d.slug)
  );
  docs.sort((a, b) => (a.data.order ?? 99) - (b.data.order ?? 99));

  let content = '# Rediacc - Full Documentation\n\n';

  for (const doc of docs) {
    content += `## ${doc.data.title}\n\n${doc.body}\n\n---\n\n`;
  }

  return new Response(content, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
