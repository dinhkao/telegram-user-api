// Build config — base './' để bundle chạy được cả dưới /app/ (aiohttp) lẫn
// file:///android_asset (WebView APK). Proxy /api → server 8090 khi dev.
import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

export default defineConfig({
  plugins: [preact()],
  base: "./",
  server: {
    port: 5174,
    proxy: { "/api": "http://localhost:8090" },
  },
  build: { target: "es2017" },
});
