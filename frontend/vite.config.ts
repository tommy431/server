import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// De server draait los (standaard op poort 8000, anders API_URL); /api wordt daarnaartoe
// doorgestuurd.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.API_URL ?? "http://localhost:8000",
        rewrite: (pad) => pad.replace(/^\/api/, ""),
      },
    },
  },
});
