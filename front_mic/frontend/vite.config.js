import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api/ai_search': {
        target: 'http://localhost:8000',
        changeOrigin: true
        // No rewrite - backend expects /api/ai_search
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
        // 不 rewrite：后端路由带 /api 前缀，如 /api/token
      },
      '/search': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/cws': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/reading': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
