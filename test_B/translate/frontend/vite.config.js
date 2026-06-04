import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  base: "./",
  build: {
    outDir: "../dist",
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8003",
        changeOrigin: true,
      },
    },
  },
});
