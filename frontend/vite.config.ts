import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  // em desenvolvimento, o Flask (porta 7860) atende a API
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:7860" } },
  // o build vai para web/dist, servido pelo app.py
  build: { outDir: "../web/dist", emptyOutDir: true },
});
