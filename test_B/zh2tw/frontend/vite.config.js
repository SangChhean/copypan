import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
export default defineConfig({
  plugins: [vue()],
  base: "/zh2tw/",
  base: "./",
  server: {
    port: 8008,
    strictPort: true,
  },
  build: {
    outDir: "../dist",
  },
});
