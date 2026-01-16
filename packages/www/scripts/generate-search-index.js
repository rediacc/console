import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import matter from 'gray-matter';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.join(__dirname, '..');

/**
 * Generate searchable index from en.json and markdown collections (blog, docs)
 * Recursively extracts all text content and auto-categorizes it
 */

function generateSearchIndex() {
  try {
    const searchIndex = [];
    let idCounter = 0;

    // Part 1: Index translations from en.json - DISABLED
    // (Only indexing blog and docs for better search results)
    // console.log('📄 Indexing translations...');
    // indexTranslations(searchIndex, idCounter);
    // idCounter = searchIndex.length;

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

    // Write search index
    const outputPath = path.join(projectRoot, 'public/search-index.json');
    fs.writeFileSync(outputPath, JSON.stringify(searchIndex, null, 2));

    console.log(`✓ Search index generated: ${searchIndex.length} items`);
    return true;
  } catch (error) {
    console.error('✗ Failed to generate search index:', error.message);
    return false;
  }
}

/**
 * Index translations from en.json
 */
function indexTranslations(searchIndex, startingId) {
  try {
    const translationsPath = path.join(
      projectRoot,
      'src/i18n/translations/en.json'
    );
    const translations = JSON.parse(fs.readFileSync(translationsPath, 'utf-8'));

    let idCounter = startingId;

    function traverse(obj, keyPath = '', parentKey = 'root') {
      if (
        typeof obj === 'string' &&
        obj.trim().length > 0 &&
        !keyPath.includes('meta')
      ) {
        const id = `search-${idCounter++}`;
        const category = categorizeByPath(keyPath);
        const page = detectPage(keyPath);
        const priority = calculatePriority(keyPath);

        const cleanContent = obj.replace(/\{\{.*?\}\}/g, '').trim();

        if (cleanContent.length > 0) {
          searchIndex.push({
            id,
            content: cleanContent,
            excerpt: truncateExcerpt(cleanContent, 150),
            category,
            page,
            path: keyPath,
            priority,
          });
        }
      } else if (Array.isArray(obj)) {
        obj.forEach((item, index) => {
          const newKeyPath = keyPath ? `${keyPath}[${index}]` : `[${index}]`;
          traverse(item, newKeyPath, parentKey);
        });
      } else if (obj !== null && typeof obj === 'object') {
        Object.entries(obj).forEach(([key, value]) => {
          const newKeyPath = keyPath ? `${keyPath}.${key}` : key;
          traverse(value, newKeyPath, key);
        });
      }
    }

    traverse(translations);
  } catch (error) {
    console.warn(
      '⚠ Warning: Could not index translations:',
      error.message
    );
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
          if (!file.endsWith('.md')) return;

          totalFiles++;
          const filePath = path.join(langPath, file);
          const fileContent = fs.readFileSync(filePath, 'utf-8');
          const { data: frontmatter, content } = matter(fileContent);

          // Index frontmatter title
          if (frontmatter.title) {
            const slug = file.replace(/\.md$/, '');
            searchIndex.push({
              id: `search-${idCounter++}`,
              content: frontmatter.title,
              excerpt: frontmatter.description || truncateExcerpt(content, 150),
              category: category,
              page: `/${langDir}/${urlPrefix}/${slug}`,
              path: `${urlPrefix}.${slug}.title`,
              priority: 1,
              language: langDir,
            });
          }

          // Index frontmatter description
          if (frontmatter.description) {
            const slug = file.replace(/\.md$/, '');
            searchIndex.push({
              id: `search-${idCounter++}`,
              content: frontmatter.description,
              excerpt: truncateExcerpt(frontmatter.description, 150),
              category: category,
              page: `/${langDir}/${urlPrefix}/${slug}`,
              path: `${urlPrefix}.${slug}.description`,
              priority: 2,
              language: langDir,
            });
          }

          // Index tags/keywords
          if (frontmatter.tags && Array.isArray(frontmatter.tags)) {
            const slug = file.replace(/\.md$/, '');
            frontmatter.tags.forEach((tag) => {
              searchIndex.push({
                id: `search-${idCounter++}`,
                content: tag,
                excerpt: `Tag: ${tag}`,
                category: category,
                page: `/${langDir}/${urlPrefix}/${slug}`,
                path: `${urlPrefix}.${slug}.tags`,
                priority: 3,
                language: langDir,
              });
            });
          }

          // Extract and index headings from markdown content
          const headingRegex = /^#+\s+(.+)$/gm;
          let match;
          const slug = file.replace(/\.md$/, '');

          while ((match = headingRegex.exec(content)) !== null) {
            const headingText = match[1].trim();
            if (headingText.length > 0) {
              searchIndex.push({
                id: `search-${idCounter++}`,
                content: headingText,
                excerpt: headingText,
                category: category,
                page: `/${langDir}/${urlPrefix}/${slug}`,
                path: `${urlPrefix}.${slug}.content`,
                priority: 2,
                language: langDir,
              });
            }
          }

          // Index markdown content (first 300 chars of first paragraph)
          const paragraphs = content
            .split('\n\n')
            .filter((p) => p.trim() && !p.startsWith('#'));

          if (paragraphs.length > 0) {
            const contentSnippet = paragraphs[0]
              .replace(/#+/g, '')
              .replace(/[*_]/g, '')
              .trim();

            if (contentSnippet.length > 0) {
              searchIndex.push({
                id: `search-${idCounter++}`,
                content: contentSnippet,
                excerpt: truncateExcerpt(contentSnippet, 150),
                category: category,
                page: `/${langDir}/${urlPrefix}/${slug}`,
                path: `${urlPrefix}.${slug}.content`,
                priority: 3,
                language: langDir,
              });
            }
          }
        });
      });
    } else {
      // Flat structure (backward compatibility)
      const files = fs.readdirSync(collectionDir);
      files.forEach((file) => {
        if (!file.endsWith('.md')) return;

        totalFiles++;
        const filePath = path.join(collectionDir, file);
        const fileContent = fs.readFileSync(filePath, 'utf-8');
        const { data: frontmatter, content } = matter(fileContent);

        // Index frontmatter title
        if (frontmatter.title) {
          const slug = file.replace(/\.md$/, '');
          searchIndex.push({
            id: `search-${idCounter++}`,
            content: frontmatter.title,
            excerpt: frontmatter.description || truncateExcerpt(content, 150),
            category: category,
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
    console.warn(
      `⚠ Warning: Could not index ${category}:`,
      error.message
    );
  }
}

/**
 * Categorize content based on key path (for translations)
 */
function categorizeByPath(keyPath) {
  if (keyPath.startsWith('hero')) return 'Hero';
  if (keyPath.startsWith('solutions')) return 'Solutions';
  if (keyPath.startsWith('problem')) return 'Problem';
  if (keyPath.startsWith('earlyAccess')) return 'Early Access';
  if (keyPath.startsWith('pages.contact')) return 'Contact';
  if (keyPath.startsWith('pages.home')) return 'Home';
  if (keyPath.startsWith('pages')) return 'Pages';
  if (keyPath.startsWith('navigation')) return 'Navigation';
  if (keyPath.startsWith('footer')) return 'Footer';
  if (keyPath.startsWith('common')) return 'Common';
  return 'Other';
}

/**
 * Detect which page this content belongs to
 */
function detectPage(keyPath) {
  if (keyPath.includes('pages.contact')) return '/contact';
  if (keyPath.includes('pages.notFound')) return '/404';
  return '/';
}

/**
 * Calculate priority for ranking (for translations)
 * 1 = highest, 3 = lowest
 */
function calculatePriority(keyPath) {
  if (
    keyPath.startsWith('hero.title') ||
    keyPath.startsWith('solutions.title') ||
    keyPath.startsWith('problem.title')
  ) {
    return 1;
  }
  if (
    keyPath.includes('description') ||
    keyPath.includes('benefits') ||
    keyPath.includes('subtitle')
  ) {
    return 2;
  }
  return 3;
}

/**
 * Truncate text to excerpt length with ellipsis
 */
function truncateExcerpt(text, maxLength = 150) {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength).trim() + '...';
}

// Run generator
generateSearchIndex();
