<script setup lang="ts">
/**
 * 剧本编辑器主视图 — PR#11 commit 1 骨架。
 *
 * 后续 commit 会填充:
 *  - commit 2:左栏原文 + 右栏剧本面板 + scene 联动
 *  - commit 3:改编决策 3 选项面板(差异化)
 *  - commit 4:触发 compose + 进度对话框
 */
import { computed, onMounted, provide, ref, watch } from "vue";
import { useRouter } from "vue-router";

import AdaptationDecisionPanel from "../components/AdaptationDecisionPanel.vue";
import ComposeDialog from "../components/ComposeDialog.vue";
import ExportMenu from "../components/ExportMenu.vue";
import NovelTextPanel from "../components/NovelTextPanel.vue";
import OptimizationModal from "../components/OptimizationModal.vue";
import ScreenplayPanel from "../components/ScreenplayPanel.vue";
import VersionSwitcher from "../components/VersionSwitcher.vue";
import { useScreenplayStore } from "../stores/screenplay";
import type { OptimizeScope } from "../types/screenplay";

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

const composeDialogVisible = ref<boolean>(false);
function openComposeDialog() {
  composeDialogVisible.value = true;
}
function closeComposeDialog() {
  composeDialogVisible.value = false;
}

// AI 优化弹窗(A + B 入口共用)
const optimizationModalVisible = ref<boolean>(false);
const optimizationScope = ref<OptimizeScope>("full_screenplay");
const optimizationTargetScene = ref<string | undefined>(undefined);

function openOptimizationModal(
  scope: OptimizeScope,
  targetSceneId?: string,
) {
  optimizationScope.value = scope;
  optimizationTargetScene.value = targetSceneId;
  optimizationModalVisible.value = true;
}
function closeOptimizationModal() {
  optimizationModalVisible.value = false;
}

// 把 open 函数 provide 给子组件(StructureReportPanel / ScreenplayPanel 用)
provide("openOptimizationModal", openOptimizationModal);

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
        <VersionSwitcher v-if="store.hasScreenplay" />
        <ExportMenu v-if="store.hasScreenplay" />
        <button
          class="primary-btn"
          :disabled="
            store.loadingState === 'loading' ||
            store.loadingState === 'composing'
          "
          @click="openComposeDialog"
        >
          {{ store.hasScreenplay ? "重新生成" : "生成剧本" }}
        </button>
      </div>
    </header>

    <!-- ===== 双栏主体 ===== -->
    <div class="panes">
      <!-- 左栏:原文 -->
      <section class="pane pane-left">
        <div class="pane-header">
          <h3>
            原文
            <span class="pane-stat">{{ store.novelChapters.length }} 章</span>
          </h3>
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
          <h3>
            剧本
            <span v-if="store.hasScreenplay" class="pane-stat">
              {{ store.totalScenes }} 场
            </span>
          </h3>
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

    <!-- ===== 编排对话框 ===== -->
    <ComposeDialog
      :visible="composeDialogVisible"
      @close="closeComposeDialog"
    />

    <!-- ===== AI 优化弹窗(A + B 共用,PR#16) ===== -->
    <OptimizationModal
      :visible="optimizationModalVisible"
      :scope="optimizationScope"
      :target-scene-id="optimizationTargetScene"
      @close="closeOptimizationModal"
    />
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

/* ===== 顶栏 — 更轻、更文气 ===== */
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4) var(--space-6);
  background: var(--card-bg);
  border-bottom: 1px solid var(--border-soft);
  flex-shrink: 0;
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.back-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  transition: all var(--transition-fast);
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
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 500;
  color: var(--text-strong);
  letter-spacing: 0.01em;
}
.status-line {
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  gap: var(--space-2);
  align-items: center;
  letter-spacing: 0.04em;
}
.status-pill {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 0.02em;
}
.status-pill--muted {
  background: var(--code-bg);
  color: var(--text-muted);
}
.status-pill--success {
  background: var(--success-soft);
  color: var(--success);
}
.status-pill--danger {
  background: var(--danger-soft);
  color: var(--danger);
}

.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border-radius: var(--radius-md);
  background: var(--accent);
  color: white;
  border: none;
  font-size: 12.5px;
  font-weight: 500;
  letter-spacing: 0.04em;
  transition: all var(--transition-fast);
}
.primary-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}
.primary-btn:disabled {
  opacity: 0.4;
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
  padding: var(--space-4) var(--space-6);
  border-bottom: 1px solid var(--border-soft);
  background: var(--card-bg);
  flex-shrink: 0;
}
.pane-header h3 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  letter-spacing: 0.24em;
  display: inline-flex;
  align-items: baseline;
  gap: var(--space-3);
}
.pane-stat {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-muted);
  letter-spacing: 0.06em;
  font-weight: 400;
  text-transform: lowercase;
  opacity: 0.7;
}
.pane-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-5) var(--space-6);
}

.divider {
  width: 1px;
  background: var(--border-soft);
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
  margin-bottom: var(--space-3);
  opacity: 0.3;
}
.placeholder-text {
  font-family: var(--font-serif);
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-secondary);
}
.placeholder-hint {
  font-size: 11.5px;
  color: var(--text-muted);
  margin-top: var(--space-2);
  letter-spacing: 0.04em;
}
</style>
