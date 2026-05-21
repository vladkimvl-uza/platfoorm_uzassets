import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "node:path";

/**
 * UzAssets — Telegram Web App (Phase C)
 *
 * `base: '/twa/'` so all asset URLs are prefixed and nginx can serve the
 * separate bundle at https://platform.uz-assets.uz/twa/.
 *
 * Build output: dist/ — nginx mounts this at /twa/.
 */
export default defineConfig({
  plugins: [vue()],
  base: "/twa/",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5174,
    strictPort: true,
  },
  preview: {
    host: "0.0.0.0",
    port: 5174,
    strictPort: true,
  },
});
