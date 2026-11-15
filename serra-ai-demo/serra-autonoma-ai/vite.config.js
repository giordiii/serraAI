import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Le chiamate /api vengono inoltrate al backend simulato (serra_backend, FastAPI).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": { target: process.env.VITE_BACKEND_URL || "http://127.0.0.1:8000", changeOrigin: true } }
  }
});
