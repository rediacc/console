import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: process.env.NODE_ENV === 'production' ? '/console/' : '/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    headers: {
      'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ws: http://localhost:*; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'; form-action 'self';",
      'X-Frame-Options': 'DENY',
      'X-Content-Type-Options': 'nosniff',
      'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
      'X-XSS-Protection': '1; mode=block',
      'Referrer-Policy': 'strict-origin-when-cross-origin',
      'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=()'
    },
    proxy: {
      '/api': {
        target: `http://localhost:${process.env.VITE_MIDDLEWARE_PORT || '8080'}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-antd': ['antd', '@ant-design/icons'],
          'vendor-charts': ['@ant-design/charts', 'd3'],
          'vendor-state': ['@reduxjs/toolkit', 'react-redux', '@tanstack/react-query'],
          'vendor-utils': ['lodash', 'axios', 'date-fns', 'zod'],
        },
      },
    },
  },
  define: {
    'process.env.NODE_ENV': JSON.stringify(mode),
  },
}))