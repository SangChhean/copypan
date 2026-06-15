import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { AntDesignVueResolver } from 'unplugin-vue-components/resolvers'
import { resolve } from 'path'

export default defineConfig({
  plugins: [
    vue(),
    Components({
      resolvers: [
        AntDesignVueResolver({
          importStyle: false,
        }),
      ],
    }),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5176,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8014',
        changeOrigin: true,
      },
      // 仅本地开发：借用 front_qa 的 LSM PDF 静态资源（Phase 2.3）
      '/lsm': {
        target: 'http://127.0.0.1:5174',
        changeOrigin: true,
      },
    },
  },
})
