import { defineConfig, Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import tsconfigPaths from 'vite-tsconfig-paths';
import path from 'path';

// Custom plugin to resolve @rediacc/shared to source files in dev mode
// This runs before other resolution, ensuring source files are used
function sharedSourcePlugin(isDev: boolean): Plugin {
  const sharedSrcPath = path.resolve(__dirname, '../shared/src');

  return {
    name: 'resolve-shared-source',
    enforce: 'pre', // Run before other plugins
    resolveId(source) {
      if (!isDev) return null; // Only in dev mode

      if (source === '@rediacc/shared') {
        return path.join(sharedSrcPath, 'index.ts');
      }
      if (source.startsWith('@rediacc/shared/')) {
        const subpath = source.replace('@rediacc/shared/', '');
        // Try with /index.ts first, then .ts
        return path.join(sharedSrcPath, subpath, 'index.ts');
      }
      return null;
    },
  };
}

export default defineConfig(({ mode }) => {
  const isDev = mode === 'development';

  return {
    plugins: [
      sharedSourcePlugin(isDev), // Must be first to intercept @rediacc/shared
      react(),
      tsconfigPaths({ root: '../..' }), // Resolve tsconfig paths from monorepo root
    ],
    // Use environment variable for base path configuration
    // Local development: defaults to '/console/' (works with middleware at localhost:7322/console/)
    // Production (GitHub Pages): set VITE_BASE_PATH=/ (works at console.rediacc.com/)
    base: process.env.VITE_BASE_PATH || '/console/',
    resolve: {
      alias: [{ find: '@', replacement: path.resolve(__dirname, './src') }],
    },
    server: {
      port: 3000,
      headers: {
        'X-Frame-Options': 'DENY',
        'X-Content-Type-Options': 'nosniff',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'X-XSS-Protection': '1; mode=block',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()',
      },
      proxy: {
        '/api': {
          target: `http://localhost:${process.env.VITE_HTTP_PORT || '7322'}`,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: mode === 'development',
      minify: 'terser',
      terserOptions: {
        compress: {
          drop_console: mode === 'production',
          drop_debugger: true,
          pure_funcs: ['console.log', 'console.info', 'console.debug', 'console.trace'],
        },
      },
      rollupOptions: {
        output: {
          manualChunks: {
            'vendor-react': ['react', 'react-dom', 'react-router-dom'],
            'vendor-antd': ['antd'],
            'vendor-charts': ['d3'],
            'vendor-state': ['@reduxjs/toolkit', 'react-redux', '@tanstack/react-query'],
            'vendor-utils': ['axios', 'date-fns', 'zod'],
            'vendor-i18n': ['i18next', 'react-i18next', 'i18next-browser-languagedetector'],
          },
          chunkFileNames: (chunkInfo) => {
            const facadeModuleId = chunkInfo.facadeModuleId
              ? chunkInfo.facadeModuleId.split('/').pop()
              : 'chunk';
            return `assets/js/${facadeModuleId}-[hash].js`;
          },
        },
      },
      chunkSizeWarningLimit: 1000, // 1MB warning threshold
      reportCompressedSize: false, // Disable gzip size reporting for faster builds
    },
    optimizeDeps: {
      include: ['react', 'react-dom', 'antd', '@ant-design/icons'],
      exclude: ['@rediacc/shared'], // Let vite-tsconfig-paths resolve from source
    },
    define: {
      'process.env.NODE_ENV': JSON.stringify(mode),
      'import.meta.env.VITE_APP_VERSION': JSON.stringify(
        process.env.TAG || process.env.VITE_APP_VERSION || 'dev'
      ),
      'import.meta.env.VITE_BUILD_TYPE': JSON.stringify(
        process.env.REDIACC_BUILD_TYPE || (mode === 'production' ? 'RELEASE' : 'DEBUG')
      ),
      'import.meta.env.VITE_SANDBOX_API_URL': JSON.stringify(
        process.env.SANDBOX_API_URL || 'https://sandbox.rediacc.com/api'
      ),
      'import.meta.env.VITE_TURNSTILE_SITE_KEY': JSON.stringify(
        process.env.VITE_TURNSTILE_SITE_KEY || ''
      ),
    },
  };
});
