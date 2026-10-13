import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    // Local integration: `VITE_API_URL=/api npm run dev` proxies to the
    // FastAPI service (uvicorn api.main:app --port 8000) without CORS friction.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  preview: {
    host: '0.0.0.0',
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
