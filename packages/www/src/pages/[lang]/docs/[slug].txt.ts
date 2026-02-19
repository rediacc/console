import { getCollection } from 'astro:content';
import type { APIRoute, GetStaticPaths } from 'astro';
import type { Language } from '../../../i18n/types';
import { DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES } from '../../../i18n/language-utils';
import { getBaseSlug } from '../../../utils/slug';

// Docs excluded from LLM text endpoints (cloud-specific or auto-generated references)
const EXCLUDED_BASE_SLUGS = ['cli-application', 'web-application'] as const;
const isExcludedBaseSlug = (slug: string) =>
  EXCLUDED_BASE_SLUGS.includes(slug as (typeof EXCLUDED_BASE_SLUGS)[number]);

export const getStaticPaths: GetStaticPaths = async () => {
  const docs = await getCollection('docs', (d) => !isExcludedBaseSlug(getBaseSlug(d.slug)));

  return docs
    .filter((doc) => SUPPORTED_LANGUAGES.includes((doc.data.language || DEFAULT_LANGUAGE) as Language))
    .map((doc) => ({
      params: {
        lang: (doc.data.language || DEFAULT_LANGUAGE) as Language,
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
