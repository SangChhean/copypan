import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/zh2tw/',
  build: {
    outDir: '../dist'
  }
})
