/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@talvynza/shared-types': fileURLToPath(new URL('../../packages/shared-types/index.ts', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8000', changeOrigin: false } },
  },
  test: { include: ['src/**/*.test.{ts,tsx}'], environment: 'jsdom', globals: true, setupFiles: ['./src/test/setup.ts'], css: false },
})
