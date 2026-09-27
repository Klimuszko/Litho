import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {proxy: {"/api": "http://backend:8000"}},
  worker: {format: "es"},
  build: {rollupOptions: {output: {manualChunks: {three: ["three"]}}}},
});
