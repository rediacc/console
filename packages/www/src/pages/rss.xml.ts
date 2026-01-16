import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import type { APIContext } from 'astro';

export async function GET(context: APIContext) {
  const blog = await getCollection('blog');

  // Filter for English posts only for the main RSS feed
  const englishPosts = blog
    .filter((post) => post.data.language === 'en')
    .sort((a, b) => b.data.publishedDate.valueOf() - a.data.publishedDate.valueOf());

  return rss({
    title: 'Rediacc Blog',
    description: 'Infrastructure automation, disaster recovery, and system portability insights',
    site: context.site ?? 'https://www.rediacc.com',
    items: englishPosts.map((post) => {
      const slug = post.slug.split('/').pop() ?? post.slug;
      return {
        title: post.data.title,
        description: post.data.description,
        link: `/en/blog/${slug}`,
        pubDate: post.data.publishedDate,
        author: post.data.author,
        categories: [...post.data.tags, post.data.category],
      };
    }),
    customData: '<language>en</language>',
    stylesheet: false,
  });
}
