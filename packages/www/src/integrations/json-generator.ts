/**
 * Astro integration for JSON template catalog generation
 *
 * This integration runs the JSON generation script during build
 * to produce the JSON configuration files from packages/json templates.
 *
 * Output: dist/json/
 *   - templates.json (master catalog)
 *   - templates/*.json (individual template files)
 *   - configs/*.json (configuration files)
 *   - index.html, api.html (catalog website)
 */

import { execSync } from 'node:child_process';
import type { AstroIntegration } from 'astro';

export default function jsonGeneratorIntegration(): AstroIntegration {
  return {
    name: 'json-generator',
    hooks: {
      'astro:build:done': ({ dir }) => {
        // dir.pathname gives us the output directory (e.g., /app/packages/www/dist/)
        // We need the project root which is the parent of dist
        const projectRoot = new URL('..', dir).pathname.replace(/^\/([A-Z]:)/, '$1');

        process.stdout.write('Generating JSON configuration files...\n');

        execSync('node scripts/generate-json.js', {
          stdio: 'inherit',
          cwd: projectRoot,
        });

        process.stdout.write('JSON generation complete.\n');
      },
    },
  };
}
