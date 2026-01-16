import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { SUPPORTED_LANGUAGES } from '../../i18n/language-utils';
import type { Language } from '../../i18n/types';
import type { APIContext } from 'astro';

export function getStaticPaths() {
  return SUPPORTED_LANGUAGES.map((lang) => ({
    params: { lang },
  }));
}

export async function GET(context: APIContext) {
  const { lang } = context.params;
  const blog = await getCollection('blog');

  // Filter posts for the specific language
  const languagePosts = blog
    .filter((post) => post.data.language === lang)
    .sort((a, b) => b.data.publishedDate.valueOf() - a.data.publishedDate.valueOf());

  const languageNames: Record<Language, string> = {
    en: 'English',
    de: 'Deutsch',
    es: 'Español',
    fr: 'Français',
    ja: '日本語',
    ar: 'العربية',
    ru: 'Русский',
    tr: 'Türkçe',
    zh: '中文',
  };

  return rss({
    title: `Rediacc Blog - ${languageNames[lang as Language]}`,
    description: 'Infrastructure automation, disaster recovery, and system portability insights',
    site: context.site ?? 'https://www.rediacc.com',
    items: languagePosts.map((post) => {
      const slug = post.slug.split('/').pop() ?? post.slug;
      return {
        title: post.data.title,
        description: post.data.description,
        link: `/${lang}/blog/${slug}`,
        pubDate: post.data.publishedDate,
        author: post.data.author,
        categories: [...post.data.tags, post.data.category],
      };
    }),
    customData: `<language>${lang}</language>`,
    stylesheet: false,
  });
}
