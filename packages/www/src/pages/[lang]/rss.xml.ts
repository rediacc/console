import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { SITE_URL } from '../../config/constants';
import { SUPPORTED_LANGUAGES, getLanguageName } from '../../i18n/language-utils';
import { getBaseSlug } from '../../utils/slug';
import type { Language } from '../../i18n/types';
import type { APIContext } from 'astro';

export function getStaticPaths() {
  return SUPPORTED_LANGUAGES.map((lang) => ({ params: { lang } }));
}

export async function GET(context: APIContext) {
  const { lang } = context.params;
  const blog = await getCollection('blog');

  const languagePosts = blog
    .filter((post) => post.data.language === lang)
    .sort((a, b) => b.data.publishedDate.valueOf() - a.data.publishedDate.valueOf());

  return rss({
    title: `Rediacc Blog - ${getLanguageName(lang as Language)}`,
    description: 'Infrastructure automation, disaster recovery, and system portability insights',
    site: context.site ?? SITE_URL,
    items: languagePosts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      link: `/${lang}/blog/${getBaseSlug(post.slug)}`,
      pubDate: post.data.publishedDate,
      author: post.data.author,
      categories: [...post.data.tags, post.data.category],
    })),
    customData: `<language>${lang}</language>`,
    stylesheet: false,
  });
}
