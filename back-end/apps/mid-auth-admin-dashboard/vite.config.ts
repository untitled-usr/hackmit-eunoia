import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    host: "127.0.0.1",
    proxy: {
      "/admin": { target: "http://127.0.0.1:18080", changeOrigin: true },
      "/auth": { target: "http://127.0.0.1:18080", changeOrigin: true },
      "/embed": { target: "http://127.0.0.1:18080", changeOrigin: true, ws: true },
      "/healthz": { target: "http://127.0.0.1:18080", changeOrigin: true }
    }
  }
});
