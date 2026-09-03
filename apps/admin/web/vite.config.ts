import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Admin app dev server: 5174 (the Control Centre's is 5173), proxying
// /api to the admin backend on 8730. Both are overridable for a
// locked-down environment that assigns its own ports.
const DEV_PORT = Number(process.env.VITE_DEV_PORT ?? 5174)
const API_PROXY_TARGET = process.env.VITE_DEV_API_PROXY ?? 'http://127.0.0.1:8730'

export default defineConfig({
  plugins: [react()],
  server: {
    port: DEV_PORT,
    proxy: {
      '/api': API_PROXY_TARGET,
    },
  },
})
