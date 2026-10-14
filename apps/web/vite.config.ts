import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Same-origin /api in dev, as Caddy does in production.
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
});
