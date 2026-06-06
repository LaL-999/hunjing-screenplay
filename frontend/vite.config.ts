import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174, // 5173 留给浑晶主平台
    proxy: {
      // 前端开发时,/api/xxx 请求转发到 backend 8002,/api 前缀剥除
      // 即 frontend 调 /api/health → backend 收到 /health
      "/api": {
        target: "http://localhost:8002",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
