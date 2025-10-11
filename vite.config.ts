import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // Use root path for custom domain (console.rediacc.com)
  // If deploying to github.io/console, change to '/console/'
  base: '/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    headers: {
      'X-Frame-Options': 'DENY',
      'X-Content-Type-Options': 'nosniff',
      'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
      'X-XSS-Protection': '1; mode=block',
      'Referrer-Policy': 'strict-origin-when-cross-origin',
      'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()'
    },
    proxy: {
      '/configs/templates.json': {
        target: 'https://json.rediacc.com',
        changeOrigin: true,
        secure: true,
        rewrite: (path) => '/templates.json',
      },
      '/configs/templates/': {
        target: 'https://json.rediacc.com',
        changeOrigin: true,
        secure: true,
        rewrite: (path) => path.replace('/configs', ''),
      },
      '/configs/pricing.json': {
        target: 'https://json.rediacc.com',
        changeOrigin: true,
        secure: true,
        rewrite: (path) => '/configs/pricing.json',
      },
      '/configs/services.json': {
        target: 'https://json.rediacc.com',
        changeOrigin: true,
        secure: true,
        rewrite: (path) => '/configs/services.json',
      },
      '/configs/tiers.json': {
        target: 'https://json.rediacc.com',
        changeOrigin: true,
        secure: true,
        rewrite: (path) => '/configs/tiers.json',
      },
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
          'vendor-charts': ['@ant-design/charts', 'd3'],
          'vendor-state': ['@reduxjs/toolkit', 'react-redux', '@tanstack/react-query'],
          'vendor-utils': ['lodash', 'axios', 'date-fns', 'zod'],
          'vendor-i18n': ['i18next', 'react-i18next', 'i18next-browser-languagedetector'],
        },
        chunkFileNames: (chunkInfo) => {
          const facadeModuleId = chunkInfo.facadeModuleId ? chunkInfo.facadeModuleId.split('/').pop() : 'chunk';
          return `assets/js/${facadeModuleId}-[hash].js`;
        },
      },
    },
    chunkSizeWarningLimit: 1000, // 1MB warning threshold
    reportCompressedSize: false, // Disable gzip size reporting for faster builds
  },
  optimizeDeps: {
    include: ['react', 'react-dom', 'antd', '@ant-design/icons'],
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify(mode),
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(process.env.TAG || process.env.VITE_APP_VERSION || 'dev'),
    'import.meta.env.VITE_BUILD_TYPE': JSON.stringify(process.env.REDIACC_BUILD_TYPE || (mode === 'production' ? 'RELEASE' : 'DEBUG')),
    'import.meta.env.VITE_SANDBOX_API_URL': JSON.stringify(process.env.SANDBOX_API_URL || 'https://sandbox.rediacc.com/api'),
  },
}))