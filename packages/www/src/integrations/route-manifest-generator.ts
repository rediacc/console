/**
 * Astro integration for route manifest generation.
 *
 * Runs after build to scan dist/ and produce route-manifest.json,
 * used by the Cloudflare Worker for smart 404 redirects.
 */

import { execSync } from 'node:child_process';
import type { AstroIntegration } from 'astro';

export default function routeManifestIntegration(): AstroIntegration {
  return {
    name: 'route-manifest-generator',
    hooks: {
      'astro:build:done': ({ dir }) => {
        const projectRoot = new URL('..', dir).pathname.replace(/^\/([A-Z]:)/, '$1');

        process.stdout.write('Generating route manifest for smart 404 redirects...\n');

        execSync('node scripts/generate-route-manifest.js', {
          stdio: 'inherit',
          cwd: projectRoot,
        });

        process.stdout.write('Route manifest generation complete.\n');
      },
    },
  };
}
