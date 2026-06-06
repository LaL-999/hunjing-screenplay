<script setup lang="ts">
import { onMounted, ref } from "vue";

const backendStatus = ref<"unknown" | "ok" | "error">("unknown");
const backendInfo = ref<{ version?: string; llm_model?: string; llm_configured?: boolean }>({});
const errorMsg = ref<string>("");

async function checkBackend() {
  try {
    const r = await fetch("/api/health");
    if (!r.ok) {
      throw new Error(`HTTP ${r.status}`);
    }
    const body = await r.json();
    backendInfo.value = body;
    backendStatus.value = "ok";
  } catch (e) {
    backendStatus.value = "error";
    errorMsg.value = e instanceof Error ? e.message : String(e);
  }
}

onMounted(() => {
  // 注:vite.config.ts 配置了 /api → http://localhost:8002 代理
  // 所以 frontend 用 /api/health 即可
  // 但 /api 前缀是 vite 代理拦截的,backend 实际 endpoint 是 /health
  // 调整一下:vite 代理改成把 /api 前缀去掉
  checkBackend();
});
</script>

<template>
  <main class="app">
    <header class="hdr">
      <h1>
        <span class="brand-icon">📝</span>
        浑晶 · 剧创态
      </h1>
      <p class="tagline">AI 小说自动转剧本 YAML · 浑晶平台第 5 态</p>
    </header>

    <section class="status-card">
      <h2>后端服务状态</h2>

      <!-- 主状态:三态互斥 unknown / ok / error -->
      <template v-if="backendStatus === 'unknown'">
        <div class="status-row">
          <span class="dot dot--pending"></span>
          <span>正在连接 backend...</span>
        </div>
      </template>
      <template v-else-if="backendStatus === 'ok'">
        <div class="status-row status-row--ok">
          <span class="dot dot--ok"></span>
          <span>已连接</span>
          <span class="meta">v{{ backendInfo.version }} · LLM: {{ backendInfo.llm_model }}</span>
        </div>
        <!-- LLM 配置子状态 — 已连接时才显示 -->
        <div
          v-if="backendInfo.llm_configured === false"
          class="status-row status-row--warn"
        >
          <span class="dot dot--warn"></span>
          <span>LLM API key 未配置</span>
          <span class="meta">编辑 backend/.env 填入 DEEPSEEK_API_KEY</span>
        </div>
        <div
          v-else-if="backendInfo.llm_configured === true"
          class="status-row status-row--ok"
        >
          <span class="dot dot--ok"></span>
          <span>LLM 已配置</span>
          <span class="meta">DeepSeek 凭据已加载</span>
        </div>
      </template>
      <template v-else>
        <div class="status-row status-row--err">
          <span class="dot dot--err"></span>
          <span>未连接 — {{ errorMsg }}</span>
        </div>
        <p class="hint">
          请检查 backend 是否在 8003 端口运行:<br />
          <code>cd backend &amp;&amp; uvicorn app.main:app --reload --port 8003</code>
        </p>
      </template>
    </section>

    <section class="roadmap">
      <h2>开发进度(2026 年 6 月 5-7 日)</h2>
      <ol>
        <li class="done">脚手架 + Schema 文档(PR#1-2)</li>
        <li class="todo">小说摄入 + 故事圣经(PR#3-4)</li>
        <li class="todo">场景切分(PR#5-6)</li>
        <li class="todo">逐场转换流水线(PR#7-9)</li>
        <li class="todo">YAML 组装 + 校验(PR#10)</li>
        <li class="todo">双栏编辑器 UI(PR#11)</li>
        <li class="todo">fidelity 评分 + 结构报告(PR#12-13)</li>
        <li class="todo">README 终稿 + demo 视频(PR#14)</li>
      </ol>
    </section>

    <footer class="footer">
      <a href="https://github.com/LaL-999/hunjing-screenplay" target="_blank">GitHub 仓库</a>
      <span class="sep">·</span>
      <a href="http://localhost:8003/docs" target="_blank">API 文档</a>
      <span class="sep">·</span>
      <a href="https://github.com/LaL-999/hunjing-screenplay/blob/main/docs/SCHEMA_DESIGN.md" target="_blank">Schema 设计</a>
    </footer>
  </main>
</template>

<style scoped>
.app {
  max-width: 640px;
  margin: 36px auto;
  padding: 0 20px;
  font-family:
    -apple-system, "PingFang SC", "Microsoft YaHei", Segoe UI, Roboto,
    sans-serif;
  color: #2a2724;
}

.hdr {
  text-align: center;
  margin-bottom: 28px;
}
.hdr h1 {
  font-size: 22px;
  margin: 0 0 4px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.brand-icon {
  margin-right: 4px;
}
.tagline {
  color: #6a665e;
  font-size: 12.5px;
  margin: 0;
}

.status-card,
.roadmap {
  background: #fffdf9;
  border: 1px solid #ece8de;
  border-radius: 10px;
  padding: 16px 18px;
  margin-bottom: 16px;
}
.status-card h2,
.roadmap h2 {
  font-size: 11px;
  font-weight: 600;
  color: #9a968d;
  margin: 0 0 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  padding: 4px 0;
}
.status-row + .status-row {
  border-top: 1px dashed #ece8de;
  margin-top: 4px;
  padding-top: 8px;
}
.status-row .meta {
  color: #9a968d;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  margin-left: auto;
  text-align: right;
}
.status-row--ok {
  color: #047857;
}
.status-row--err {
  color: #b91c1c;
}
.status-row--warn {
  color: #b45309;
  margin-top: 6px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot--ok {
  background: #10b981;
}
.dot--err {
  background: #ef4444;
}
.dot--warn {
  background: #f59e0b;
}
.dot--pending {
  background: #9ca3af;
  animation: blink 1.4s ease-in-out infinite;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.4; }
}

.hint {
  font-size: 11.5px;
  color: #9a968d;
  margin: 10px 0 0;
  line-height: 1.6;
}
.hint code {
  background: #f5f3ee;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 11px;
}

.roadmap ol {
  margin: 0;
  padding-left: 18px;
}
.roadmap li {
  font-size: 12.5px;
  line-height: 1.75;
  color: #4a4640;
}
.roadmap li.done {
  color: #047857;
}
.roadmap li.done::before {
  content: "✓ ";
  font-weight: 600;
}
.roadmap li.todo {
  color: #9a968d;
}

.footer {
  text-align: center;
  margin-top: 24px;
  font-size: 11.5px;
  color: #9a968d;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.footer a {
  color: #8b5cf6;
  text-decoration: none;
  transition: color 150ms;
}
.footer a:hover {
  text-decoration: underline;
  color: #7c3aed;
}
.footer .sep {
  color: #d1cfc7;
}
</style>
