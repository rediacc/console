import { getCollection } from 'astro:content';
import type { APIRoute } from 'astro';
import JSZip from 'jszip';
import { getBaseSlug } from '../utils/slug';

export const GET: APIRoute = async () => {
  const docs = await getCollection('docs', (d) => d.data.language === 'en');

  const zip = new JSZip();

  for (const doc of docs) {
    const slug = getBaseSlug(doc.slug);
    const frontmatter = [
      '---',
      `title: ${doc.data.title}`,
      `description: ${doc.data.description}`,
      `category: ${doc.data.category}`,
      `order: ${doc.data.order}`,
      '---',
    ].join('\n');

    zip.file(`${slug}.md`, `${frontmatter}\n\n${doc.body}`);
  }

  const buffer = await zip.generateAsync({ type: 'uint8array' });

  return new Response(buffer, {
    headers: {
      'Content-Type': 'application/zip',
      'Content-Disposition': 'attachment; filename="docs-markdown.zip"',
    },
  });
};
