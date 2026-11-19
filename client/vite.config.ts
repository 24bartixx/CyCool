import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Where the dev server forwards /api requests.
// Locally: the backend on localhost. In Docker Compose: http://backend:8000.
const apiProxyTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    // Allow public tunnel hostnames (ngrok) so the demo can be shared.
    allowedHosts: ['.ngrok-free.app', '.ngrok-free.dev', '.ngrok.app', '.ngrok.dev'],
    proxy: {
      '/api': { target: apiProxyTarget, changeOrigin: true },
    },
  },
})
