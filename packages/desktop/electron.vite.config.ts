import { resolve } from 'path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'electron-vite';
import tsconfigPaths from 'vite-tsconfig-paths';

export default defineConfig({
  main: {
    build: {
      outDir: 'out/main',
      externalizeDeps: true,
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/main/index.ts'),
        },
      },
    },
  },
  preload: {
    build: {
      outDir: 'out/preload',
      externalizeDeps: true,
      rollupOptions: {
        input: {
          index: resolve(__dirname, 'src/preload/index.ts'),
        },
      },
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
