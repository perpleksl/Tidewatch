/// <reference types="vitest/config" />
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Exposes VITE_* and CLERK_PUBLISHABLE_KEY to the browser. Never add a prefix that could
  // match a secret (e.g. "CLERK_"), or CLERK_SECRET_KEY would be shipped to every visitor.
  envPrefix: ['VITE_', 'CLERK_PUBLISHABLE_'],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: false,
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
})
