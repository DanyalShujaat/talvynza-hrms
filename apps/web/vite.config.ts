/// <reference types="vitest/config" />
import { createHash } from 'node:crypto'
import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const apiProxy = process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8000'
const proxyKey = createHash('sha256').update(apiProxy).digest('hex').slice(0, 12)

export default defineConfig({
  cacheDir: `node_modules/.vite-${proxyKey}`,
  plugins: [react(), tailwindcss()],
  optimizeDeps: { include: ['leaflet'] },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@talvynza/shared-types': fileURLToPath(new URL('../../packages/shared-types/index.ts', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: { '/api': { target: apiProxy, changeOrigin: false } },
  },
  test: { include: ['src/**/*.test.{ts,tsx}'], environment: 'jsdom', globals: true, setupFiles: ['./src/test/setup.ts'], css: false },
})
