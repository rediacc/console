import react from '@vitejs/plugin-react';
import tailwind from '@tailwindcss/vite';
import fs from 'fs';
import path from 'path';
import { defineConfig, Plugin } from 'vite';
import tsconfigPaths from 'vite-tsconfig-paths';

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
        // Try direct .ts file first, then /index.ts for directories
        const directPath = path.join(sharedSrcPath, `${subpath}.ts`);
        const indexPath = path.join(sharedSrcPath, subpath, 'index.ts');

        if (fs.existsSync(directPath)) {
          return directPath;
        }
        if (fs.existsSync(indexPath)) {
          return indexPath;
        }
        // Fallback to direct path (will show proper error if missing)
        return directPath;
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
      tailwind(),
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
          // VITE_API_URL: Set explicitly for CI/remote (e.g., https://xxx.trycloudflare.com)
          // Default: http://localhost:7322 for local development
          target: process.env.VITE_API_URL ?? 'http://localhost:7322',
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
      chunkSizeWarningLimit: 1000, // 1MB warning threshold
      reportCompressedSize: false, // Disable gzip size reporting for faster builds
      rollupOptions: {
        onwarn(warning, warn) {
          // Fail build on circular dependency warnings in our own code
          // (ignore node_modules which may have internal circular deps)
          if (warning.code === 'CIRCULAR_DEPENDENCY' && !warning.message.includes('node_modules')) {
            throw new Error(warning.message);
          }
          warn(warning);
        },
      },
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
