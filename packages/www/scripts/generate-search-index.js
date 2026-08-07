import fs from 'node:fs';
import matter from 'gray-matter';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.join(__dirname, '..');

/** Locale an index entry belongs to when it carries none (the flat, pre-i18n layout). */
const DEFAULT_LANG = 'en';

/**
 * The first of `value` / `fallback` that actually has content.
 *
 * Deliberately NOT `??`: a frontmatter field that is present but empty
 * (`description: ""`) means "nothing here", so it has to fall back exactly like
 * an absent one, and a stripped markdown section body is routinely `''`.
 *
 * @param {unknown} value
 * @param {string} fallback
 * @returns {unknown}
 */
function withContent(value, fallback) {
  return value === undefined || value === null || value === '' ? fallback : value;
}

/**
 * Generate searchable index from en.json and markdown collections (blog, docs)
 * Recursively extracts all text content and auto-categorizes it
 */

function generateSearchIndex() {
  try {
    const searchIndex = [];
    let idCounter = 0;

    // Translations are deliberately NOT indexed: indexing them buried the blog
    // and docs hits under hundreds of UI-string matches.

    // Part 2: Index blog posts
    console.log('📝 Indexing blog posts...');
    indexCollectionType(
      searchIndex,
      idCounter,
      path.join(projectRoot, 'src/content/blog'),
      'Blog',
      'blog'
    );
    idCounter = searchIndex.length;

    // Part 3: Index documentation
    console.log('📚 Indexing documentation...');
    indexCollectionType(
      searchIndex,
      idCounter,
      path.join(projectRoot, 'src/content/docs'),
      'Documentation',
      'docs'
    );

    // Ensure public directory exists
    const publicDir = path.join(projectRoot, 'public');
    if (!fs.existsSync(publicDir)) {
      fs.mkdirSync(publicDir, { recursive: true });
    }

    // Group entries by language and write one JSON per locale. The runtime
    // fetches /search-index-<lang>.json so visitors only download their own
    // locale (~10x smaller than the combined file). search-index.json is kept
    // as a byte-identical copy of the English file for backward compat.
    const byLang = new Map();
    for (const entry of searchIndex) {
      const lang = entry.language ?? DEFAULT_LANG;
      if (!byLang.has(lang)) byLang.set(lang, []);
      byLang.get(lang).push(entry);
    }

    // Stale per-locale files left over from a previous generation would
    // pollute git status and confuse the freshness check. Sweep before write.
    for (const file of fs.readdirSync(publicDir)) {
      if (/^search-index(-[a-z]{2})?\.json$/.test(file)) {
        fs.unlinkSync(path.join(publicDir, file));
      }
    }

    const langs = [...byLang.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
    for (const lang of langs) {
      const entries = byLang.get(lang);
      const outPath = path.join(publicDir, `search-index-${lang}.json`);
      fs.writeFileSync(outPath, `${JSON.stringify(entries, null, 2)}\n`);
      console.log(`  → ${path.relative(projectRoot, outPath)}: ${entries.length} items`);
    }

    // Backward-compat fallback: any consumer that hardcoded the legacy URL
    // gets English content rather than a 404.
    const enPath = path.join(publicDir, 'search-index-en.json');
    const fallbackPath = path.join(publicDir, 'search-index.json');
    if (fs.existsSync(enPath)) {
      fs.copyFileSync(enPath, fallbackPath);
    } else {
      // No English content was indexed (would happen only if src/content/docs/en/ vanished).
      // Write an empty array so the runtime fetch still succeeds.
      fs.writeFileSync(fallbackPath, '[]\n');
    }

    console.log(
      `✓ Search index generated: ${searchIndex.length} items across ${langs.length} locales`
    );
    return true;
  } catch (error) {
    console.error('✗ Failed to generate search index:', error.message);
    return false;
  }
}

/**
 * Index markdown files from a collection directory (supports language subdirectories)
 */
function indexCollectionType(searchIndex, startingId, collectionDir, category, urlPrefix) {
  try {
    if (!fs.existsSync(collectionDir)) {
      console.log(`  (${category} directory not found, skipping)`);
      return;
    }

    let idCounter = startingId;
    const langDirs = fs.readdirSync(collectionDir);
    let totalFiles = 0;

    // Check if this is a language-based structure (en/, es/, etc.) or flat structure
    const hasLanguageDirs = langDirs.some((dir) => {
      const fullPath = path.join(collectionDir, dir);
      return fs.statSync(fullPath).isDirectory() && /^[a-z]{2}$/.test(dir);
    });

    if (hasLanguageDirs) {
      // Language-based structure: blog/en/, blog/es/, etc.
      langDirs.forEach((langDir) => {
        const langPath = path.join(collectionDir, langDir);
        if (!fs.statSync(langPath).isDirectory()) return;
        if (!/^[a-z]{2}$/.test(langDir)) return; // Only process language directories

        const files = fs.readdirSync(langPath);
        files.forEach((file) => {
          if (!file.endsWith('.md') && !file.endsWith('.mdx')) return;

          totalFiles++;
          const filePath = path.join(langPath, file);
          const fileContent = fs.readFileSync(filePath, 'utf-8');
          const { data: frontmatter, content } = matter(fileContent);

          // Index frontmatter title
          if (frontmatter.title) {
            const slug = file.replace(/\.mdx?$/, '');
            searchIndex.push({
              id: `search-${idCounter++}`,
              content: frontmatter.title,
              excerpt: withContent(frontmatter.description, truncateExcerpt(content, 150)),
              category,
              page: `/${langDir}/${urlPrefix}/${slug}`,
              path: `${urlPrefix}.${slug}.title`,
              priority: 1,
              language: langDir,
            });
          }

          // Index frontmatter description
          if (frontmatter.description) {
            const slug = file.replace(/\.mdx?$/, '');
            searchIndex.push({
              id: `search-${idCounter++}`,
              content: frontmatter.description,
              excerpt: truncateExcerpt(frontmatter.description, 150),
              category,
              page: `/${langDir}/${urlPrefix}/${slug}`,
              path: `${urlPrefix}.${slug}.description`,
              priority: 2,
              language: langDir,
            });
          }

          // Index tags/keywords
          if (frontmatter.tags && Array.isArray(frontmatter.tags)) {
            const slug = file.replace(/\.mdx?$/, '');
            frontmatter.tags.forEach((tag) => {
              searchIndex.push({
                id: `search-${idCounter++}`,
                content: tag,
                excerpt: `Tag: ${tag}`,
                category,
                page: `/${langDir}/${urlPrefix}/${slug}`,
                path: `${urlPrefix}.${slug}.tags`,
                priority: 3,
                language: langDir,
              });
            });
          }

          // Walk the markdown body section by section (split on H2/H3).
          // Each section produces ONE index entry whose `body` is the full
          // stripped section text — that's what makes buried terms searchable.
          const slug = file.replace(/\.mdx?$/, '');
          const sections = splitIntoSections(content, withContent(frontmatter.title, slug));

          for (const section of sections) {
            const body = stripMarkdown(section.body);
            if (!section.heading && !body) continue;

            searchIndex.push({
              id: `search-${idCounter++}`,
              content: section.heading,
              body,
              excerpt: truncateExcerpt(withContent(body, section.heading), 150),
              category,
              page: `/${langDir}/${urlPrefix}/${slug}`,
              path: `${urlPrefix}.${slug}.content`,
              priority: 2,
              language: langDir,
            });
          }
        });
      });
    } else {
      // Flat structure (backward compatibility)
      const files = fs.readdirSync(collectionDir);
      files.forEach((file) => {
        if (!file.endsWith('.md') && !file.endsWith('.mdx')) return;

        totalFiles++;
        const filePath = path.join(collectionDir, file);
        const fileContent = fs.readFileSync(filePath, 'utf-8');
        const { data: frontmatter, content } = matter(fileContent);

        // Index frontmatter title
        if (frontmatter.title) {
          const slug = file.replace(/\.mdx?$/, '');
          searchIndex.push({
            id: `search-${idCounter++}`,
            content: frontmatter.title,
            excerpt: withContent(frontmatter.description, truncateExcerpt(content, 150)),
            category,
            page: `/${urlPrefix}/${slug}`,
            path: `${urlPrefix}.${slug}.title`,
            priority: 1,
          });
        }

        // Index other fields same as above...
        // (keep existing indexing logic)
      });
    }

    console.log(`  ✓ Indexed ${totalFiles} ${category.toLowerCase()} files`);
  } catch (error) {
    console.warn(`⚠ Warning: Could not index ${category}:`, error.message);
  }
}

/**
 * Truncate text to excerpt length with ellipsis
 */
function truncateExcerpt(text, maxLength = 150) {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength).trim() + '...';
}

/**
 * Split a markdown body into sections at H2 and H3 boundaries. Content that
 * appears before the first heading becomes an "intro" section labeled with
 * the doc's frontmatter title.
 */
function splitIntoSections(markdown, fallbackHeading) {
  const lines = markdown.split('\n');
  const sections = [];
  let currentHeading = fallbackHeading;
  let currentBody = [];
  let inFence = false;

  const flush = () => {
    const body = currentBody.join('\n').trim();
    if (currentHeading || body) {
      sections.push({ heading: currentHeading, body });
    }
  };

  for (const line of lines) {
    if (line.startsWith('```')) {
      inFence = !inFence;
      currentBody.push(line);
      continue;
    }
    // Drop MDX ESM imports/exports at the source so they never appear in any
    // section body — defence in depth alongside stripMarkdown's later pass.
    if (!inFence && /^\s*(?:import|export)\s+/.test(line)) {
      continue;
    }
    const headingMatch = !inFence && line.match(/^(#{2,3})\s+(.+?)\s*#*\s*$/);
    if (headingMatch) {
      flush();
      currentHeading = headingMatch[2].trim();
      currentBody = [];
    } else {
      currentBody.push(line);
    }
  }
  flush();

  return sections;
}

/**
 * Strip markdown syntax while preserving identifier text. Code-block contents
 * are kept (env vars and CLI snippets often live there); only the fences,
 * link/image syntax, and emphasis markers are removed.
 */
function stripMarkdown(text) {
  if (!text) return '';
  return (
    text
      .replaceAll(/<!--[\s\S]*?-->/g, ' ')
      // MDX: strip top-of-file ESM imports/exports so they do not pollute the
      // search index with module paths and identifiers.
      .replaceAll(/^\s*import\s+[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, ' ')
      .replaceAll(/^\s*export\s+(?:default\s+)?[\s\S]*?;?\s*$/gm, ' ')
      // MDX: strip JSX components (capitalised tag names) so component names
      // and prop values do not leak into search results.
      .replaceAll(/<[A-Z][A-Za-z0-9]*\b[^>]*\/>/g, ' ')
      .replaceAll(/<[A-Z][A-Za-z0-9]*\b[^>]*>[\s\S]*?<\/[A-Z][A-Za-z0-9]*>/g, ' ')
      .replaceAll(/^```.*$/gm, ' ')
      .replaceAll(/`([^`]+)`/g, '$1')
      .replaceAll(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replaceAll(/\[([^\]]+)\]\([^)]*\)/g, '$1')
      .replaceAll(/^\s*>\s?/gm, '')
      .replaceAll(/^\s*[-*+]\s+/gm, '')
      .replaceAll(/^\s*\d+\.\s+/gm, '')
      .replaceAll(/\*\*([^*\n]+)\*\*/g, '$1')
      .replaceAll(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '$1')
      .replaceAll(/~~([^~\n]+)~~/g, '$1')
      .replaceAll(/\s+/g, ' ')
      .trim()
  );
}

// Run generator
generateSearchIndex();
