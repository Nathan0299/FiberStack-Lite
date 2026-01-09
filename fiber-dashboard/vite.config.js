import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // Listen on 0.0.0.0 for Docker
    port: 3000, // Match legacy CRA port
    proxy: {
      '/api': {
        target: 'http://fiber-api:8000',
        changeOrigin: true,
        secure: false,
      }
    }
  }
})
