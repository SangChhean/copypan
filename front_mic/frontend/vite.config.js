import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@testd': resolve(__dirname, '../../testD/frontend/src'),
      '@main': resolve(__dirname, 'src'),
    }
  },
  // 默认即带 content hash；显式写出便于确认 index.html 引用 [name]-[hash].js
  build: {
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
  server: {
    port: 5173,
    fs: {
      allow: [resolve(__dirname, '../..')],
    },
    proxy: {
      '/api/ai_search': {
        target: 'http://localhost:8000',
        changeOrigin: true
        // No rewrite - backend expects /api/ai_search
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
        // 不 rewrite：后端路由带 /api 前缀，如 /api/token、/api/ws/progress
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
