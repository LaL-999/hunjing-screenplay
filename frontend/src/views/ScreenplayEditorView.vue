<script setup lang="ts">
/**
 * 剧本编辑器主视图 — PR#11 commit 1 骨架。
 *
 * 后续 commit 会填充:
 *  - commit 2:左栏原文 + 右栏剧本面板 + scene 联动
 *  - commit 3:改编决策 3 选项面板(差异化)
 *  - commit 4:触发 compose + 进度对话框
 */
import { computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";

import AdaptationDecisionPanel from "../components/AdaptationDecisionPanel.vue";
import NovelTextPanel from "../components/NovelTextPanel.vue";
import ScreenplayPanel from "../components/ScreenplayPanel.vue";
import { useScreenplayStore } from "../stores/screenplay";

const props = defineProps<{ id: string }>();
const router = useRouter();
const store = useScreenplayStore();

const status = computed(() => {
  if (store.loadingState === "loading") return { label: "加载中...", tone: "muted" };
  if (store.loadingState === "composing")
    return { label: "AI 编排中(约 1-2 分钟)", tone: "muted" };
  if (store.loadingState === "error")
    return { label: `错误:${store.lastError}`, tone: "danger" };
  if (store.loadingState === "ready") return { label: "已生成", tone: "success" };
  return { label: "待生成 — 点击右上「生成剧本」", tone: "muted" };
});

function goHome() {
  router.push({ name: "home" });
}

// 路由变化时重新加载
watch(
  () => props.id,
  (id) => {
    if (id) store.loadLatestForNovel(id);
  },
  { immediate: false },
);

onMounted(() => {
  store.loadLatestForNovel(props.id);
});
</script>

<template>
  <div class="editor">
    <!-- ===== 顶栏 ===== -->
    <header class="topbar">
      <div class="topbar-left">
        <button class="back-btn" @click="goHome" title="返回主页">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
        </button>
        <div class="title-block">
          <div class="novel-title">
            {{
              store.novelTitle ||
              (store.loadingState === "error" ? "—" : "加载中...")
            }}
          </div>
          <div class="status-line">
            <span :class="['status-pill', `status-pill--${status.tone}`]">
              {{ status.label }}
            </span>
            <span v-if="store.hasScreenplay" class="stats">
              · {{ store.totalScenes }} 场 ·
              {{ store.screenplay?.characters.length ?? 0 }} 角色 ·
              {{ store.screenplay?.locations.length ?? 0 }} 地点
            </span>
          </div>
        </div>
      </div>
      <div class="topbar-right">
        <button
          class="primary-btn"
          :disabled="
            store.loadingState === 'loading' ||
            store.loadingState === 'composing'
          "
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
            <path
              d="M12 2l2.4 7.4H22l-6 4.6 2.3 7.4-6.3-4.6-6.3 4.6L8 14l-6-4.6h7.6z"
            />
          </svg>
          {{ store.hasScreenplay ? "重新生成" : "生成剧本" }}
        </button>
      </div>
    </header>

    <!-- ===== 双栏主体 ===== -->
    <div class="panes">
      <!-- 左栏:原文 -->
      <section class="pane pane-left">
        <div class="pane-header">
          <h3>原文</h3>
          <span class="pane-hint">{{ store.novelChapters.length }} 章 · 选中 scene 自动定位段落</span>
        </div>
        <div class="pane-body">
          <NovelTextPanel />
        </div>
      </section>

      <!-- 分隔线 -->
      <div class="divider"></div>

      <!-- 右栏:剧本 -->
      <section class="pane pane-right">
        <div class="pane-header">
          <h3>剧本</h3>
          <span v-if="store.hasScreenplay" class="pane-hint">
            scene_001 ~ scene_{{ String(store.totalScenes).padStart(3, "0") }} · 点击切换焦点
          </span>
          <span v-else class="pane-hint">未生成 — 点击右上「生成剧本」</span>
        </div>
        <div class="pane-body">
          <div v-if="!store.hasScreenplay" class="placeholder">
            <div class="placeholder-icon">
              <svg
                width="36"
                height="36"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M9 7h6M9 12h6M9 17h6" />
              </svg>
            </div>
            <div class="placeholder-text">
              剧本待生成<br />
              <span class="placeholder-hint">点击右上「生成剧本」运行 LLM 流水线</span>
            </div>
          </div>
          <ScreenplayPanel v-else />
        </div>
      </section>
    </div>

    <!-- ===== 改编决策浮窗(差异化创新核心)===== -->
    <AdaptationDecisionPanel />
  </div>
</template>

<style scoped>
.editor {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--bg);
  color: var(--text);
}

/* ===== 顶栏 ===== */
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  background: var(--card-bg);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.back-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--card-bg);
  color: var(--text-muted);
  transition: all 120ms;
}
.back-btn:hover {
  background: var(--hover-bg);
  color: var(--text);
}
.title-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.novel-title {
  font-size: 15px;
  font-weight: 600;
}
.status-line {
  font-size: 11.5px;
  color: var(--text-muted);
  display: flex;
  gap: 8px;
  align-items: center;
}
.status-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10.5px;
  font-weight: 500;
}
.status-pill--muted {
  background: var(--hover-bg);
  color: var(--text-muted);
}
.status-pill--success {
  background: rgba(16, 185, 129, 0.1);
  color: var(--success);
}
.status-pill--danger {
  background: rgba(239, 68, 68, 0.1);
  color: var(--danger);
}

.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 6px;
  background: var(--accent);
  color: white;
  border: none;
  font-size: 13px;
  font-weight: 500;
  transition: all 120ms;
}
.primary-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}
.primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ===== 双栏 ===== */
.panes {
  display: flex;
  flex: 1;
  overflow: hidden;
}
.pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}
.pane-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--card-bg);
  flex-shrink: 0;
}
.pane-header h3 {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.pane-hint {
  font-size: 11px;
  color: var(--text-muted);
}
.pane-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px;
}

.divider {
  width: 1px;
  background: var(--border);
  flex-shrink: 0;
}

/* 占位符 */
.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  text-align: center;
  color: var(--text-muted);
}
.placeholder-icon {
  margin-bottom: 12px;
  opacity: 0.4;
}
.placeholder-text {
  font-size: 13px;
  line-height: 1.6;
}
.placeholder-hint {
  font-size: 11.5px;
  color: var(--text-muted);
  opacity: 0.7;
}
</style>
