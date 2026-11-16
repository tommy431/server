import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// De server draait los op poort 8000; /api wordt daarnaartoe doorgestuurd.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        rewrite: (pad) => pad.replace(/^\/api/, ""),
      },
    },
  },
});
