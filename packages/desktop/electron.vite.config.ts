import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'electron-vite';
import tsconfigPaths from 'vite-tsconfig-paths';

// Single source of truth for externalized modules (see externals.json)
const externalsConfig = JSON.parse(readFileSync(resolve(__dirname, 'externals.json'), 'utf8'));
const ssrExternal: string[] = [
  ...externalsConfig.managed,
  ...externalsConfig.externals,
  ...externalsConfig.optional,
];

export default defineConfig({
  main: {
    build: {
      outDir: 'out/main',
      // Don't auto-externalize deps - we handle it via ssr.external
      externalizeDeps: false,
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/main/index.ts'),
        },
      },
    },
    resolve: {
      alias: {
        '@rediacc/shared': resolve(__dirname, '../shared/src'),
        '@rediacc/shared-desktop': resolve(__dirname, '../shared-desktop/src'),
      },
    },
    // SSR externalization - only externalize native/electron modules.
    // List sourced from externals.json (single source of truth).
    ssr: {
      external: ssrExternal,
      // Bundle all other packages including workspace packages
      noExternal: true,
    },
  },
  preload: {
    build: {
      outDir: 'out/preload',
      externalizeDeps: false,
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/preload/index.ts'),
        },
      },
    },
    resolve: {
      alias: {
        '@rediacc/shared': resolve(__dirname, '../shared/src'),
        '@rediacc/shared-desktop': resolve(__dirname, '../shared-desktop/src'),
      },
    },
    ssr: {
      external: ['electron'],
      noExternal: true,
    },
  },
  renderer: {
    root: resolve(__dirname, 'src/renderer'),
    plugins: [react(), tsconfigPaths({ root: resolve(__dirname, '../..') })],
    resolve: {
      alias: {
        '@': resolve(__dirname, '../web/src'),
        '@rediacc/shared': resolve(__dirname, '../shared/src'),
      },
    },
    build: {
      outDir: resolve(__dirname, 'out/renderer'),
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/renderer/index.html'),
        },
      },
    },
    define: {
      'import.meta.env.VITE_BUILD_TYPE': JSON.stringify('ELECTRON'),
      'import.meta.env.VITE_BASE_PATH': JSON.stringify('/'),
    },
  },
});
