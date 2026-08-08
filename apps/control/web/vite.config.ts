import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const DEV_PORT = Number(process.env.VITE_DEV_PORT ?? 5173)
const API_PROXY_TARGET = process.env.VITE_DEV_API_PROXY ?? 'http://127.0.0.1:8720'

export default defineConfig({
  plugins: [react()],
  server: {
    port: DEV_PORT,
    proxy: {
      '/api': API_PROXY_TARGET,
    },
  },
})
