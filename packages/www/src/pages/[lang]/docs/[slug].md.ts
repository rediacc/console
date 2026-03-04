import { getCollection } from 'astro:content';
import { SUPPORTED_LANGUAGES } from '../../../i18n/language-utils';
import { getBaseSlug } from '../../../utils/slug';
import type { APIRoute, GetStaticPaths } from 'astro';

export const getStaticPaths: GetStaticPaths = async () => {
  const docs = await getCollection('docs');

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
    headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
  });
};

