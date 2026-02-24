import { getCollection } from 'astro:content';
import { SUPPORTED_LANGUAGES } from '../../../i18n/language-utils';
import { getBaseSlug } from '../../../utils/slug';
import type { APIRoute, GetStaticPaths } from 'astro';

// Docs excluded from LLM text endpoints (cloud-specific or auto-generated references)
const EXCLUDED_BASE_SLUGS = [
  'cli-application',
  'cli-application-cloud',
  'web-application',
] as const;
const isExcludedBaseSlug = (slug: string) =>
  EXCLUDED_BASE_SLUGS.includes(slug as (typeof EXCLUDED_BASE_SLUGS)[number]);

export const getStaticPaths: GetStaticPaths = async () => {
  const docs = await getCollection('docs', (d) => !isExcludedBaseSlug(getBaseSlug(d.slug)));

  return docs
    .filter((doc) => SUPPORTED_LANGUAGES.includes(doc.data.language))
    .map((doc) => ({
      params: {
        lang: doc.data.language,
        slug: getBaseSlug(doc.slug),
      },
      props: { doc },
    }));
};

export const GET: APIRoute = ({ props }) => {
  const { doc } = props as { doc: { body: string } };
  return new Response(doc.body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
