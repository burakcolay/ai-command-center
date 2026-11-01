import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // ACC_PORT comes from the Makefile (default 7420); only used by the dev proxy.
  const port = loadEnv(mode, ".", "ACC_").ACC_PORT || "7420";
  const backend = `http://127.0.0.1:${port}`;
  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        "/api": backend,
        "/ws": { target: backend.replace("http", "ws"), ws: true },
      },
    },
  };
});
