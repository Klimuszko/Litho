import {defineConfig} from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // React's library build otherwise leaves process.env.NODE_ENV in the IIFE.
  // WordPress loads this file directly in the browser, where Node's `process`
  // global does not exist.
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    outDir: "../wordpress/litho-woocommerce/assets/react",
    emptyOutDir: true,
    cssCodeSplit: false,
    lib: {entry: "src/wordpress.tsx", name: "LithoWooCommerce", formats: ["iife"], fileName: () => "configurator.js"},
    rollupOptions: {output: {inlineDynamicImports: true, assetFileNames: "configurator.css"}},
  },
});
