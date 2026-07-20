import { defineConfig } from "vitest/config";
import solidPlugin from "vite-plugin-solid";
import { VitePWA } from "vite-plugin-pwa";
import { resolve } from "path";

export default defineConfig({
  plugins: [
    solidPlugin() as any,
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "logo.png"],
      manifest: {
        name: "AnonyMus",
        short_name: "AnonyMus",
        description: "Privacy-first encrypted P2P messaging over Tor",
        theme_color: "#0f0f23",
        background_color: "#0f0f23",
        display: "standalone",
        orientation: "portrait",
        icons: [
          { src: "logo-192.png", sizes: "192x192", type: "image/png" },
          { src: "logo-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg,wasm}"],
      },
    }) as any,
  ],

  build: {
    target: "esnext",
    // Expose WASM files through the bundle
    assetsInlineLimit: 0,
  },

  resolve: {
    alias: {
      "@": resolve(__dirname, "./src"),
      "@lib": resolve(__dirname, "./src/lib"),
      "@stores": resolve(__dirname, "./src/stores"),
      "@components": resolve(__dirname, "./src/components"),
    },
  },

  server: {
    port: 3000,
    // Proxy API calls to the FastAPI v3 node
    proxy: {
      "/v3": {
        target: "http://localhost:5001",
        changeOrigin: true,
      },
      "/socket.io": {
        target: "http://localhost:5000",
        changeOrigin: true,
        ws: true,
      },
    },
  },

  // Ensure WASM files are served with the correct MIME type
  optimizeDeps: {
    exclude: ["@/pkg"],
  },

  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{js,ts,jsx,tsx}"],
    exclude: ["tests/e2e/**", "node_modules/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
    },
  },
});
