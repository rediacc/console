import * as esbuild from 'esbuild';

/** Plugin to exclude native .node bindings from the bundle.
 *  ssh2 and cpu-features have optional native bindings wrapped in try/catch,
 *  so they gracefully fall back to pure JavaScript when unavailable. */
const nativeModulesPlugin = {
  name: 'native-node-modules',
  setup(build) {
    build.onResolve({ filter: /\.node$/ }, (args) => ({
      path: args.path,
      external: true,
    }));
  },
};

await esbuild.build({
  entryPoints: ['src/index.ts'],
  bundle: true,
  platform: 'node',
  target: 'node18',
  outfile: 'dist/cli-bundle.cjs',
  format: 'cjs',
  // Note: shebang comes from src/index.ts - no banner needed
  external: [],
  plugins: [nativeModulesPlugin],
});

console.log('✓ CLI bundled to dist/cli-bundle.cjs');
