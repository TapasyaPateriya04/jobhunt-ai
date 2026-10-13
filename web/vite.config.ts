import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server serves the pages and proxies /api to the local FastAPI layer,
// which binds to 127.0.0.1 only. `npm run build` writes web/dist, which that
// same server then serves, so the finished app runs from one URL.
declare const process: { env: Record<string, string | undefined> };
const API_PORT = process.env.JOBHUNT_API_PORT ?? "8787";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: `http://127.0.0.1:${API_PORT}`, changeOrigin: false },
    },
  },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
});
