<script setup lang="ts">
/**
 * 主页 — 后端状态 + 小说列表入口 + 路线图。
 * PR#11 从 App.vue 抽离过来,App.vue 改为路由容器。
 */
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import NovelUploadCard from "../components/NovelUploadCard.vue";
import { deleteNovel, getHealth, listNovels } from "../api/client";
import type { NovelInfo } from "../types/screenplay";

const router = useRouter();

const backendStatus = ref<"unknown" | "ok" | "error">("unknown");
const backendInfo = ref<{
  version?: string;
  llm_model?: string;
  llm_configured?: boolean;
}>({});
const errorMsg = ref<string>("");

const novels = ref<NovelInfo[]>([]);
const novelsLoading = ref<boolean>(false);

async function checkBackend() {
  try {
    backendInfo.value = await getHealth();
    backendStatus.value = "ok";
  } catch (e) {
    backendStatus.value = "error";
    errorMsg.value = e instanceof Error ? e.message : String(e);
  }
}

async function loadNovels() {
  novelsLoading.value = true;
  try {
    novels.value = await listNovels();
  } catch {
    novels.value = [];
  } finally {
    novelsLoading.value = false;
  }
}

function openEditor(novelId: string) {
  router.push({ name: "screenplay-editor", params: { id: novelId } });
}

async function handleUploaded(novelId: string) {
  // 上传成功 → 刷新列表 + 直接跳编辑器
  await loadNovels();
  openEditor(novelId);
}

async function handleDelete(novelId: string, title: string, ev: MouseEvent) {
  // 阻止冒泡(不要触发 openEditor)
  ev.stopPropagation();
  if (!confirm(`确定删除《${title}》?同时清除所有章节、剧本、改编决策。`)) {
    return;
  }
  try {
    await deleteNovel(novelId);
    await loadNovels();
  } catch (e) {
    alert("删除失败:" + (e instanceof Error ? e.message : String(e)));
  }
}

onMounted(() => {
  checkBackend();
  loadNovels();
});
</script>

<template>
  <main class="home">
    <header class="hdr">
      <h1>浑晶 · 剧创态</h1>
      <p class="tagline">AI 小说自动转剧本 YAML · 浑晶平台第 5 态</p>
    </header>

    <section class="status-card">
      <h2>后端服务状态</h2>
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
        <div
          v-if="backendInfo.llm_configured === false"
          class="status-row status-row--warn"
        >
          <span class="dot dot--warn"></span>
          <span>LLM API key 未配置</span>
          <span class="meta">编辑 backend/.env</span>
        </div>
        <div v-else class="status-row status-row--ok">
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
      </template>
    </section>

    <NovelUploadCard @uploaded="handleUploaded" />

    <section class="novels-card">
      <h2>已上传的小说</h2>
      <div v-if="novelsLoading" class="empty">加载中...</div>
      <div v-else-if="novels.length === 0" class="empty">
        还没有上传过小说 — 上面的上传卡拖一个 .txt / .epub / .docx 文件试试
      </div>
      <ul v-else class="novel-list">
        <li
          v-for="n in novels"
          :key="n.id"
          class="novel-item"
          @click="openEditor(n.id)"
        >
          <div class="novel-main">
            <div class="novel-title">{{ n.title }}</div>
            <div class="novel-meta">
              {{ n.source_format }} · {{ n.total_chapters }} 章 ·
              {{ n.total_chars.toLocaleString() }} 字
            </div>
          </div>
          <button
            class="delete-btn"
            title="删除"
            @click="(e) => handleDelete(n.id, n.title, e)"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <polyline points="3 6 5 6 21 6" />
              <path
                d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6m5 0V4a2 2 0 0 1 2-2h0a2 2 0 0 1 2 2v2"
              />
            </svg>
          </button>
          <span class="open-arrow">→</span>
        </li>
      </ul>
    </section>

    <footer class="footer">
      <a href="https://github.com/LaL-999/hunjing-screenplay" target="_blank"
        >GitHub 仓库</a
      >
      <span class="sep">·</span>
      <a href="http://localhost:8003/docs" target="_blank">API 文档</a>
      <span class="sep">·</span>
      <a
        href="https://github.com/LaL-999/hunjing-screenplay/blob/main/docs/SCHEMA_DESIGN.md"
        target="_blank"
        >Schema 设计</a
      >
    </footer>
  </main>
</template>

<style scoped>
.home {
  max-width: 720px;
  margin: 36px auto;
  padding: 0 20px;
  color: var(--text);
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
.tagline {
  color: var(--text-muted);
  font-size: 12.5px;
  margin: 0;
}

.status-card,
.novels-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px 18px;
  margin-bottom: 16px;
}
.status-card h2,
.novels-card h2 {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
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
  border-top: 1px dashed var(--border);
  margin-top: 4px;
  padding-top: 8px;
}
.status-row .meta {
  color: var(--text-muted);
  font-size: 11.5px;
  margin-left: auto;
  text-align: right;
}
.status-row--ok { color: var(--success); }
.status-row--err { color: var(--danger); }
.status-row--warn { color: var(--warning); margin-top: 6px; }

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot--ok { background: var(--success); }
.dot--err { background: var(--danger); }
.dot--warn { background: var(--warning); }
.dot--pending {
  background: var(--text-muted);
  animation: blink 1.4s ease-in-out infinite;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.empty {
  font-size: 12.5px;
  color: var(--text-muted);
  padding: 12px 0;
}
.empty code {
  background: var(--code-bg);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 11.5px;
}

.novel-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.novel-item {
  display: flex;
  align-items: center;
  padding: 12px 0;
  border-top: 1px dashed var(--border);
  transition: background 120ms;
}
.novel-item:first-child {
  border-top: none;
}
.novel-item:hover {
  background: var(--hover-bg);
}
.novel-main {
  flex: 1;
}
.novel-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}
.novel-meta {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: 2px;
}
.open-arrow {
  color: var(--accent);
  font-size: 16px;
  padding-right: 4px;
}

.delete-btn {
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  cursor: pointer;
  margin-right: 8px;
  transition: all 120ms;
}
.delete-btn:hover {
  color: var(--danger);
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.2);
}

.footer {
  text-align: center;
  margin-top: 24px;
  font-size: 11.5px;
  color: var(--text-muted);
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.footer a {
  color: var(--accent);
  text-decoration: none;
  transition: color 150ms;
}
.footer a:hover {
  text-decoration: underline;
}
.footer .sep {
  color: var(--border);
}
</style>
