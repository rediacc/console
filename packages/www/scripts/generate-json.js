import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.join(__dirname, '..');
const jsonPackageDir = path.join(projectRoot, '..', 'json');

// Configuration
const TEMPLATES_DIR = path.join(jsonPackageDir, 'templates');
const CONFIG_DIR = path.join(jsonPackageDir, 'config');
const OUTPUT_DIR = path.join(projectRoot, 'dist', 'json');
const SKIPLIST_FILE = path.join(jsonPackageDir, '.templates-skiplist');

/**
 * JSON Template Catalog Generator
 * Processes template directories and generates JSON catalog
 *
 * Port of packages/json/generate.sh to Node.js
 */

// Load skip list from .templates-skiplist file
function loadSkipList() {
  const skipList = [];

  if (fs.existsSync(SKIPLIST_FILE)) {
    const content = fs.readFileSync(SKIPLIST_FILE, 'utf-8');
    const lines = content.split('\n');

    for (const line of lines) {
      const trimmed = line.trim();
      // Skip comments and empty lines
      if (trimmed && !trimmed.startsWith('#')) {
        skipList.push(trimmed);
        console.log(`  Will skip: ${trimmed}`);
      }
    }
  }

  return skipList;
}

// Check if template should be skipped
function shouldSkipTemplate(templatePath, skipList) {
  return skipList.includes(templatePath);
}

// Escape string for JSON
function jsonEscape(str) {
  if (!str) return '';
  return str
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r')
    .replace(/\t/g, '\\t');
}

// Get file type based on extension
function getFileType(filename) {
  const ext = path.extname(filename).toLowerCase().slice(1);
  const typeMap = {
    md: 'markdown',
    yaml: 'yaml',
    yml: 'yaml',
    json: 'json',
    sh: 'script',
    env: 'environment',
    dockerfile: 'dockerfile',
  };
  return typeMap[ext] || 'text';
}

// Extract template metadata from README
function extractTemplateMetadata(templateDir) {
  const templateName = path.basename(templateDir);
  const readmePath = path.join(templateDir, 'README.md');

  let title = templateName;
  let description = '';

  if (fs.existsSync(readmePath)) {
    const content = fs.readFileSync(readmePath, 'utf-8');

    // Extract title (first header)
    const titleMatch = content.match(/^#[^#]\s*(.+)$/m);
    if (titleMatch) {
      title = titleMatch[1].trim();
    }

    // Extract description (first paragraph after title)
    const lines = content.split('\n');
    let foundTitle = false;
    for (const line of lines) {
      if (line.match(/^#[^#]/)) {
        foundTitle = true;
        continue;
      }
      if (foundTitle && line.trim() && !line.startsWith('#')) {
        description = line.trim();
        break;
      }
    }
  }

  if (!description) {
    description = `Template for ${templateName}`;
  }

  return { title, description };
}

// Read file content
function readFileContent(filePath) {
  if (fs.existsSync(filePath)) {
    return fs.readFileSync(filePath, 'utf-8');
  }
  return '';
}

// Generate individual template JSON file
function generateTemplateJson(templateDir, outputFile) {
  const templateName = path.basename(templateDir);
  const category = path.basename(path.dirname(templateDir));
  const templateId = `${category}_${templateName}`;

  console.log(`  Processing: ${category}/${templateName}`);

  const metadata = extractTemplateMetadata(templateDir);

  const template = {
    id: templateId,
    name: metadata.title,
    description: metadata.description,
    category: category,
    tags: [category, templateName],
    files: [],
    readme: readFileContent(path.join(templateDir, 'README.md')),
    generated: new Date().toISOString(),
  };

  // Process files in template directory
  const entries = fs.readdirSync(templateDir, { withFileTypes: true });

  for (const entry of entries) {
    if (entry.isDirectory()) continue;

    const filename = entry.name;
    // Skip hidden files except .env
    if (filename.startsWith('.') && filename !== '.env') continue;

    const filePath = path.join(templateDir, filename);
    const content = readFileContent(filePath);

    template.files.push({
      name: filename,
      path: `${templateName}/${filename}`,
      type: getFileType(filename),
      content: content,
    });
  }

  // Write template JSON
  fs.writeFileSync(outputFile, JSON.stringify(template, null, 2));
}

// Generate master catalog JSON
function generateCatalogJson(templatesDir, outputFile, skipList) {
  console.log('Generating templates catalog...');

  const catalog = {
    version: '1.0',
    generated: new Date().toISOString(),
    total_templates: 0,
    categories: [],
    templates: [],
  };

  const categoriesSet = new Set();

  // Process each category directory
  const categories = fs
    .readdirSync(templatesDir, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .sort();

  for (const category of categories) {
    const categoryDir = path.join(templatesDir, category);
    const templates = fs
      .readdirSync(categoryDir, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => d.name)
      .sort();

    for (const templateName of templates) {
      const templateDir = path.join(categoryDir, templateName);
      const templatePath = `${category}/${templateName}`;

      // Check if it's a valid template (has README or docker-compose or Rediaccfile)
      const hasReadme = fs.existsSync(path.join(templateDir, 'README.md'));
      const hasDocker = fs.existsSync(path.join(templateDir, 'docker-compose.yaml'));
      const hasRediaccfile = fs.existsSync(path.join(templateDir, 'Rediaccfile'));

      if (!hasReadme && !hasDocker && !hasRediaccfile) continue;

      catalog.total_templates++;
      categoriesSet.add(category);

      const templateId = `${category}_${templateName}`;
      const metadata = extractTemplateMetadata(templateDir);
      const status = shouldSkipTemplate(templatePath, skipList) ? 'skipped' : 'active';

      // Count files
      const fileCount = fs
        .readdirSync(templateDir, { withFileTypes: true })
        .filter((f) => f.isFile()).length;

      catalog.templates.push({
        id: templateId,
        name: metadata.title,
        description: metadata.description,
        category: category,
        tags: [category, templateName],
        file_count: fileCount,
        has_readme: hasReadme,
        has_docker: hasDocker,
        status: status,
        download_url: `templates/${templateId}.json`,
        readme: readFileContent(path.join(templateDir, 'README.md')),
      });
    }
  }

  catalog.categories = Array.from(categoriesSet).sort();

  // Write catalog JSON
  fs.writeFileSync(outputFile, JSON.stringify(catalog, null, 2));
}

// Process configuration files
function processConfigs(configDir, outputDir) {
  console.log('Processing configuration files...');

  const configFiles = ['endpoints.json', 'pricing.json', 'services.json', 'tiers.json'];
  const configsOutputDir = path.join(outputDir, 'configs');

  fs.mkdirSync(configsOutputDir, { recursive: true });

  let processed = 0;

  for (const filename of configFiles) {
    const srcPath = path.join(configDir, filename);
    const destPath = path.join(configsOutputDir, filename);

    if (fs.existsSync(srcPath)) {
      fs.copyFileSync(srcPath, destPath);
      processed++;
    }
  }

  console.log(`  Processed ${processed} configuration files`);
}

// Copy static website files
function copyWebsiteFiles(jsonPackageDir, outputDir) {
  console.log('Copying website files...');

  const srcDir = path.join(jsonPackageDir, 'src');

  // Copy HTML files
  const files = ['index.html', 'api.html', '_config.yml'];

  for (const filename of files) {
    const srcPath = path.join(srcDir, filename);
    const destPath = path.join(outputDir, filename);

    if (fs.existsSync(srcPath)) {
      fs.copyFileSync(srcPath, destPath);
    }
  }

  console.log('  Website files copied');
}

// Minify JSON files
function minifyJsonFiles(outputDir) {
  console.log('Minifying JSON files...');

  let minified = 0;
  let sizeBefore = 0;
  let sizeAfter = 0;

  function processDir(dir) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);

      if (entry.isDirectory()) {
        processDir(fullPath);
      } else if (entry.name.endsWith('.json')) {
        const stats = fs.statSync(fullPath);
        sizeBefore += stats.size;

        const content = fs.readFileSync(fullPath, 'utf-8');
        const minifiedContent = JSON.stringify(JSON.parse(content));
        fs.writeFileSync(fullPath, minifiedContent);

        const newStats = fs.statSync(fullPath);
        sizeAfter += newStats.size;
        minified++;
      }
    }
  }

  processDir(outputDir);

  const savings = sizeBefore - sizeAfter;
  const percentage = sizeBefore > 0 ? Math.round((savings / sizeBefore) * 100) : 0;

  console.log(`  Minified ${minified} files (saved ${savings} bytes, ${percentage}% reduction)`);
}

// Main function
async function main() {
  console.log('========================================');
  console.log('JSON Config Generator (Node.js)');
  console.log('========================================');
  console.log('');

  // Check if json package exists
  if (!fs.existsSync(TEMPLATES_DIR)) {
    console.error(`Templates directory not found: ${TEMPLATES_DIR}`);
    console.error('Please ensure packages/json exists');
    process.exit(1);
  }

  // Clean and create output directory
  console.log('Cleaning output directory...');
  if (fs.existsSync(OUTPUT_DIR)) {
    fs.rmSync(OUTPUT_DIR, { recursive: true });
  }
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  fs.mkdirSync(path.join(OUTPUT_DIR, 'templates'), { recursive: true });

  // Load skip list
  console.log('Loading skip list...');
  const skipList = loadSkipList();

  // Process templates
  console.log('Processing templates...');
  let processedCount = 0;

  const categories = fs
    .readdirSync(TEMPLATES_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name)
    .sort();

  for (const category of categories) {
    const categoryDir = path.join(TEMPLATES_DIR, category);
    const templates = fs
      .readdirSync(categoryDir, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => d.name)
      .sort();

    for (const templateName of templates) {
      const templateDir = path.join(categoryDir, templateName);
      const templatePath = `${category}/${templateName}`;

      // Check if it's a valid template
      const hasReadme = fs.existsSync(path.join(templateDir, 'README.md'));
      const hasDocker = fs.existsSync(path.join(templateDir, 'docker-compose.yaml'));
      const hasRediaccfile = fs.existsSync(path.join(templateDir, 'Rediaccfile'));

      if (!hasReadme && !hasDocker && !hasRediaccfile) continue;

      // Skip if in skip list
      if (shouldSkipTemplate(templatePath, skipList)) {
        console.log(`  Skipping: ${templatePath}`);
        continue;
      }

      const templateId = `${category}_${templateName}`;
      const outputFile = path.join(OUTPUT_DIR, 'templates', `${templateId}.json`);

      generateTemplateJson(templateDir, outputFile);
      processedCount++;
    }
  }

  console.log(`  Processed ${processedCount} templates`);

  // Generate catalog
  generateCatalogJson(TEMPLATES_DIR, path.join(OUTPUT_DIR, 'templates.json'), skipList);

  // Process configs
  processConfigs(CONFIG_DIR, OUTPUT_DIR);

  // Copy website files
  copyWebsiteFiles(jsonPackageDir, OUTPUT_DIR);

  // Create test-results.json placeholder
  const testResultsPath = path.join(OUTPUT_DIR, 'test-results.json');
  if (!fs.existsSync(testResultsPath)) {
    fs.writeFileSync(
      testResultsPath,
      JSON.stringify({
        summary: { total: 0, passed: 0, failed: 0, skipped: 0, duration: '0s', timestamp: '' },
        results: [],
      })
    );
  }

  // Minify JSON files
  minifyJsonFiles(OUTPUT_DIR);

  // Summary
  console.log('');
  console.log('========================================');
  console.log('Generation Summary');
  console.log('========================================');
  console.log(`Output Directory: ${OUTPUT_DIR}`);
  console.log('');
  console.log('Generated Files:');
  console.log('  - index.html (Template catalog UI)');
  console.log('  - api.html (API documentation)');
  console.log('  - templates.json (Templates index)');
  console.log(`  - templates/ (${processedCount} template files)`);
  console.log('  - configs/ (Configuration files)');
  console.log('');
  console.log('Generation completed successfully!');
}

// Run
main().catch((error) => {
  console.error('Generation failed:', error);
  process.exit(1);
});
