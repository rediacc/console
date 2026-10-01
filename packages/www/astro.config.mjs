/* global process */
// @ts-check
import { defineConfig } from 'astro/config';
import { execSync } from 'child_process';

// Version is injected by CI via APP_VERSION (resolved from git tags). Local dev shows 0.0.0-dev. No git-describe fallback — version resolution is the caller's job, not the build's.
const version = process.env.APP_VERSION || '0.0.0-dev';

// Astro 7 renders Markdown with Sätteri by default; the site's remark/rehype plugins need the unified processor from this package.
import { unified } from '@astrojs/markdown-remark';
import mdx from '@astrojs/mdx';
import react from '@astrojs/react';
import sitemap, { ChangeFreqEnum } from '@astrojs/sitemap';
import { WK_SITE_ORIGIN } from '../shared/src/config/well-known.generated.ts';
import jsonGeneratorIntegration from './src/integrations/json-generator.ts';
import routeManifestIntegration from './src/integrations/route-manifest-generator.ts';
import { rehypeStableHeadingIds } from './src/plugins/rehype-stable-heading-ids.mjs';
import { remarkDocsCliLinks } from './src/plugins/remark-docs-cli-links.ts';
import { remarkResolveTranslations } from './src/plugins/remark-resolve-translations.ts';
import { remarkTutorialEmbed } from './src/plugins/remark-tutorial-embed.ts';
import { remarkVideoEmbed } from './src/plugins/remark-video-embed.ts';

// Integration to generate search index before build. A failure fails the BUILD: the generator deletes the previous index files before writing, so swallowing its error ships a site with no search index while exiting 0.
const searchIndexIntegration = {
  name: 'search-index-generator',
  hooks: {
    'astro:build:start': () => {
      execSync('node scripts/generate-search-index.js', { stdio: 'inherit' });
    },
  },
};

// https://astro.build/config
export default defineConfig({
  site: process.env.PUBLIC_SITE_URL || WK_SITE_ORIGIN,
  trailingSlash: 'never',
  integrations: [
    react(),
    mdx(),
    sitemap({
      // Default values (will be overridden by serialize function)
      changefreq: 'weekly',
      priority: 0.7,
      lastmod: new Date(),

      // Internationalization support
      i18n: {
        defaultLocale: 'en',
        locales: {
          en: 'en',
          de: 'de-DE',
          es: 'es-ES',
          fr: 'fr-FR',
          ja: 'ja-JP',
          ar: 'ar',
          ru: 'ru-RU',
          tr: 'tr-TR',
          zh: 'zh-CN',
          et: 'et-EE',
          ko: 'ko-KR',
          pt: 'pt-PT',
          it: 'it-IT',
        },
      },

      // Optimize XML file size by excluding unused namespaces
      namespaces: {
        news: false, // Not a news site
        video: false, // No video content
        image: true, // Keep for images
        xhtml: true, // Keep for hreflang (i18n)
      },

      // Per-page customization for priority and changefreq
      serialize: (item) => {
        const url = item.url;

        // Homepage - highest priority
        if (url.match(/\/(en|de|es|fr|ja|ar|ru|tr|zh|et|ko|pt|it)\/?$/)) {
          item.priority = 1.0;
          item.changefreq = ChangeFreqEnum.WEEKLY;
        }
        // Root homepage
        else if (url === (process.env.PUBLIC_SITE_URL || WK_SITE_ORIGIN) + '/') {
          item.priority = 1.0;
          item.changefreq = ChangeFreqEnum.WEEKLY;
        }
        // Solutions pages - high priority
        else if (url.includes('/solutions/')) {
          item.priority = 0.9;
          item.changefreq = ChangeFreqEnum.MONTHLY;
        }
        // Disaster recovery page - high priority
        else if (url.includes('/disaster-recovery')) {
          item.priority = 0.8;
          item.changefreq = ChangeFreqEnum.MONTHLY;
        }
        // Blog listing pages - high priority, frequent updates
        else if (url.match(/\/blog\/?$/)) {
          item.priority = 0.8;
          item.changefreq = ChangeFreqEnum.DAILY;
        }
        // Docs listing pages - high priority
        else if (url.match(/\/docs\/?$/)) {
          item.priority = 0.8;
          item.changefreq = ChangeFreqEnum.WEEKLY;
        }
        // Individual blog posts - medium-high priority, frequent updates
        else if (url.includes('/blog/') && !url.endsWith('/blog/')) {
          item.priority = 0.7;
          item.changefreq = ChangeFreqEnum.DAILY;
        }
        // Individual doc pages - medium-high priority
        else if (url.includes('/docs/') && !url.endsWith('/docs/')) {
          item.priority = 0.7;
          item.changefreq = ChangeFreqEnum.WEEKLY;
        }
        // Company page - medium-high priority
        else if (url.includes('/company')) {
          item.priority = 0.7;
          item.changefreq = ChangeFreqEnum.MONTHLY;
        }
        // Contact page - medium priority
        else if (url.includes('/contact')) {
          item.priority = 0.6;
          item.changefreq = ChangeFreqEnum.MONTHLY;
        }
        // Other pages - lower priority
        else {
          item.priority = 0.5;
          item.changefreq = ChangeFreqEnum.MONTHLY;
        }

        return item;
      },
    }),
    searchIndexIntegration,
    jsonGeneratorIntegration(),
    routeManifestIntegration(),
  ],
  output: 'static',
  // Astro 7 defaults to 'jsx', which drops whitespace that spans a line break between inline elements: a 'jsx' build of this site rendered the skip links as "Skip to main contentSkip to navigation" and the docs breadcrumb as "Home/". true keeps the HTML-collapsing behavior the templates were written against.
  compressHTML: true,
  redirects: {
    '/en/team': '/en/company',
    '/de/team': '/de/company',
    '/es/team': '/es/company',
    '/fr/team': '/fr/company',
    '/ja/team': '/ja/company',
    '/ar/team': '/ar/company',
    '/ru/team': '/ru/company',
    '/tr/team': '/tr/company',
    '/zh/team': '/zh/company',
    '/et/team': '/et/company',
    '/ko/team': '/ko/company',
    '/pt/team': '/pt/company',
    '/it/team': '/it/company',

    /* The `/[lang]/solutions` index route was deleted and the constellation it
       existed to hold moved onto the homepage, under `id="solutions"` (see
       SPHomePage.astro). These keep the thirteen published URLs landing on the
       figure instead of on a 404. The root `/solutions` is NOT in this map: a
       page file, pages/solutions.astro, already claims that path and issues the
       301 itself. */
    '/en/solutions': '/en#solutions',
    '/de/solutions': '/de#solutions',
    '/es/solutions': '/es#solutions',
    '/fr/solutions': '/fr#solutions',
    '/ja/solutions': '/ja#solutions',
    '/ar/solutions': '/ar#solutions',
    '/ru/solutions': '/ru#solutions',
    '/tr/solutions': '/tr#solutions',
    '/zh/solutions': '/zh#solutions',
    '/et/solutions': '/et#solutions',
    '/ko/solutions': '/ko#solutions',
    '/pt/solutions': '/pt#solutions',
    '/it/solutions': '/it#solutions',
  },
  build: {
    assets: 'assets',
  },
  vite: {
    define: {
      __APP_VERSION__: JSON.stringify(version),
    },
  },
  markdown: {
    processor: unified({
      remarkPlugins: [
        remarkVideoEmbed,
        remarkTutorialEmbed,
        remarkDocsCliLinks,
        remarkResolveTranslations,
      ],
      // Runs BEFORE Astro's default rehypeHeadingIds, which respects an existing id, so these ids win and also land in file.data.astro.headings.
      rehypePlugins: [rehypeStableHeadingIds],
    }),
  },
});
