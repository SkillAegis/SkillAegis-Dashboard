import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'


// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    // Canonical dev port (socket.js pins the backend to :4001 in DEV). If it's
    // taken Vite increments; the backends' DEV CORS accepts any localhost port.
    port: 5173
  }
})
