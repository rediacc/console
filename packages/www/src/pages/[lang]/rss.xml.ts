import { getCollection } from 'astro:content';
import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { SITE_URL } from '../../config/constants';
import { getLanguageName, SUPPORTED_LANGUAGES } from '../../i18n/language-utils';
import type { Language } from '../../i18n/types';
import { getBaseSlug } from '../../utils/slug';

export function getStaticPaths() {
  return SUPPORTED_LANGUAGES.map((lang) => ({ params: { lang } }));
}

export async function GET(context: APIContext) {
  const { lang } = context.params;
  const blog = await getCollection('blog');

  const languagePosts = blog
    .filter((post) => post.data.language === lang)
    // Same-day posts fall back to the entry id, so the order never depends on the content loader's iteration order.
    .sort((a, b) => b.data.publishedDate.valueOf() - a.data.publishedDate.valueOf() || a.id.localeCompare(b.id));

  return rss({
    title: `Rediacc Blog - ${getLanguageName(lang as Language)}`,
    description: 'Infrastructure automation, disaster recovery, and system portability insights',
    site: context.site ?? SITE_URL,
    items: languagePosts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      link: `/${lang}/blog/${getBaseSlug(post.id)}?utm_source=rss&utm_medium=feed&utm_campaign=blog`,
      pubDate: post.data.publishedDate,
      author: post.data.author,
      categories: [...post.data.tags, post.data.category],
    })),
    customData: `<language>${lang}</language>`,
    stylesheet: false,
  });
}
