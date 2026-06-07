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
      <div class="brand">浑晶</div>
      <h1 class="title literary-heading">剧创态</h1>
      <p class="tagline">小说 <span class="arrow">→</span> 剧本</p>
      <p class="sub-tagline">浑晶平台 · 第五创作态</p>
    </header>

    <!-- 上传卡 — 直接醒目放最上 -->
    <NovelUploadCard @uploaded="handleUploaded" />

    <!-- 小说书架 -->
    <section v-if="!novelsLoading && novels.length > 0" class="shelf">
      <div class="shelf-title literary-heading">书架</div>
      <ul class="novel-list">
        <li
          v-for="n in novels"
          :key="n.id"
          class="novel-item"
          @click="openEditor(n.id)"
        >
          <div class="novel-main">
            <div class="novel-title literary">{{ n.title }}</div>
            <div class="novel-meta">
              <span>{{ n.total_chapters }} 章</span>
              <span class="meta-sep">·</span>
              <span>{{ n.total_chars.toLocaleString() }} 字</span>
              <span class="meta-sep">·</span>
              <span class="meta-format">{{ n.source_format }}</span>
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
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <polyline points="3 6 5 6 21 6" />
              <path
                d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6m5 0V4a2 2 0 0 1 2-2h0a2 2 0 0 1 2 2v2"
              />
            </svg>
          </button>
          <span class="open-arrow">›</span>
        </li>
      </ul>
    </section>

    <p v-if="!novelsLoading && novels.length === 0" class="shelf-empty literary">
      书架尚空 — 拖一份小说试试。
    </p>

    <!-- 系统状态(收到底部,不喧宾夺主) -->
    <section class="status-line">
      <template v-if="backendStatus === 'unknown'">
        <span class="dot dot--pending"></span>
        <span class="status-text">正在连接服务…</span>
      </template>
      <template v-else-if="backendStatus === 'ok'">
        <span class="dot dot--ok"></span>
        <span class="status-text">
          后端就绪
          <span class="status-meta">· {{ backendInfo.llm_model }}</span>
          <span
            v-if="backendInfo.llm_configured === false"
            class="status-warn"
          >
            · LLM 未配置
          </span>
        </span>
      </template>
      <template v-else>
        <span class="dot dot--err"></span>
        <span class="status-text status-err">服务未连接 · {{ errorMsg }}</span>
      </template>
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

.home {
  max-width: 640px;
  margin: var(--space-8) auto;
  padding: 0 var(--space-5);
}

.hdr {
  text-align: center;
  margin-bottom: var(--space-7);
  padding: var(--space-5) 0;
}
.brand {
  font-family: var(--font-serif);
  font-size: 13px;
  color: var(--text-muted);
  letter-spacing: 0.32em;
  margin-bottom: var(--space-3);
  text-transform: none;
}
.title {
  font-size: 38px;
  margin: 0 0 var(--space-3);
  font-weight: 500;
  color: var(--text-strong);
  letter-spacing: 0.04em;
  line-height: 1.2;
}
.tagline {
  font-family: var(--font-serif);
  color: var(--text-secondary);
  font-size: 16px;
  margin: 0 0 var(--space-2);
  letter-spacing: 0.12em;
}
.tagline .arrow {
  display: inline-block;
  margin: 0 var(--space-2);
  color: var(--accent);
  font-family: var(--font-sans);
  font-weight: 300;
  font-size: 18px;
  vertical-align: -1px;
}
.sub-tagline {
  font-family: var(--font-sans);
  color: var(--text-muted);
  font-size: 11.5px;
  margin: 0;
  letter-spacing: 0.16em;
}

/* === 书架 === */
.shelf {
  margin-top: var(--space-6);
  padding: var(--space-5) 0;
}
.shelf-title {
  font-size: 12px;
  color: var(--text-muted);
  letter-spacing: 0.24em;
  margin-bottom: var(--space-4);
  padding-left: var(--space-2);
  text-transform: uppercase;
}
.shelf-empty {
  text-align: center;
  color: var(--text-muted);
  font-size: 14px;
  padding: var(--space-7) 0;
  margin: 0;
  font-style: italic;
}

.novel-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.novel-item {
  display: flex;
  align-items: center;
  padding: var(--space-4) var(--space-3);
  cursor: pointer;
  transition: all var(--transition-fast);
  border-radius: var(--radius-md);
}
.novel-item + .novel-item {
  border-top: 1px solid var(--border-soft);
}
.novel-item:hover {
  background: var(--hover-bg);
}
.novel-main {
  flex: 1;
}
.novel-title {
  font-size: 18px;
  font-weight: 500;
  color: var(--text-strong);
  margin-bottom: var(--space-1);
}
.novel-meta {
  font-size: 11.5px;
  color: var(--text-muted);
  letter-spacing: 0.04em;
  display: flex;
  gap: 6px;
  align-items: center;
}
.meta-sep {
  color: var(--border);
}
.meta-format {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  padding: 1px 6px;
  background: var(--code-bg);
  border-radius: var(--radius-sm);
}
.open-arrow {
  color: var(--text-muted);
  font-size: 24px;
  padding-right: var(--space-2);
  font-family: var(--font-serif);
  transition: all var(--transition-fast);
}
.novel-item:hover .open-arrow {
  color: var(--accent);
  transform: translateX(2px);
}

/* === 状态行 === */
.status-line {
  margin-top: var(--space-7);
  padding-top: var(--space-4);
  border-top: 1px solid var(--border-soft);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.04em;
}
.status-text {
  display: flex;
  align-items: center;
  gap: 4px;
}
.status-meta {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 10.5px;
}
.status-warn {
  color: var(--warning);
}
.status-err {
  color: var(--danger);
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot--ok { background: var(--success); }
.dot--err { background: var(--danger); }
.dot--warn { background: var(--warning); }
.dot--pending {
  background: var(--text-muted);
  animation: blink 1.6s ease-in-out infinite;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.delete-btn {
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  cursor: pointer;
  margin-right: var(--space-2);
  opacity: 0;
  transition: all var(--transition-fast);
}
.novel-item:hover .delete-btn {
  opacity: 1;
}
.delete-btn:hover {
  color: var(--danger);
  background: var(--danger-soft);
}

.footer {
  text-align: center;
  margin-top: var(--space-7);
  padding-top: var(--space-4);
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  letter-spacing: 0.04em;
}
.footer a {
  color: var(--text-muted);
  transition: color var(--transition-fast);
}
.footer a:hover {
  color: var(--accent);
  border-bottom: none;
}
.footer .sep {
  color: var(--border);
}
</style>
