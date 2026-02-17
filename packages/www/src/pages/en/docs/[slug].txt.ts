import type { APIRoute, GetStaticPaths } from 'astro';
import { getCollection } from 'astro:content';

// Docs excluded from LLM text endpoints (cloud-specific or auto-generated references)
const EXCLUDED_SLUGS = ['en/cli-application', 'en/web-application'];

export const getStaticPaths: GetStaticPaths = async () => {
  const docs = await getCollection(
    'docs',
    (d) => d.data.language === 'en' && !EXCLUDED_SLUGS.includes(d.slug)
  );

  return docs.map((doc) => {
    const baseSlug = doc.slug.split('/').pop()!;
    return {
      params: { slug: baseSlug },
      props: { doc },
    };
  });
};

export const GET: APIRoute = async ({ props }) => {
  const { doc } = props as { doc: { data: { title: string }; body: string } };

  const content = doc.body;

  return new Response(content, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
