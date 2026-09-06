import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built bundle lands in src/devmemory/web/static/ (committed; the wheel ships
// it) and is served by FastAPI: "/" -> index.html, "/static/*" -> assets.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  base: "/static/",
  build: {
    outDir: "../static",
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  server: {
    port: 5173,
    proxy: {
      // `npm run dev` talks to a locally running `devmemory serve`.
      "/api": "http://127.0.0.1:8000",
    },
  },
});
