import * as esbuild from 'esbuild';

await esbuild.build({
  entryPoints: ['src/index.ts'],
  bundle: true,
  platform: 'node',
  target: 'node18',
  outfile: 'dist/cli-bundle.cjs',
  format: 'cjs',
  // Note: shebang comes from src/index.ts - no banner needed
  external: [],
});

console.log('✓ CLI bundled to dist/cli-bundle.cjs');
