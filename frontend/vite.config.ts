import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxy = {
  "/api": process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000",
};

export default defineConfig(() => ({
  plugins: [react()],
  test: {
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
  },
  server: {
    proxy: apiProxy,
  },
  preview: { proxy: apiProxy },
}));
