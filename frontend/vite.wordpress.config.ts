import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../wordpress/litho-woocommerce/assets/react",
    emptyOutDir: true,
    cssCodeSplit: false,
    lib: {entry: "src/wordpress.tsx", name: "LithoWooCommerce", formats: ["iife"], fileName: () => "configurator.js"},
    rollupOptions: {output: {inlineDynamicImports: true, assetFileNames: "configurator.css"}},
  },
});
