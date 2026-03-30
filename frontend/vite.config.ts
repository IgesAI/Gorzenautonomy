import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import cesium from 'vite-plugin-cesium';
import path from 'path';

const apiProxyTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react(), cesium()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            const c = proxyRes.statusCode;
            if (c !== 301 && c !== 302 && c !== 307 && c !== 308) return;
            const loc = proxyRes.headers.location;
            if (!loc || typeof loc !== 'string') return;
            try {
              const targetOrigin = new URL(apiProxyTarget).origin;
              const u = new URL(loc, apiProxyTarget);
              if (u.origin === targetOrigin) {
                proxyRes.headers.location = `/api${u.pathname}${u.search}`;
              }
            } catch {
              /* ignore malformed Location */
            }
          });
        },
      },
    },
  },
});
