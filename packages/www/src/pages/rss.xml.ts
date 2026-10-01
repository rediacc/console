import { getCollection } from 'astro:content';
import rss from '@astrojs/rss';
import type { APIContext } from 'astro';
import { SITE_URL } from '../config/constants';
import { getBaseSlug } from '../utils/slug';

export async function GET(context: APIContext) {
  const blog = await getCollection('blog');

  // Filter for English posts only for the main RSS feed
  const englishPosts = blog
    .filter((post) => post.data.language === 'en')
    // Same-day posts fall back to the entry id, so the order never depends on the content loader's iteration order.
    .sort(
      (a, b) =>
        b.data.publishedDate.valueOf() - a.data.publishedDate.valueOf() || a.id.localeCompare(b.id)
    );

  return rss({
    title: 'Rediacc Blog',
    description: 'Infrastructure automation, disaster recovery, and system portability insights',
    site: context.site ?? SITE_URL,
    items: englishPosts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      link: `/en/blog/${getBaseSlug(post.id)}?utm_source=rss&utm_medium=feed&utm_campaign=blog`,
      pubDate: post.data.publishedDate,
      author: post.data.author,
      categories: [...post.data.tags, post.data.category],
    })),
    customData: '<language>en</language>',
    stylesheet: false,
  });
}
