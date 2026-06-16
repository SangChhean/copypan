import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  base: "./",
  server: {
    port: 8052,
    proxy: {
      "/api": {
        target: "http://localhost:8051",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "../dist",
  },
});
