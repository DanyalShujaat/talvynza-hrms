import { join } from 'node:path'
import { defineConfig, devices } from '@playwright/test'

const py = process.platform === 'win32' ? join('.venv', 'Scripts', 'python') : join('.venv', 'bin', 'python')

// Browser tests run against a throwaway API (fresh SQLite database) and a dev web server.
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  workers: 1,
  fullyParallel: false,
  reporter: [['list']],
  use: { baseURL: 'http://localhost:5174', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    { command: `${py} scripts/run_e2e_api.py`, cwd: '../api', url: 'http://127.0.0.1:8100/health', reuseExistingServer: false, timeout: 90_000 },
    { command: 'npx vite --port 5174 --strictPort', url: 'http://localhost:5174', reuseExistingServer: false, timeout: 60_000, env: { VITE_API_PROXY: 'http://127.0.0.1:8100' } },
  ],
})
